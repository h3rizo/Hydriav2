from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

import pytz

from apps.organization.models import Organisation, Ouvrage, OuvrageGradingAnnuel
from apps.planning.models import Planning
from apps.planning.repair_classification import (
    get_repair_classification,
    get_repair_fiches_queryset,
)


GRADE_API_TO_MODEL = {
    "A": "A",
    "B": "B",
    "B_panne": "B_PANNE",
    "C": "C",
    "D": "D",
    "D_panne": "D_PANNE",
}


class Command(BaseCommand):
    help = (
        "Synchronise le grading courant des ouvrages (workflow reparations) "
        "vers la table OuvrageGradingAnnuel."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--annee-target",
            type=int,
            required=True,
            help="Annee de stockage dans OuvrageGradingAnnuel (ex: 2025).",
        )
        parser.add_argument(
            "--annee-source",
            default="all",
            help=(
                "Filtre annee du workflow reparations: 'all' (par defaut) "
                "ou une annee numerique (ex: 2025)."
            ),
        )
        parser.add_argument(
            "--organisation-id",
            default=None,
            help="UUID organisation cible (prioritaire sur --organisation-name).",
        )
        parser.add_argument(
            "--organisation-name",
            default="soakoja",
            help="Nom (icontains) de l'organisation cible si --organisation-id absent.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Appliquer les changements (sinon simulation).",
        )

    def _resolve_organisation(self, organisation_id, organisation_name):
        if organisation_id:
            org = Organisation.objects.filter(id=organisation_id).first()
            if not org:
                raise CommandError(f"Organisation introuvable pour id={organisation_id}")
            return org

        org = Organisation.objects.filter(
            nom_organisation__icontains=organisation_name
        ).order_by("nom_organisation").first()
        if not org:
            raise CommandError(
                f"Aucune organisation trouvee avec nom contenant '{organisation_name}'"
            )
        return org

    def _repair_activity_mappings(self):
        fiches_reparation = list(get_repair_fiches_queryset())
        fiche_poste_ids = [fiche.id for fiche in fiches_reparation]
        fiche_poste_to_activite_nom = {
            fiche.id: (
                f"{getattr(getattr(fiche, 'type_activites', None), 'nomtype', '') or ''} "
                f"{fiche.tache or ''}"
            ).strip()
            for fiche in fiches_reparation
        }
        return fiche_poste_ids, fiche_poste_to_activite_nom

    @staticmethod
    def _compute_grade(has_reparations_futur, has_rehabilitations_futur, has_pannes_futur):
        if not has_reparations_futur and not has_rehabilitations_futur and not has_pannes_futur:
            return "A"
        if has_rehabilitations_futur and has_pannes_futur:
            return "D_panne"
        if has_rehabilitations_futur:
            return "D"
        if has_reparations_futur and has_pannes_futur:
            return "B_panne"
        if has_reparations_futur:
            return "B"
        return "C"

    def handle(self, *args, **options):
        annee_target = options["annee_target"]
        annee_source = str(options["annee_source"]).strip().lower()
        apply_changes = options["apply"]

        organisation = self._resolve_organisation(
            options.get("organisation_id"),
            options.get("organisation_name"),
        )

        annee_source_int = None
        if annee_source not in ("", "all"):
            try:
                annee_source_int = int(annee_source)
            except ValueError as exc:
                raise CommandError("--annee-source doit etre 'all' ou une annee numerique") from exc

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(
            f"[{mode}] organisation={organisation.nom_organisation} | "
            f"annee_target={annee_target} | annee_source={annee_source if annee_source else 'all'}"
        )

        ouvrages_qs = (
            Ouvrage.objects.filter(
                modalites_gestion__date_fin__isnull=True,
                modalites_gestion__gestionnaire=organisation,
                type_ouvrage__existe=True,
            )
            .distinct()
            .only("id", "nom_ouvrage")
        )

        ouvrages = list(ouvrages_qs)
        if not ouvrages:
            self.stdout.write(self.style.WARNING("Aucun ouvrage cible trouve."))
            return

        ouvrage_ids = [o.id for o in ouvrages]
        fiche_poste_ids, fiche_poste_to_activite_nom = self._repair_activity_mappings()
        if not fiche_poste_ids:
            self.stdout.write(self.style.WARNING("Aucune activite/fiches de reparation mappee."))
            return

        reparations_qs = Planning.objects.filter(
            ouvrage_id__in=ouvrage_ids,
            fiche_poste_id__in=fiche_poste_ids,
        ).values("ouvrage_id", "date", "fiche_poste_id")

        if annee_source_int:
            reparations_qs = reparations_qs.filter(date__year=annee_source_int)

        stats_by_ouvrage = {
            oid: {
                "has_reparations_futur": False,
                "has_rehabilitations_futur": False,
                "has_pannes_futur": False,
            }
            for oid in ouvrage_ids
        }

        tz_madagascar = pytz.timezone("Indian/Antananarivo")
        today = timezone.now().date()

        for rep in reparations_qs.iterator():
            rep_date = rep.get("date")
            if not rep_date:
                continue

            date_aware = rep_date if rep_date.tzinfo else timezone.make_aware(rep_date)
            date_mg = date_aware.astimezone(tz_madagascar)
            if date_mg.date() < today:
                continue

            ouvrage_stat = stats_by_ouvrage.get(rep["ouvrage_id"])
            if not ouvrage_stat:
                continue

            classification = get_repair_classification(
                type_name=fiche_poste_to_activite_nom.get(rep["fiche_poste_id"], ""),
            )
            family = classification.get("family")
            if classification.get("is_panne", False):
                ouvrage_stat["has_pannes_futur"] = True
            if family == "rehabilitation":
                ouvrage_stat["has_rehabilitations_futur"] = True
            elif family in ("reparation", "panne"):
                ouvrage_stat["has_reparations_futur"] = True

        grades_by_ouvrage = {}
        distribution = {k: 0 for k in GRADE_API_TO_MODEL.keys()}

        for ouvrage in ouvrages:
            s = stats_by_ouvrage[ouvrage.id]
            grade_api = self._compute_grade(
                s["has_reparations_futur"],
                s["has_rehabilitations_futur"],
                s["has_pannes_futur"],
            )
            grades_by_ouvrage[ouvrage.id] = GRADE_API_TO_MODEL[grade_api]
            distribution[grade_api] += 1

        existing_by_ouvrage = {
            item.ouvrage_id: item
            for item in OuvrageGradingAnnuel.objects.filter(
                annee=annee_target,
                ouvrage_id__in=ouvrage_ids,
            )
        }

        to_create = 0
        to_update = 0
        unchanged = 0

        for ouvrage_id, grade_model in grades_by_ouvrage.items():
            existing = existing_by_ouvrage.get(ouvrage_id)
            if not existing:
                to_create += 1
                if apply_changes:
                    OuvrageGradingAnnuel.objects.create(
                        ouvrage_id=ouvrage_id,
                        annee=annee_target,
                        grade=grade_model,
                        source="manuel",
                    )
                continue

            if existing.grade != grade_model:
                to_update += 1
                if apply_changes:
                    existing.grade = grade_model
                    existing.source = "manuel"
                    existing.save(update_fields=["grade", "source", "updated_at"])
            else:
                unchanged += 1

        self.stdout.write(
            "Distribution workflow: "
            f"A={distribution['A']}, "
            f"B={distribution['B']}, "
            f"B_panne={distribution['B_panne']}, "
            f"C={distribution['C']}, "
            f"D={distribution['D']}, "
            f"D_panne={distribution['D_panne']}"
        )
        self.stdout.write(
            f"Resultat: create={to_create}, update={to_update}, unchanged={unchanged}, total={len(ouvrages)}"
        )

        if not apply_changes:
            self.stdout.write(self.style.WARNING("Simulation terminee. Relancer avec --apply pour enregistrer."))
        else:
            self.stdout.write(self.style.SUCCESS("Synchronisation des gradings annuels terminee."))
