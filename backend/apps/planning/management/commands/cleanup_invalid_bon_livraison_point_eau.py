import json

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Q

from apps.planning.models import BonLivraison


def _invalid_point_eau_q():
    mismatch_q = (
        Q(planning__ouvrage__isnull=False) &
        Q(point_eau__ouvrage__isnull=False) &
        ~Q(planning__ouvrage_id=F('point_eau__ouvrage_id'))
    )
    return (
        Q(point_eau__isnull=False) &
        (
            Q(point_eau__ouvrage__isnull=True) |
            Q(planning__ouvrage__isnull=True) |
            mismatch_q
        )
    )


class Command(BaseCommand):
    help = (
        "Nettoie les BonLivraison avec un point d'eau invalide "
        "(ouvrage manquant ou incoherent avec le planning)."
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
            BonLivraison.objects
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
        self.stdout.write(self.style.HTTP_INFO(f"BonLivraison invalides detectes: {total}"))

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Aucune anomalie detectee."))
            return

        backup_rows = []
        cleaned_count = 0
        error_count = 0

        for bon in qs:
            planning = bon.planning
            point_eau = bon.point_eau
            planning_ouvrage_nom = getattr(getattr(planning, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'
            planning_tache = getattr(getattr(planning, 'fiche_poste', None), 'tache', '') or ''
            point_eau_code = getattr(point_eau, 'code_point_eau', '') or str(bon.point_eau_id)
            point_eau_ouvrage_nom = getattr(getattr(point_eau, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'

            backup_rows.append({
                'bon_id': str(bon.id),
                'planning_id': str(bon.planning_id) if bon.planning_id else None,
                'planning_tache': planning_tache,
                'planning_ouvrage': planning_ouvrage_nom,
                'designation': str(bon.designation) if bon.designation_id else None,
                'point_eau_id': str(bon.point_eau_id) if bon.point_eau_id else None,
                'point_eau_code': point_eau_code,
                'point_eau_ouvrage': point_eau_ouvrage_nom,
            })

            self.stdout.write(
                f"- {bon.id} | {planning_tache or 'Sans tache'} | "
                f"{planning_ouvrage_nom} | {point_eau_code} -> {point_eau_ouvrage_nom}"
            )

            if not apply_changes:
                continue

            try:
                with transaction.atomic():
                    bon.point_eau = None
                    bon.save(update_fields=['point_eau', 'updated_at'])
                    cleaned_count += 1
            except Exception as exc:
                error_count += 1
                self.stderr.write(self.style.ERROR(f"  x Echec {bon.id}: {exc}"))

        if backup_file:
            with open(backup_file, 'w', encoding='utf-8') as fh:
                json.dump(backup_rows, fh, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.SUCCESS(f"Sauvegarde ecrite: {backup_file}"))

        if apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Nettoyage applique: {cleaned_count} bon(s), {error_count} erreur(s)."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run termine: {total} bon(s) seraient nettoyes."
                )
            )
