"""
Vues pour l'impression des reparations.
"""

import pytz
from django.shortcuts import render
from django.utils import timezone

from apps.organization.models import Ouvrage
from apps.planning.models import Planning
from apps.planning.repair_classification import (
    get_planning_repair_classification,
    get_reparations_fiches_queryset,
)


def reparations_imprimer(request):
    """
    Page d'impression des reparations pour les ouvrages selectionnes.
    """
    ouvrages_ids = request.GET.get("ouvrages", "").split(",")
    ouvrages_ids = [item.strip() for item in ouvrages_ids if item.strip()]

    if not ouvrages_ids:
        return render(
            request,
            "planning/reparations_print.html",
            {"error": "Aucun ouvrage selectionne"},
        )

    activities_type = request.GET.get("activities_type") or request.GET.get(
        "type", "non_terminees"
    )

    fiches_reparation = list(get_reparations_fiches_queryset())
    fiche_poste_ids = [fiche.id for fiche in fiches_reparation]

    tz_madagascar = pytz.timezone("Indian/Antananarivo")
    today = timezone.now().astimezone(tz_madagascar).date()

    ouvrages_existants = Ouvrage.objects.filter(
        id__in=ouvrages_ids,
        type_ouvrage__existe=True,
    ).values_list("id", flat=True)

    plannings = (
        Planning.objects
        .filter(ouvrage_id__in=ouvrages_existants, fiche_poste_id__in=fiche_poste_ids)
        .select_related(
            "fiche_poste",
            "fiche_poste__type_activites",
            "type_activite",
            "employe",
            "ouvrage",
            "ouvrage__type_ouvrage",
        )
        .prefetch_related("details")
        .order_by("ouvrage__nom_ouvrage", "-date")
    )

    ouvrages_data = {}
    reparations_par_ouvrage = {}

    for planning in plannings:
        ouvrage_id = str(planning.ouvrage.id)

        planning_date = None
        if planning.date:
            if hasattr(planning.date, "date"):
                if planning.date.tzinfo:
                    planning_date = planning.date.astimezone(tz_madagascar).date()
                else:
                    planning_date = tz_madagascar.localize(planning.date).date()
            else:
                planning_date = planning.date

        if not planning_date:
            continue

        if activities_type == "non_terminees" and planning.estvalide:
            continue

        reparations_par_ouvrage.setdefault(
            ouvrage_id,
            {"ouvrage": planning.ouvrage, "plannings": []},
        )
        reparations_par_ouvrage[ouvrage_id]["plannings"].append(
            {"planning": planning, "date": planning_date}
        )

    for ouvrage_id, data in reparations_par_ouvrage.items():
        plannings_list = data["plannings"]
        has_reparation_future = False
        has_rehabilitation_future = False
        has_panne = False

        for item in plannings_list:
            planning = item["planning"]
            planning_date = item["date"]
            classification = get_planning_repair_classification(planning)
            family = classification.get("family")
            is_panne = classification.get("is_panne", False)

            if planning_date < today:
                continue

            if family == "rehabilitation":
                has_rehabilitation_future = True
                has_panne = has_panne or is_panne
            elif family in ("reparation", "panne"):
                has_reparation_future = True
                has_panne = has_panne or is_panne

        if has_rehabilitation_future:
            grading_label = "D panne" if has_panne else "D"
        elif has_reparation_future:
            grading_label = "B panne" if has_panne else "B"
        else:
            grading_label = "A"

        ouvrages_data[ouvrage_id] = {
            "ouvrage": data["ouvrage"],
            "grading": grading_label,
            "reparations": [],
            "stats": {
                "signalees": 0,
                "planifiees": 0,
                "en_cours": 0,
                "terminees": 0,
                "validees": 0,
            },
        }

        for item in plannings_list:
            planning = item["planning"]
            planning_date = item["date"]
            date_passee = planning_date < today

            if planning.estvalide:
                statut = "terminee"
                statut_display = "Terminee"
                statut_color = "success"
                ouvrages_data[ouvrage_id]["stats"]["terminees"] += 1
            elif planning_date >= today:
                statut = "planifiee"
                statut_display = "Planifiee"
                statut_color = "warning"
                ouvrages_data[ouvrage_id]["stats"]["planifiees"] += 1
            else:
                statut = "a_traiter"
                statut_display = "A traiter"
                statut_color = "error"
                ouvrages_data[ouvrage_id]["stats"]["en_cours"] += 1

            details_data = []
            for detail in planning.details.all():
                bons = []
                try:
                    from apps.billing.models import BonLivraison

                    bons_qs = (
                        BonLivraison.objects
                        .filter(planningdetail_bonlivraison__planning_detail_id=detail.id)
                        .select_related("fournisseur")
                    )

                    for bon in bons_qs:
                        bons.append(
                            {
                                "numero": bon.numero_bl,
                                "date_emission": bon.date_emission,
                                "fournisseur": (
                                    bon.fournisseur.nom_fournisseur
                                    if bon.fournisseur
                                    else None
                                ),
                                "statut": bon.statut,
                                "montant_total": bon.montant_total,
                            }
                        )
                except Exception:
                    pass

                details_data.append(
                    {
                        "designation": (
                            detail.designation.nom
                            if detail.designation
                            else "Sans designation"
                        ),
                        "type_designation": (
                            detail.designation.type_designation.nom
                            if detail.designation and detail.designation.type_designation
                            else None
                        ),
                        "quantite": detail.quantity or 0,
                        "prix_unitaire": detail.pu or 0,
                        "montant": detail.montant or 0,
                        "equipement": (
                            detail.equipement_constitutif.nom
                            if detail.equipement_constitutif
                            else None
                        ),
                        "point_eau": (
                            detail.point_eau.nomabonne or detail.point_eau.code_point_eau
                            if detail.point_eau
                            else None
                        ),
                        "retour": detail.retour,
                        "date_retour": detail.date_retour,
                        "bons_livraison": bons,
                    }
                )

            ouvrages_data[ouvrage_id]["reparations"].append(
                {
                    "id": planning.id,
                    "activite": planning.fiche_poste.tache if planning.fiche_poste else "-",
                    "date": planning.date,
                    "employe": planning.employe,
                    "remarque": planning.remarque or "",
                    "bilan": planning.bilan or "",
                    "suiteadonner": planning.suiteadonner or "",
                    "statut": statut,
                    "statut_display": statut_display,
                    "statut_color": statut_color,
                    "date_passee": date_passee,
                    "necessite_action": date_passee and not planning.estvalide,
                    "action_message": (
                        "Date passee : marquer terminee ou reporter la date"
                        if (date_passee and not planning.estvalide)
                        else ""
                    ),
                    "details": details_data,
                    "total_details": len(details_data),
                }
            )

    stats_globales = {
        "signalees": 0,
        "planifiees": 0,
        "en_cours": 0,
        "terminees": 0,
        "validees": 0,
    }

    for ouvrage_data in ouvrages_data.values():
        for key in stats_globales.keys():
            stats_globales[key] += ouvrage_data["stats"][key]

    grading_stats = {}
    total_ouvrages = len(ouvrages_data)

    for ouvrage_data in ouvrages_data.values():
        grading = ouvrage_data.get("grading", "Inconnu")
        grading_stats.setdefault(grading, {"count": 0, "percentage": 0})
        grading_stats[grading]["count"] += 1

    for grading in grading_stats:
        if total_ouvrages > 0:
            grading_stats[grading]["percentage"] = int(
                (grading_stats[grading]["count"] / total_ouvrages) * 100
            )

    context = {
        "ouvrages_data": ouvrages_data,
        "stats_globales": stats_globales,
        "grading_stats": grading_stats,
        "total_ouvrages": total_ouvrages,
        "date_impression": timezone.now().astimezone(tz_madagascar),
        "activities_type": activities_type,
        "activities_type_label": (
            "Activites non terminees uniquement"
            if activities_type == "non_terminees"
            else "Toutes les activites"
        ),
    }

    return render(request, "planning/reparations_print.html", context)
