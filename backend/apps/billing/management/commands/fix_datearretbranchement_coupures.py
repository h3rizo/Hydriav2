"""
Resynchronise PointEau.datearretbranchement avec l'historique de coupure
(modèle CoupureEau).

Règle (identique à CoupureEau.sync_specific_point_eau) : pour chaque point
d'eau ayant au moins un événement de coupure, on regarde le DERNIER événement
par date ; si c'est une 'coupure' (pas de 'remise' après) -> datearretbranchement
= date de cet événement ; sinon -> datearretbranchement = None.

La colonne peut être désynchronisée quand des événements CoupureEau ont été
créés/importés sans passer par .save() (qui déclenche la synchro). Les pages
de recouvrement (dashboard volume, widget, impression) s'appuient sur cette
colonne + l'historique : une fois la colonne remise d'aplomb, les factures
d'un point coupé sortent bien du montant à recouvrer.

Dry-run par défaut ; ajouter --apply pour écrire.
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from apps.billing.models import CoupureEau, PointEau


def _as_date(value):
    # datearretbranchement est stocké en UTC : minuit à Madagascar = 21h UTC la
    # veille. Sans conversion, chaque point « coupé » paraîtrait décalé d'un jour
    # par rapport à son événement de coupure et serait réécrit à tort.
    if isinstance(value, datetime):
        from apps.billing.management.commands.reconcilier_coupures_sans_historique import jour_madagascar
        return jour_madagascar(value)
    return value


class Command(BaseCommand):
    help = "Resynchronise PointEau.datearretbranchement avec l'historique CoupureEau."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help="Écrit les corrections. Sans cette option : dry-run (aperçu seulement).",
        )
        parser.add_argument(
            '--full-sync',
            action='store_true',
            help=(
                "Utilise CoupureEau.sync_specific_point_eau() (resynchro complète : "
                "inclut la règle métier qui retire le tarif forfaitaire d'un point "
                "coupé depuis plus d'un an). Par défaut : seule la colonne "
                "datearretbranchement est touchée."
            ),
        )

    def handle(self, *args, **options):
        apply = options['apply']
        full_sync = options['full_sync']

        point_ids = list(
            CoupureEau.objects.values_list('point_eau_id', flat=True).distinct()
        )
        self.stdout.write(
            f"{len(point_ids)} point(s) d'eau avec un historique de coupure."
        )

        points = PointEau.objects.filter(id__in=point_ids)
        derniers = {
            pe_id: (type_evt, date_evt)
            for pe_id, type_evt, date_evt in _latest_events(point_ids)
        }

        a_corriger = []
        for pe in points:
            type_evt, date_evt = derniers.get(pe.id, (None, None))
            cible = date_evt if type_evt == 'coupure' else None
            actuel = _as_date(pe.datearretbranchement)
            if _as_date(cible) != actuel:
                a_corriger.append((pe, actuel, cible, type_evt))

        if not a_corriger:
            self.stdout.write(self.style.SUCCESS(
                "datearretbranchement déjà conforme à l'historique pour tous les points."
            ))
            return

        self.stdout.write(
            self.style.WARNING(f"{len(a_corriger)} point(s) à corriger :")
        )
        for pe, actuel, cible, type_evt in a_corriger:
            label = (
                pe.nomabonne or pe.code_point_eau or str(pe.id)
            )
            self.stdout.write(
                f"  - {label}  ({pe.id})  {actuel!r} -> {_as_date(cible)!r}"
                f"  [dernier évènement: {type_evt or 'aucun'}]"
            )

        if not apply:
            self.stdout.write(self.style.NOTICE(
                "\nDry-run. Relancez avec --apply pour écrire ces corrections."
            ))
            return

        corriges = 0
        for pe, actuel, cible, type_evt in a_corriger:
            if full_sync:
                CoupureEau.sync_specific_point_eau(pe)
            else:
                pe.datearretbranchement = cible
                pe.save(update_fields=['datearretbranchement'])
            corriges += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n{corriges} point(s) d'eau corrigé(s)"
            f"{' (full-sync)' if full_sync else ''}."
        ))


def _latest_events(point_ids):
    """Dernier évènement (par date puis created_at) pour chaque point donné."""
    seen = set()
    for evt in CoupureEau.objects.filter(
        point_eau_id__in=point_ids,
    ).order_by('point_eau_id', '-date_evenement', '-created_at').values_list(
        'point_eau_id', 'type_evenement', 'date_evenement',
    ):
        pe_id = evt[0]
        if pe_id in seen:
            continue
        seen.add(pe_id)
        yield evt
