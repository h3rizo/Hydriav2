import json

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import PaiementForfaitaire, PointEau, Releve
from apps.planning.models import BonLivraison, PlanningDetail


class Command(BaseCommand):
    help = (
        "Nettoie les points d'eau sans ouvrage. "
        "Retire d'abord les references optionnelles, puis supprime le point s'il est devenu sans reference."
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
            help='Limite le nombre de points d eau analyses.',
        )
        parser.add_argument(
            '--backup-file',
            type=str,
            default='',
            help='Chemin JSON de sauvegarde des points impactes.',
        )

    def handle(self, *args, **options):
        apply_changes = bool(options['apply'])
        limit = options.get('limit')
        backup_file = (options.get('backup_file') or '').strip()

        qs = PointEau.objects.filter(ouvrage__isnull=True).order_by('code_point_eau', 'id')
        if limit:
            qs = qs[:limit]

        total = qs.count() if hasattr(qs, 'count') else len(qs)
        self.stdout.write(self.style.HTTP_INFO(f"Points d'eau orphelins detectes: {total}"))

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Aucun point d'eau orphelin detecte."))
            return

        backup_rows = []
        deleted_count = 0
        cleaned_bons_count = 0
        cleaned_details_count = 0
        blocked_count = 0
        error_count = 0

        for point_eau in qs:
            paiements_qs = PaiementForfaitaire.objects.filter(point_eau=point_eau)
            releves_qs = Releve.objects.filter(point_eau=point_eau)
            details_qs = PlanningDetail.objects.filter(point_eau=point_eau)
            bons_qs = BonLivraison.objects.filter(point_eau=point_eau)

            row = {
                'point_eau_id': str(point_eau.id),
                'code_point_eau': point_eau.code_point_eau,
                'idxls': point_eau.idxls,
                'paiements_forfaitaires': paiements_qs.count(),
                'releves': releves_qs.count(),
                'planning_details': details_qs.count(),
                'bons_livraison': bons_qs.count(),
            }
            backup_rows.append(row)

            self.stdout.write(
                f"- {point_eau.id} | {point_eau.code_point_eau or 'Sans code'} | "
                f"PF={row['paiements_forfaitaires']} RL={row['releves']} "
                f"DT={row['planning_details']} BL={row['bons_livraison']}"
            )

            if not apply_changes:
                continue

            try:
                with transaction.atomic():
                    details_updated = details_qs.update(point_eau=None)
                    bons_updated = bons_qs.update(point_eau=None)

                    cleaned_details_count += details_updated
                    cleaned_bons_count += bons_updated

                    still_blocked = (
                        PaiementForfaitaire.objects.filter(point_eau=point_eau).exists() or
                        Releve.objects.filter(point_eau=point_eau).exists() or
                        PlanningDetail.objects.filter(point_eau=point_eau).exists() or
                        BonLivraison.objects.filter(point_eau=point_eau).exists()
                    )

                    if still_blocked:
                        blocked_count += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ! Point conserve: references restantes sur {point_eau.code_point_eau or point_eau.id}"
                            )
                        )
                    else:
                        point_eau.delete()
                        deleted_count += 1
            except Exception as exc:
                error_count += 1
                self.stderr.write(self.style.ERROR(f"  x Echec {point_eau.id}: {exc}"))

        if backup_file:
            with open(backup_file, 'w', encoding='utf-8') as fh:
                json.dump(backup_rows, fh, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.SUCCESS(f"Sauvegarde ecrite: {backup_file}"))

        if apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Nettoyage applique: {deleted_count} point(s) supprime(s), "
                    f"{cleaned_bons_count} bon(s) nettoye(s), "
                    f"{cleaned_details_count} detail(s) nettoye(s), "
                    f"{blocked_count} point(s) bloque(s), "
                    f"{error_count} erreur(s)."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run termine: {total} point(s) analyses."
                )
            )
