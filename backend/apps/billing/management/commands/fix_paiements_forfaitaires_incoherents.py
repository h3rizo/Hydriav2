import json
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.billing.models import PaiementForfaitaire
from apps.employees.models_evaluation import FichePoste
from apps.planning.models import Planning


def _get_collecte_forfaitaire_fiche_poste():
    fiche_poste = FichePoste.objects.select_related('type_activites').filter(
        tache__iexact='Collecte des paiements forfaitaires'
    ).first()
    if fiche_poste:
        return fiche_poste

    return FichePoste.objects.select_related('type_activites').filter(
        tache__icontains='paiements forfaitaires'
    ).order_by('tache').first()


def _find_matching_forfaitaire_planning(point_eau, date_facture, employe):
    fiche_poste = _get_collecte_forfaitaire_fiche_poste()
    if not fiche_poste:
        raise ValueError(
            "La fiche de poste 'Collecte des paiements forfaitaires' est introuvable."
        )

    existing_qs = Planning.objects.filter(
        date__date=date_facture,
        ouvrage=point_eau.ouvrage,
        fiche_poste=fiche_poste,
    ).order_by('created_at', 'date')

    planning = None
    if employe:
        planning = existing_qs.filter(employe=employe).first()
    if planning is None:
        planning = existing_qs.first()

    return fiche_poste, planning


def _create_forfaitaire_planning(point_eau, date_facture, employe, fiche_poste):
    planning_dt = datetime.combine(date_facture, datetime.min.time())
    if timezone.is_naive(planning_dt) and timezone.is_aware(timezone.now()):
        planning_dt = timezone.make_aware(planning_dt, timezone.get_current_timezone())

    return Planning.objects.create(
        date=planning_dt,
        remarque=(
            "Collecte des paiements forfaitaires "
            f"(PE: {point_eau.code_point_eau or point_eau.id})"
        ),
        estvalide=False,
        statut='en_cours',
        employe=employe,
        ouvrage=point_eau.ouvrage,
        fiche_poste=fiche_poste,
        type_activite=fiche_poste.type_activites,
    )


class Command(BaseCommand):
    help = (
        "Corrige les paiements forfaitaires dont le planning pointe vers un ouvrage "
        "different de celui du point d'eau."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Applique reellement les corrections. Par defaut, affiche seulement le dry-run.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limite le nombre de paiements a analyser.',
        )
        parser.add_argument(
            '--backup-file',
            type=str,
            default='',
            help='Chemin JSON pour sauvegarder l etat initial des paiements impactes.',
        )

    def handle(self, *args, **options):
        apply_changes = bool(options['apply'])
        limit = options.get('limit')
        backup_file = (options.get('backup_file') or '').strip()

        qs = (
            PaiementForfaitaire.objects
            .exclude(planning__isnull=True)
            .exclude(point_eau__isnull=True)
            .exclude(planning__ouvrage_id=F('point_eau__ouvrage_id'))
            .select_related(
                'planning',
                'planning__ouvrage',
                'planning__employe',
                'point_eau',
                'point_eau__ouvrage',
            )
            .order_by('created_at', 'id')
        )

        if limit:
            qs = qs[:limit]

        total = qs.count() if hasattr(qs, 'count') else len(qs)
        self.stdout.write(self.style.HTTP_INFO(f"Paiements incoherents detectes: {total}"))

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Aucune incoherence detectee."))
            return

        backup_rows = []
        reassigned_count = 0
        reused_planning_count = 0
        created_planning_count = 0
        error_count = 0

        for paiement in qs:
            old_planning = paiement.planning
            old_employe = getattr(old_planning, 'employe', None)
            old_ouvrage_nom = getattr(getattr(old_planning, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'
            point_eau_ouvrage_nom = getattr(getattr(paiement.point_eau, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'

            fiche_poste, target_planning = _find_matching_forfaitaire_planning(
                point_eau=paiement.point_eau,
                date_facture=paiement.date_facture,
                employe=old_employe,
            )

            would_create = target_planning is None
            target_planning_id = str(target_planning.id) if target_planning else None

            backup_rows.append({
                'paiement_id': str(paiement.id),
                'date_facture': str(paiement.date_facture),
                'old_planning_id': str(old_planning.id) if old_planning else None,
                'old_planning_ouvrage': old_ouvrage_nom,
                'old_planning_employe': getattr(old_employe, 'surnom', None),
                'point_eau_id': str(paiement.point_eau_id) if paiement.point_eau_id else None,
                'point_eau_code': paiement.point_eau.code_point_eau,
                'point_eau_ouvrage': point_eau_ouvrage_nom,
                'target_planning_id': target_planning_id,
                'target_planning_would_create': would_create,
            })

            self.stdout.write(
                f"- {paiement.id} | {old_ouvrage_nom} -> {point_eau_ouvrage_nom} | "
                f"PE={paiement.point_eau.code_point_eau or paiement.point_eau_id}"
            )

            if not apply_changes:
                if would_create:
                    created_planning_count += 1
                else:
                    reused_planning_count += 1
                continue

            try:
                with transaction.atomic():
                    if target_planning is None:
                        target_planning = _create_forfaitaire_planning(
                            point_eau=paiement.point_eau,
                            date_facture=paiement.date_facture,
                            employe=old_employe,
                            fiche_poste=fiche_poste,
                        )
                        created_planning_count += 1
                    else:
                        reused_planning_count += 1

                    paiement.planning = target_planning
                    paiement.save(update_fields=['planning', 'updated_at'])
                    reassigned_count += 1
            except Exception as exc:
                error_count += 1
                self.stderr.write(
                    self.style.ERROR(f"  x Echec {paiement.id}: {exc}")
                )

        if backup_file:
            with open(backup_file, 'w', encoding='utf-8') as fh:
                json.dump(backup_rows, fh, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.SUCCESS(f"Sauvegarde ecrite: {backup_file}"))

        if apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Corrections appliquees: {reassigned_count} paiement(s), "
                    f"{reused_planning_count} planning(s) reutilise(s), "
                    f"{created_planning_count} planning(s) cree(s), "
                    f"{error_count} erreur(s)."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run termine: {total} paiement(s), "
                    f"{reused_planning_count} planning(s) deja trouvable(s), "
                    f"{created_planning_count} planning(s) a creer."
                )
            )
