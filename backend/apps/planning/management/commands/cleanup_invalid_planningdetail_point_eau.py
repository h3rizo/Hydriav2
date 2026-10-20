import json

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Q

from apps.planning.models import PlanningDetail


ABSENCE_TACHE_LABELS = [
    'Repos',
    'Congé',
    'Récupération',
    'Repos médical',
    'Jour férié',
]


def _invalid_point_eau_q():
    mismatch_q = (
        Q(planning__ouvrage__isnull=False) &
        Q(point_eau__ouvrage__isnull=False) &
        ~Q(planning__ouvrage_id=F('point_eau__ouvrage_id'))
    )
    return (
        Q(point_eau__ouvrage__isnull=True) |
        Q(planning__ouvrage__isnull=True) |
        Q(planning__fiche_poste__tache__in=ABSENCE_TACHE_LABELS) |
        mismatch_q
    )


class Command(BaseCommand):
    help = (
        "Nettoie les PlanningDetail avec un point d'eau invalide "
        "(planning d'absence, ouvrage manquant ou ouvrage incoherent)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Applique reellement le nettoyage. Par defaut, dry-run.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limite le nombre de lignes analysees.',
        )
        parser.add_argument(
            '--backup-file',
            type=str,
            default='',
            help='Chemin JSON de sauvegarde des lignes impactees.',
        )

    def handle(self, *args, **options):
        apply_changes = bool(options['apply'])
        limit = options.get('limit')
        backup_file = (options.get('backup_file') or '').strip()

        qs = (
            PlanningDetail.objects
            .filter(point_eau__isnull=False)
            .filter(_invalid_point_eau_q())
            .select_related(
                'planning',
                'planning__fiche_poste',
                'planning__ouvrage',
                'point_eau',
                'point_eau__ouvrage',
                'designation',
            )
            .order_by('created_at', 'id')
        )

        if limit:
            qs = qs[:limit]

        total = qs.count() if hasattr(qs, 'count') else len(qs)
        self.stdout.write(self.style.HTTP_INFO(f"PlanningDetail invalides detectes: {total}"))

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Aucune anomalie detectee."))
            return

        backup_rows = []
        cleaned_count = 0
        error_count = 0

        for detail in qs:
            planning = detail.planning
            point_eau = detail.point_eau
            planning_tache = getattr(getattr(planning, 'fiche_poste', None), 'tache', '') or ''
            planning_ouvrage_nom = getattr(getattr(planning, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'
            point_eau_code = getattr(point_eau, 'code_point_eau', '') or str(detail.point_eau_id)
            point_eau_ouvrage_nom = getattr(getattr(point_eau, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'

            backup_rows.append({
                'detail_id': str(detail.id),
                'planning_id': str(detail.planning_id) if detail.planning_id else None,
                'planning_tache': planning_tache,
                'planning_ouvrage': planning_ouvrage_nom,
                'designation': str(detail.designation) if detail.designation_id else None,
                'point_eau_id': str(detail.point_eau_id) if detail.point_eau_id else None,
                'point_eau_code': point_eau_code,
                'point_eau_ouvrage': point_eau_ouvrage_nom,
            })

            self.stdout.write(
                f"- {detail.id} | {planning_tache or 'Sans tache'} | "
                f"{planning_ouvrage_nom} | {point_eau_code} -> {point_eau_ouvrage_nom}"
            )

            if not apply_changes:
                continue

            try:
                with transaction.atomic():
                    detail.point_eau = None
                    detail.save(update_fields=['point_eau', 'updated_at'])
                    cleaned_count += 1
            except Exception as exc:
                error_count += 1
                self.stderr.write(self.style.ERROR(f"  x Echec {detail.id}: {exc}"))

        if backup_file:
            with open(backup_file, 'w', encoding='utf-8') as fh:
                json.dump(backup_rows, fh, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.SUCCESS(f"Sauvegarde ecrite: {backup_file}"))

        if apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Nettoyage applique: {cleaned_count} detail(s), {error_count} erreur(s)."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run termine: {total} detail(s) seraient nettoyes."
                )
            )
