from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import PaiementForfaitaire
from apps.planning.models import BonLivraison, Planning, PlanningDetail, PlanningEmploye
from apps.planning.views import _build_duplicate_merge_group_key
from apps.planning.views_simple import _build_new_secondary_participant_ids


class Command(BaseCommand):
    help = (
        "Fusionne les plannings en doublon selon le mode choisi. "
        "Deplace les details, bons de livraison et paiements forfaitaires "
        "vers la premiere ligne, puis supprime les doublons."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            choices=["strict", "activity"],
            default="activity",
            help=(
                "strict: date + scope + employe + activite + type_activite. "
                "activity: date + scope + activite."
            ),
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Appliquer les changements (sinon dry-run).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limiter le nombre de groupes traites.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Ne pas afficher le detail par groupe.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        mode = options["mode"]
        limit = options["limit"]
        quiet = options["quiet"]

        planning_list = list(
            Planning.objects.select_related("fiche_poste", "type_activite", "employe")
            .order_by("date", "created_at", "id")
        )

        grouped_plannings = {}
        for planning in planning_list:
            group_key = _build_duplicate_merge_group_key(planning, mode=mode)
            if not group_key:
                continue
            grouped_plannings.setdefault(group_key, []).append(planning)

        grouped_items = [items for items in grouped_plannings.values() if len(items) > 1]
        if limit:
            grouped_items = grouped_items[:limit]

        total_groups = 0
        total_duplicates = 0
        total_details = 0
        total_bons = 0
        total_paiements = 0
        total_participants = 0

        for items in grouped_items:
            total_groups += 1
            primary = next((item for item in items if item.estvalide), None) or items[0]
            duplicates = [item for item in items if item.id != primary.id]
            duplicate_ids = [duplicate.id for duplicate in duplicates]
            if not duplicate_ids:
                continue

            details_count = PlanningDetail.objects.filter(planning_id__in=duplicate_ids).count()
            bons_count = BonLivraison.objects.filter(planning_id__in=duplicate_ids).count()
            paiements_count = PaiementForfaitaire.objects.filter(planning_id__in=duplicate_ids).count()

            duplicate_owner_ids = [duplicate.employe_id for duplicate in duplicates if duplicate.employe_id]
            duplicate_participant_ids = list(
                PlanningEmploye.objects.filter(planning_id__in=duplicate_ids).values_list("employee_id", flat=True)
            )
            existing_participant_ids = list(
                PlanningEmploye.objects.filter(planning=primary).values_list("employee_id", flat=True)
            )
            participants_to_add = _build_new_secondary_participant_ids(
                primary,
                "",
                [*duplicate_owner_ids, *duplicate_participant_ids],
                existing_participant_ids=existing_participant_ids,
            )

            total_duplicates += len(duplicate_ids)
            total_details += details_count
            total_bons += bons_count
            total_paiements += paiements_count
            total_participants += len(participants_to_add)

            if not quiet:
                self.stdout.write(
                    f"[{total_groups}] primary={primary.id} -> {len(duplicate_ids)} doublon(s)"
                )

            if not apply_changes:
                continue

            with transaction.atomic():
                if details_count:
                    PlanningDetail.objects.filter(planning_id__in=duplicate_ids).update(planning=primary)
                if bons_count:
                    BonLivraison.objects.filter(planning_id__in=duplicate_ids).update(planning=primary)
                if paiements_count:
                    PaiementForfaitaire.objects.filter(planning_id__in=duplicate_ids).update(planning=primary)
                if participants_to_add:
                    PlanningEmploye.objects.bulk_create(
                        [
                            PlanningEmploye(planning_id=primary.id, employee_id=participant_id)
                            for participant_id in participants_to_add
                        ],
                        ignore_conflicts=True,
                    )

                Planning.objects.filter(id__in=duplicate_ids).delete()

        mode_label = "APPLIQUE" if apply_changes else "DRY-RUN"
        self.stdout.write(
            f"{mode_label}({mode}): groupes={total_groups}, "
            f"doublons={total_duplicates}, "
            f"details={total_details}, "
            f"bons={total_bons}, "
            f"paiements={total_paiements}, "
            f"participants_ajoutes={total_participants}"
        )
