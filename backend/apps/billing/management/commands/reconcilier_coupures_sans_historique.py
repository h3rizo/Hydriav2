"""
Réconcilie les points d'eau « coupés » (date d'arrêt de branchement renseignée)
avec l'historique de coupure (CoupureEau).

Trois corrections, décidées le 28/09/2026 :

1. Point coupé SANS historique mais avec un relevé de consommation (> 0) plus
   d'un mois après sa date d'arrêt : la date d'arrêt est fausse.
   (Un relevé dans le mois qui suit l'arrêt est considéré comme le relevé de
   clôture et ne prouve pas que le point est encore en service.)
   a. Il est encore relevé (dernier relevé à moins de 60 jours du dernier
      relevé de son ouvrage) : il n'est pas coupé -> datearretbranchement vidée.
   b. Il ne l'est plus alors que son ouvrage l'est : il a été coupé plus tard
      -> date d'arrêt = jour de son dernier relevé avec consommation, et
      événement « coupure » créé à cette date.
2. Point coupé SANS historique et sans activité après l'arrêt : la coupure est
   reconnue -> création de l'événement « coupure » manquant à la date d'arrêt
   (raison « autre », note explicative). La date d'arrêt n'est pas modifiée.
   Les événements sont insérés par bulk_create pour NE PAS déclencher
   CoupureEau.save() -> sync_specific_point_eau(), qui retirerait aussi le
   tarif forfaitaire des points coupés depuis plus d'un an.
3. Coupure active dans l'historique mais date d'arrêt vide
   -> date d'arrêt = date de cette coupure (l'historique fait foi).

Les points dont l'historique confirme déjà la coupure ne sont pas touchés.
Les dates d'arrêt (DateTimeField stocké en UTC) sont comparées en jours de
Madagascar.

Dry-run par défaut ; --apply pour écrire. Avant écriture, l'état initial des
points modifiés est sauvegardé en JSON (--backup-dir) pour pouvoir revenir en
arrière.
"""
import json
import os
from datetime import datetime, timedelta

import pytz
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.billing.models import CoupureEau, PointEau, Releve

TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')
DELAI_RELEVE_CLOTURE = timedelta(days=31)
# Un point dont le dernier relevé a plus de 60 jours de retard sur celui de son
# ouvrage n'est plus relevé : il est considéré comme coupé depuis ce relevé.
RETARD_MAX_RELEVE = timedelta(days=60)
NOTE_RECONSTITUE = (
    "Événement reconstitué le {jour} depuis la date d'arrêt de branchement "
    "(coupure sans historique, aucune consommation relevée après l'arrêt)."
)
NOTE_REDATE = (
    "Événement reconstitué le {jour} : ancienne date d'arrêt {ancienne} démentie "
    "par des relevés avec consommation ; coupure fixée au dernier relevé, le point "
    "n'étant plus relevé alors que son ouvrage l'est."
)


def jour_madagascar(value):
    """Jour (date) à Madagascar d'une valeur date / datetime (naïve = UTC)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = pytz.utc.localize(value)
        return value.astimezone(TZ_MADAGASCAR).date()
    return value


def dernier_evenement_par_point():
    derniers = {}
    for pe_id, type_evt, date_evt in CoupureEau.objects.order_by(
        'point_eau_id', '-date_evenement', '-created_at'
    ).values_list('point_eau_id', 'type_evenement', 'date_evenement'):
        derniers.setdefault(pe_id, (type_evt, date_evt))
    return derniers


def dernier_releve(**filtres):
    return Releve.objects.filter(**filtres).aggregate(m=Max('datereleve'))['m']


def classer_points():
    """Retourne (a_vider, a_redater, a_documenter, a_dater) : listes de dicts."""
    derniers = dernier_evenement_par_point()

    a_vider, a_redater, a_documenter = [], [], []
    sans_historique = PointEau.objects.filter(
        datebranchement__isnull=False, datearretbranchement__isnull=False,
    ).exclude(id__in=list(derniers)).select_related('ouvrage')
    for point in sans_historique:
        arret = jour_madagascar(point.datearretbranchement)
        preuve = dernier_releve(
            point_eau=point, consommation__gt=0, datereleve__gt=arret + DELAI_RELEVE_CLOTURE,
        )
        info = {'point': point, 'arret': arret, 'dernier_releve_actif': preuve}
        if not preuve:
            a_documenter.append(info)
            continue
        dernier_point = dernier_releve(point_eau=point)
        dernier_ouvrage = dernier_releve(point_eau__ouvrage_id=point.ouvrage_id) if point.ouvrage_id else None
        info['dernier_releve_ouvrage'] = dernier_ouvrage
        if dernier_ouvrage and dernier_point < dernier_ouvrage - RETARD_MAX_RELEVE:
            a_redater.append(info)
        else:
            a_vider.append(info)

    a_dater = []
    for point in PointEau.objects.filter(
        datearretbranchement__isnull=True, id__in=list(derniers),
    ).select_related('ouvrage'):
        type_evt, date_evt = derniers[point.id]
        if type_evt == 'coupure':
            a_dater.append({'point': point, 'coupure': date_evt})

    return a_vider, a_redater, a_documenter, a_dater


def libelle(point):
    ouvrage = point.ouvrage.nom_ouvrage if point.ouvrage else 'sans ouvrage'
    return f"{point.nomabonne or point.code_point_eau or point.id} ({ouvrage})"


class Command(BaseCommand):
    help = "Réconcilie les dates d'arrêt de branchement avec l'historique de coupure."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help="Écrit les corrections (sinon dry-run).")
        parser.add_argument(
            '--backup-dir', default='.',
            help="Dossier où écrire la sauvegarde JSON de l'état initial (avec --apply).",
        )

    def handle(self, *args, **options):
        a_vider, a_redater, a_documenter, a_dater = classer_points()

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"1a. Date d'arrêt à vider (toujours relevé, non coupé) : {len(a_vider)}"
        ))
        for item in a_vider:
            self.stdout.write(
                f"   - {libelle(item['point'])} | arrêt {item['arret']} | "
                f"dernier relevé avec consommation {item['dernier_releve_actif']}"
            )
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"1b. Coupé plus tard : date d'arrêt = dernier relevé + événement : {len(a_redater)}"
        ))
        for item in a_redater:
            self.stdout.write(
                f"   - {libelle(item['point'])} | arrêt {item['arret']} -> {item['dernier_releve_actif']} "
                f"(ouvrage relevé jusqu'au {item['dernier_releve_ouvrage']})"
            )
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"2. Événement de coupure à reconstituer : {len(a_documenter)}"
        ))
        for item in a_documenter:
            self.stdout.write(f"   - {libelle(item['point'])} | coupure au {item['arret']}")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"3. Date d'arrêt à renseigner depuis l'historique : {len(a_dater)}"
        ))
        for item in a_dater:
            self.stdout.write(f"   - {libelle(item['point'])} | coupure au {item['coupure']}")

        if not options['apply']:
            self.stdout.write(self.style.NOTICE("\nDry-run : rien n'a été écrit. Relancez avec --apply."))
            return

        horodatage = timezone.localtime().strftime('%Y%m%d-%H%M%S')
        backup_path = os.path.join(options['backup_dir'], f'backup_reconcilier_coupures_{horodatage}.json')
        with open(backup_path, 'w', encoding='utf-8') as handle:
            json.dump({
                'a_vider': [
                    {'id': str(i['point'].id), 'datearretbranchement': i['point'].datearretbranchement.isoformat()}
                    for i in a_vider
                ],
                'a_redater': [
                    {'id': str(i['point'].id), 'datearretbranchement': i['point'].datearretbranchement.isoformat()}
                    for i in a_redater
                ],
                'a_documenter': [str(i['point'].id) for i in a_documenter],
                'a_dater': [str(i['point'].id) for i in a_dater],
            }, handle, ensure_ascii=False, indent=2)
        self.stdout.write(f"Sauvegarde de l'état initial : {backup_path}")

        jour = timezone.localdate().strftime('%d/%m/%Y')
        with transaction.atomic():
            PointEau.objects.filter(id__in=[i['point'].id for i in a_vider]).update(datearretbranchement=None)
            for item in a_redater:
                nouvelle_date = item['dernier_releve_actif']
                PointEau.objects.filter(id=item['point'].id).update(
                    datearretbranchement=TZ_MADAGASCAR.localize(datetime.combine(nouvelle_date, datetime.min.time()))
                )
            CoupureEau.objects.bulk_create(
                [
                    CoupureEau(
                        point_eau=item['point'],
                        type_evenement='coupure',
                        date_evenement=item['arret'],
                        raison='autre',
                        notes=NOTE_RECONSTITUE.format(jour=jour),
                    )
                    for item in a_documenter
                ] + [
                    CoupureEau(
                        point_eau=item['point'],
                        type_evenement='coupure',
                        date_evenement=item['dernier_releve_actif'],
                        raison='autre',
                        notes=NOTE_REDATE.format(jour=jour, ancienne=item['arret'].strftime('%d/%m/%Y')),
                    )
                    for item in a_redater
                ]
            )
            for item in a_dater:
                point = item['point']
                # Même affectation que CoupureEau.sync_specific_point_eau
                point.datearretbranchement = item['coupure']
                point.save(update_fields=['datearretbranchement'])

        self.stdout.write(self.style.SUCCESS(
            f"\nÉcrit : {len(a_vider)} date(s) d'arrêt vidée(s), "
            f"{len(a_redater)} date(s) d'arrêt reportée(s) au dernier relevé,"
            f"{len(a_documenter) + len(a_redater)} événement(s) de coupure créé(s), "
            f"{len(a_dater)} date(s) d'arrêt renseignée(s)."
        ))
