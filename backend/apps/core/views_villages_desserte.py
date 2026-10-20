import uuid
from collections import Counter
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import ModaliteGestion, PointEau
from apps.chantiers.models import DemandeVillage
from apps.organization.models import Ouvrage
from apps.organization.scoping import get_user_organisation
from apps.geography.models import Commune, District, Fokontany, Parcelle, Region, Village
from apps.core.models import FiltreSauvegarde


DEMANDE_STATUS_LABELS = dict(DemandeVillage.STATUT_CHOICES)
TYPE_GESTION_LABELS = dict(ModaliteGestion.TYPE_GESTION_CHOICES)
MODALITE_PAIEMENT_LABELS = dict(ModaliteGestion.MODALITE_PAIEMENT_CHOICES)

SEGMENT_STYLES = {
    "root": {
        "surface_class": "bg-primary text-primary-content shadow-lg",
        "accent_text_class": "text-primary-content",
        "progress_class": "progress-primary",
    },
    "success": {
        "surface_class": "bg-base-100 border border-success/30 shadow",
        "accent_text_class": "text-success",
        "progress_class": "progress-success",
    },
    "info": {
        "surface_class": "bg-base-100 border border-info/30 shadow",
        "accent_text_class": "text-info",
        "progress_class": "progress-info",
    },
    "warning": {
        "surface_class": "bg-base-100 border border-warning/30 shadow",
        "accent_text_class": "text-warning",
        "progress_class": "progress-warning",
    },
    "error": {
        "surface_class": "bg-base-100 border border-error/30 shadow",
        "accent_text_class": "text-error",
        "progress_class": "progress-error",
    },
    "secondary": {
        "surface_class": "bg-base-100 border border-secondary/30 shadow",
        "accent_text_class": "text-secondary",
        "progress_class": "progress-secondary",
    },
    "base": {
        "surface_class": "bg-base-100 border border-base-300 shadow",
        "accent_text_class": "text-base-content/70",
        "progress_class": "progress-neutral",
    },
}


def _normalize_filter_value(value):
    value = (value or "").strip()
    if not value or value == "all":
        return ""
    return value


def _split_ids(value):
    """'a,b' -> ['a', 'b'] (ignore les vides, 'all' et les valeurs qui ne sont pas des UUID)."""
    ids = []
    for part in (value or "").split(","):
        part = part.strip()
        if not part or part == "all":
            continue
        try:
            ids.append(str(uuid.UUID(part)))
        except ValueError:
            continue
    return ids


def _get_multi_param(request, name):
    """Filtre à choix multiple : ?name=a&name=b ou ?name=a,b -> 'a,b'."""
    raw = ",".join(request.GET.getlist(name))
    return ",".join(dict.fromkeys(_split_ids(raw)))


def _get_commune_param(request):
    return _get_multi_param(request, "commune")


def _get_district_param(request):
    return _get_multi_param(request, "district")


def _dysfunctional_ouvrage_ids(ouvrage_ids):
    """
    Ouvrages « dysfonctionnels » = union de deux règles :
    1. Grading D (ou D panne) de la page « Suivi des réparations » : au moins une
       réhabilitation non terminée (planning non validé), toutes années confondues.
       Même règle que get_repair_workflow_grading_from_plannings.
    2. Statut fonctionnel de l'ouvrage (page Ouvrages) : chantier actif en cours,
       ou case manuelle « marqué non fonctionnel » cochée (voir
       apps.organization.services_fonctionnalite.get_statuts_fonctionnel_bulk).
    """
    from apps.organization.services_fonctionnalite import get_statuts_fonctionnel_bulk
    from apps.planning.models import Planning
    from apps.planning.repair_classification import get_reparations_fiches_queryset
    from apps.planning.repair_workflow_grading import get_repair_workflow_grading_from_plannings

    ids = {str(o) for o in ouvrage_ids if o}
    if not ids:
        return set()

    dysfunctional = set()

    # Règle 2 : statut fonctionnel (case manuelle / chantier actif)
    for ouvrage_id, info in get_statuts_fonctionnel_bulk(ids).items():
        if not info["fonctionnel"]:
            dysfunctional.add(str(ouvrage_id))

    # Règle 1 : grading D / D panne des réparations
    fiches = list(get_reparations_fiches_queryset())
    if not fiches:
        return dysfunctional
    fiche_to_nom = {
        fiche.id: f"{getattr(getattr(fiche, 'type_activites', None), 'nomtype', '') or ''} {fiche.tache or ''}".strip()
        for fiche in fiches
    }
    open_by_ouvrage = {}
    # estvalide peut être NULL : comme sur la page réparations, « non validé » = pas explicitement validé
    for planning in Planning.objects.filter(
        ouvrage_id__in=ids, fiche_poste_id__in=list(fiche_to_nom),
    ).exclude(estvalide=True).only("id", "ouvrage_id", "fiche_poste_id", "estvalide", "remarque"):
        open_by_ouvrage.setdefault(str(planning.ouvrage_id), []).append(planning)
    for ouvrage_id, plannings in open_by_ouvrage.items():
        code = get_repair_workflow_grading_from_plannings(
            plannings, fiche_poste_to_activite_nom=fiche_to_nom)["code"]
        if code in ("D", "D_panne"):
            dysfunctional.add(ouvrage_id)
    return dysfunctional


def _village_is_functional(has_served, served_ouvrage_ids, dysfunctional_ids):
    """Village desservi « fonctionnel » : au moins un ouvrage qui le dessert n'est pas en grading D."""
    if not has_served:
        return False
    ouvrages = {str(o) for o in served_ouvrage_ids}
    return not ouvrages or bool(ouvrages - dysfunctional_ids)


def _own_other_org_split(village_ids, village_stats, user_org_id):
    """
    Repartit des villages ayant au moins une modalite de gestion active en deux
    groupes : geres par l'organisation connectee (`user_org_id`) et geres
    uniquement par une ou plusieurs autres organisations.

    Un village est compte dans « organisation connectee » des lors qu'au moins
    une de ses modalites actives appartient a cette organisation, meme si
    l'organisation dominante (`primary_org_key`) du village en est une autre.

    Retourne `None` si `user_org_id` est vide (utilisateur sans organisation
    rattachee, ex. superuser) : dans ce cas la case « avec modalite » reste
    listee par organisation sans distinction connectee/autre.
    """
    if not user_org_id:
        return None
    own_ids = {
        str(village_id)
        for village_id in village_ids
        if user_org_id in village_stats.get(str(village_id), {}).get("management_org_ids", set())
    }
    other_ids = {str(village_id) for village_id in village_ids} - own_ids
    return own_ids, other_ids


def _percentage(part, total):
    if not total:
        return 0
    return int(round((part / total) * 100))


def _join_display(values, fallback="-"):
    cleaned = sorted({str(value).strip() for value in values if str(value or "").strip()})
    return ", ".join(cleaned) if cleaned else fallback


def _sample_village_names(names_by_id, village_ids, limit=5):
    names = sorted(
        {
            names_by_id.get(str(village_id), "")
            for village_id in village_ids
            if names_by_id.get(str(village_id), "")
        }
    )
    return names[:limit]


def _sum_habitants(village_ids, habitants_by_village):
    return sum(int(habitants_by_village.get(str(village_id), 0) or 0) for village_id in village_ids)


def _summarize_village_desserte(all_village_ids, served_ids, functional_ids, requested_ids):
    all_ids = {str(village_id) for village_id in all_village_ids}
    served_ids = all_ids & {str(village_id) for village_id in served_ids}
    functional_ids = served_ids & {str(village_id) for village_id in functional_ids}

    non_served_ids = all_ids - served_ids
    non_functional_ids = served_ids - functional_ids
    requested_ids = non_served_ids & {str(village_id) for village_id in requested_ids}
    without_request_ids = non_served_ids - requested_ids

    total_count = len(all_ids)
    served_count = len(served_ids)
    non_served_count = len(non_served_ids)
    functional_count = len(functional_ids)
    non_functional_count = len(non_functional_ids)
    requested_count = len(requested_ids)
    without_request_count = len(without_request_ids)

    return {
        "all_ids": all_ids,
        "served_ids": served_ids,
        "non_served_ids": non_served_ids,
        "functional_ids": functional_ids,
        "non_functional_ids": non_functional_ids,
        "requested_ids": requested_ids,
        "without_request_ids": without_request_ids,
        "total_count": total_count,
        "served_count": served_count,
        "non_served_count": non_served_count,
        "functional_count": functional_count,
        "non_functional_count": non_functional_count,
        "requested_count": requested_count,
        "without_request_count": without_request_count,
        "served_pct_total": _percentage(served_count, total_count),
        "non_served_pct_total": _percentage(non_served_count, total_count),
        "functional_pct_served": _percentage(functional_count, served_count),
        "non_functional_pct_served": _percentage(non_functional_count, served_count),
        "requested_pct_non_served": _percentage(requested_count, non_served_count),
        "without_request_pct_non_served": _percentage(without_request_count, non_served_count),
    }


def _apply_geo_filters(villages_qs, region_id="", district_id="", commune_id="", fokontany_id=""):
    if region_id:
        villages_qs = villages_qs.filter(fokontany__commune__district__region_id=region_id)
    district_ids = _split_ids(district_id)
    if district_ids:
        villages_qs = villages_qs.filter(fokontany__commune__district_id__in=district_ids)
    commune_ids = _split_ids(commune_id)
    if commune_ids:
        villages_qs = villages_qs.filter(fokontany__commune_id__in=commune_ids)
    if fokontany_id:
        villages_qs = villages_qs.filter(fokontany_id=fokontany_id)
    return villages_qs


def _geo_children(model, region_id="", district_id="", commune_id=""):
    """Options d'un niveau géographique, filtrées en cascade par les niveaux supérieurs."""
    qs = model.objects.all()
    if model is District:
        if region_id:
            qs = qs.filter(region_id=region_id)
    elif model is Commune:
        if _split_ids(district_id):
            qs = qs.filter(district_id__in=_split_ids(district_id))
        elif region_id:
            qs = qs.filter(district__region_id=region_id)
    elif model is Fokontany:
        commune_ids = _split_ids(commune_id)
        if commune_ids:
            qs = qs.filter(commune_id__in=commune_ids)
        elif _split_ids(district_id):
            qs = qs.filter(commune__district_id__in=_split_ids(district_id))
        elif region_id:
            qs = qs.filter(commune__district__region_id=region_id)
    return qs


@login_required
def analyse_villages_desserte_geo_options(request):
    """Options des listes Région > District > Commune > Fokontany (filtres en cascade)."""
    region_id = _normalize_filter_value(request.GET.get("region"))
    district_id = _get_district_param(request)
    commune_id = _get_commune_param(request)
    return JsonResponse({
        "success": True,
        "districts": [
            {"id": str(d.id), "nom": d.nom_district}
            for d in _geo_children(District, region_id).order_by("nom_district")],
        "communes": [
            {"id": str(c.id), "nom": c.nom_commune}
            for c in _geo_children(Commune, region_id, district_id).order_by("nom_commune")],
        "fokontanys": [
            {"id": str(f.id), "nom": f.nom_fokontany}
            for f in _geo_children(Fokontany, region_id, district_id, commune_id).order_by("nom_fokontany")],
    })


def _build_scope_label(region=None, district=None, commune=None, fokontany=None):
    if fokontany:
        return f"Fokontany : {fokontany.nom_fokontany}"
    if commune:
        communes = list(commune) if isinstance(commune, (list, tuple, set)) else [commune]
        noms = ", ".join(c.nom_commune for c in communes)
        return f"{'Communes' if len(communes) > 1 else 'Commune'} : {noms}"
    if district:
        districts = list(district) if isinstance(district, (list, tuple, set)) else [district]
        noms = ", ".join(d.nom_district for d in districts)
        return f"{'Districts' if len(districts) > 1 else 'District'} : {noms}"
    if region:
        return f"Region : {region.nom_region}"
    return "Toutes les zones"


def _build_detail_url(base_url, filter_params, detail_key):
    params = {key: value for key, value in filter_params.items() if value}
    params["detail"] = detail_key
    return f"{base_url}?{urlencode(params)}#details"


def _build_segment_node(
    *,
    key,
    title,
    level_label,
    village_ids,
    habitants_by_village,
    village_names,
    base_url,
    filter_params,
    detail_registry,
    parent_count,
    parent_habitants,
    tone="base",
    icon_class="fas fa-circle",
    subtitle="",
):
    village_ids = {str(village_id) for village_id in village_ids}
    styles = SEGMENT_STYLES[tone]
    village_count = len(village_ids)
    habitants_count = _sum_habitants(village_ids, habitants_by_village)

    node = {
        "key": key,
        "title": title,
        "level_label": level_label,
        "subtitle": subtitle,
        "tone": tone,
        "count": village_count,
        "habitants": habitants_count,
        "count_pct": _percentage(village_count, parent_count),
        "habitants_pct": _percentage(habitants_count, parent_habitants),
        "count_max": parent_count or 1,
        "habitants_max": parent_habitants or 1,
        "examples": _sample_village_names(village_names, village_ids),
        "detail_url": _build_detail_url(base_url, filter_params, key),
        "surface_class": styles["surface_class"],
        "accent_text_class": styles["accent_text_class"],
        "progress_class": styles["progress_class"],
        "icon_class": icon_class,
        "children": [],
    }
    detail_registry[key] = {
        "key": key,
        "title": title,
        "level_label": level_label,
        "subtitle": subtitle,
        "village_ids": village_ids,
        "count": village_count,
        "habitants": habitants_count,
        "count_pct": node["count_pct"],
        "habitants_pct": node["habitants_pct"],
        "count_max": node["count_max"],
        "habitants_max": node["habitants_max"],
        "accent_text_class": styles["accent_text_class"],
        "progress_class": styles["progress_class"],
    }
    return node


def _make_empty_village_stat(row):
    village_id = str(row["id"])
    return {
        "id": village_id,
        "nom_village": row["nom_village"],
        "fokontany": row.get("fokontany__nom_fokontany") or "-",
        "commune": row.get("fokontany__commune__nom_commune") or "-",
        "district": row.get("fokontany__commune__district__nom_district") or "-",
        "region": row.get("fokontany__commune__district__region__nom_region") or "-",
        "habitants": 0,
        "has_served": False,
        "has_functional": False,
        "points_served_count": 0,
        "points_functional_count": 0,
        "served_ouvrage_ids": set(),
        "functional_ouvrage_ids": set(),
        "demande_count": 0,
        "demande_status_labels": set(),
        "demande_status_counts": Counter(),
        "has_management_modalite": False,
        "management_org_labels": set(),
        "management_org_ids": set(),
        "management_type_labels": set(),
        "management_payment_labels": set(),
        "primary_org_key": "",
        "primary_org_label": "",
    }


def _build_detail_rows(selected_ids, village_stats):
    rows = []
    for village_id in selected_ids:
        stat = village_stats.get(str(village_id))
        if not stat:
            continue
        rows.append(
            {
                "village": stat["nom_village"],
                "fokontany": stat["fokontany"],
                "commune": stat["commune"],
                "district": stat["district"],
                "region": stat["region"],
                "habitants": stat["habitants"],
                "desserte_label": "Desservi" if stat["has_served"] else "Non desservi",
                "fonctionnalite_label": (
                    "Fonctionnel"
                    if stat["has_functional"]
                    else "Dysfonctionnel"
                    if stat["has_served"]
                    else "-"
                ),
                "points_served_count": stat["points_served_count"],
                "points_functional_count": stat["points_functional_count"],
                "ouvrages_served_count": len(stat["served_ouvrage_ids"]),
                "ouvrages_functional_count": len(stat["functional_ouvrage_ids"]),
                "demande_count": stat["demande_count"],
                "a_demande": stat["demande_count"] > 0,
                "demande_statuses": _join_display(stat["demande_status_labels"]),
                "has_management_modalite": "Oui" if stat["has_management_modalite"] else "Non",
                "management_types": _join_display(stat["management_type_labels"], "Aucune"),
                "management_payments": _join_display(stat["management_payment_labels"], "Aucune"),
                "management_orgs": _join_display(stat["management_org_labels"], "Aucune"),
                "management_primary_org": stat["primary_org_label"] or "-",
            }
        )
    rows.sort(key=lambda item: (-item["habitants"], item["village"].lower()))
    return rows


def _group_detail_rows_by_geo(rows):
    """Regroupe les lignes de detail par Region > District > Commune.

    Sert a la fois a l'affichage (table avec en-tetes de groupe) et a l'export
    Excel : les colonnes Region / District / Commune deviennent des en-tetes de
    groupe plutot que des colonnes repetees sur chaque ligne.
    """
    regions = {}
    order_regions = []
    for row in rows:
        region_key = row.get("region") or "-"
        district_key = row.get("district") or "-"
        commune_key = row.get("commune") or "-"

        if region_key not in regions:
            regions[region_key] = {"districts": {}, "order_districts": []}
            order_regions.append(region_key)
        region_bucket = regions[region_key]

        if district_key not in region_bucket["districts"]:
            region_bucket["districts"][district_key] = {"communes": {}, "order_communes": []}
            region_bucket["order_districts"].append(district_key)
        district_bucket = region_bucket["districts"][district_key]

        if commune_key not in district_bucket["communes"]:
            district_bucket["communes"][commune_key] = []
            district_bucket["order_communes"].append(commune_key)
        district_bucket["communes"][commune_key].append(row)

    grouped = []
    for region_key in sorted(order_regions, key=lambda k: k.lower()):
        region_bucket = regions[region_key]
        districts = []
        region_count = 0
        region_habitants = 0
        for district_key in sorted(region_bucket["order_districts"], key=lambda k: k.lower()):
            district_bucket = region_bucket["districts"][district_key]
            communes = []
            district_count = 0
            district_habitants = 0
            for commune_key in sorted(district_bucket["order_communes"], key=lambda k: k.lower()):
                commune_rows = district_bucket["communes"][commune_key]
                commune_rows.sort(key=lambda item: (-item["habitants"], item["village"].lower()))
                commune_count = len(commune_rows)
                commune_habitants = sum(r["habitants"] for r in commune_rows)
                communes.append({
                    "nom": commune_key,
                    "count": commune_count,
                    "habitants": commune_habitants,
                    "rows": commune_rows,
                })
                district_count += commune_count
                district_habitants += commune_habitants
            districts.append({
                "nom": district_key,
                "count": district_count,
                "habitants": district_habitants,
                "communes": communes,
            })
            region_count += district_count
            region_habitants += district_habitants
        grouped.append({
            "nom": region_key,
            "count": region_count,
            "habitants": region_habitants,
            "districts": districts,
        })
    return grouped


def _compute_analyse_villages_desserte_context(request):
    """Calcule le contexte complet de la page d'analyse villages desserte.

    Factorise pour etre reutilise par la vue de rendu HTML et par l'export Excel,
    afin que l'export reflete exactement les memes filtres / la meme case
    selectionnee que ce qui est affiche a l'ecran.
    """
    today = timezone.localdate()
    region_id = _normalize_filter_value(request.GET.get("region"))
    district_id = _get_district_param(request)
    commune_id = _get_commune_param(request)
    fokontany_id = _normalize_filter_value(request.GET.get("fokontany"))
    selected_detail_key = (request.GET.get("detail") or "").strip()

    villages_qs = Village.objects.select_related(
        "fokontany",
        "fokontany__commune",
        "fokontany__commune__district",
        "fokontany__commune__district__region",
    )
    villages_qs = _apply_geo_filters(
        villages_qs,
        region_id=region_id,
        district_id=district_id,
        commune_id=commune_id,
        fokontany_id=fokontany_id,
    ).order_by("nom_village")

    village_rows = list(
        villages_qs.values(
            "id",
            "nom_village",
            "fokontany__nom_fokontany",
            "fokontany__commune__nom_commune",
            "fokontany__commune__district__nom_district",
            "fokontany__commune__district__region__nom_region",
        )
    )
    all_village_ids = {str(row["id"]) for row in village_rows}
    village_names = {str(row["id"]): row["nom_village"] for row in village_rows}
    village_stats = {
        str(row["id"]): _make_empty_village_stat(row)
        for row in village_rows
    }

    habitants_by_village = {
        str(row["village_id"]): int(row["total"] or 0)
        for row in Parcelle.objects.filter(
            village_id__in=all_village_ids,
        ).values(
            "village_id",
        ).annotate(
            total=Sum("nombre_habitants"),
        )
    }
    for village_id, habitants in habitants_by_village.items():
        if village_id in village_stats:
            village_stats[village_id]["habitants"] = habitants

    point_rows = PointEau.objects.filter(
        parcelle__village_id__in=all_village_ids,
        datebranchement__isnull=False,
    ).exclude(
        parcelle__village_id__isnull=True,
    ).values(
        "parcelle__village_id",
        "ouvrage_id",
        "datearretbranchement",
    )
    for row in point_rows:
        village_id = str(row["parcelle__village_id"])
        stat = village_stats.get(village_id)
        if not stat:
            continue
        stat["has_served"] = True
        stat["points_served_count"] += 1
        ouvrage_id = row.get("ouvrage_id")
        if ouvrage_id:
            stat["served_ouvrage_ids"].add(str(ouvrage_id))
        if row.get("datearretbranchement") is None:
            stat["has_functional"] = True
            stat["points_functional_count"] += 1
            if ouvrage_id:
                stat["functional_ouvrage_ids"].add(str(ouvrage_id))

    demand_rows = DemandeVillage.objects.filter(
        village_id__in=all_village_ids,
    ).values(
        "village_id",
        "statut",
    ).annotate(
        total=Count("id"),
    )
    for row in demand_rows:
        village_id = str(row["village_id"])
        stat = village_stats.get(village_id)
        if not stat:
            continue
        statut = row["statut"]
        total = int(row["total"] or 0)
        stat["demande_count"] += total
        stat["demande_status_counts"][statut] += total
        stat["demande_status_labels"].add(DEMANDE_STATUS_LABELS.get(statut, statut))

    dysfunctional_ouvrages = _dysfunctional_ouvrage_ids(
        {o for stat in village_stats.values() for o in stat["served_ouvrage_ids"]})
    for stat in village_stats.values():
        stat["has_functional"] = _village_is_functional(
            stat["has_served"], stat["served_ouvrage_ids"], dysfunctional_ouvrages)
    served_ids = {village_id for village_id, stat in village_stats.items() if stat["has_served"]}
    functional_ids = {village_id for village_id, stat in village_stats.items() if stat["has_functional"]}
    requested_ids = {village_id for village_id, stat in village_stats.items() if stat["demande_count"] > 0}

    summary = _summarize_village_desserte(
        all_village_ids,
        served_ids,
        functional_ids,
        requested_ids,
    )

    all_served_ouvrage_ids = {
        ouvrage_id
        for stat in village_stats.values()
        for ouvrage_id in stat["served_ouvrage_ids"]
    }
    managed_modalites_by_ouvrage = {}
    if all_served_ouvrage_ids:
        active_modalites = ModaliteGestion.objects.filter(
            ouvrage_id__in=all_served_ouvrage_ids,
            statut="actif",
            date_debut__lte=today,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=today)
        ).select_related("gestionnaire")

        temp_modalites = {}
        for modalite in active_modalites:
            if modalite.type_gestion == "pas_de_gestion":
                continue
            ouvrage_key = str(modalite.ouvrage_id)
            temp_modalites.setdefault(ouvrage_key, []).append(
                {
                    "org_key": str(modalite.gestionnaire_id) if modalite.gestionnaire_id else "none",
                    "org_label": (
                        modalite.gestionnaire.nom_organisation
                        if modalite.gestionnaire_id
                        else "Gestionnaire non renseigne"
                    ),
                    "type_gestion_label": TYPE_GESTION_LABELS.get(modalite.type_gestion, modalite.type_gestion),
                    "modalite_paiement_label": MODALITE_PAIEMENT_LABELS.get(
                        modalite.modalitepaiement,
                        modalite.modalitepaiement or "Non specifie",
                    ),
                }
            )
        managed_modalites_by_ouvrage = temp_modalites

    for stat in village_stats.values():
        if not stat["served_ouvrage_ids"]:
            continue
        org_counter = Counter()
        org_labels = {}
        for ouvrage_id in stat["served_ouvrage_ids"]:
            for modalite in managed_modalites_by_ouvrage.get(str(ouvrage_id), []):
                stat["has_management_modalite"] = True
                stat["management_org_labels"].add(modalite["org_label"])
                stat["management_org_ids"].add(modalite["org_key"])
                stat["management_type_labels"].add(modalite["type_gestion_label"])
                stat["management_payment_labels"].add(modalite["modalite_paiement_label"])
                org_counter[modalite["org_key"]] += 1
                org_labels[modalite["org_key"]] = modalite["org_label"]
        if org_counter:
            primary_org_key = sorted(
                org_counter.items(),
                key=lambda item: (-item[1], org_labels[item[0]].lower()),
            )[0][0]
            stat["primary_org_key"] = primary_org_key
            stat["primary_org_label"] = org_labels[primary_org_key]

    with_management_ids = {
        village_id
        for village_id, stat in village_stats.items()
        if stat["has_management_modalite"]
    }
    functional_with_any_modalite_ids = summary["functional_ids"] & with_management_ids
    functional_none_ids = summary["functional_ids"] - with_management_ids
    non_functional_with_any_modalite_ids = summary["non_functional_ids"] & with_management_ids
    non_functional_none_ids = summary["non_functional_ids"] - with_management_ids

    user_organisation = get_user_organisation(request.user)
    user_org_id = str(user_organisation.id) if user_organisation else ""
    user_org_label = user_organisation.nom_organisation if user_organisation else ""

    # Sépare les villages ayant au moins une modalite active entre ceux geres par
    # l'organisation connectee et ceux geres uniquement par une (ou plusieurs) autre(s)
    # organisation(s). Quand l'organisation connectee est connue, on obtient 3 cases au
    # meme niveau : geree par nous / geree par une autre organisation / pas de gestion —
    # ce qui rend inutile l'ancienne case intermediaire « organisation gestionnaire »
    # (le nom de l'organisation est directement dans le libelle de la case).
    functional_own_other = _own_other_org_split(functional_with_any_modalite_ids, village_stats, user_org_id)
    non_functional_own_other = _own_other_org_split(
        non_functional_with_any_modalite_ids, village_stats, user_org_id)
    if functional_own_other:
        functional_own_ids, functional_other_org_ids = functional_own_other
    else:
        functional_own_ids, functional_other_org_ids = set(), set()
    if non_functional_own_other:
        non_functional_own_ids, non_functional_other_org_ids = non_functional_own_other
    else:
        non_functional_own_ids, non_functional_other_org_ids = set(), set()

    # Sans organisation connectee (ex. superuser), « avec modalite » reste une case unique
    # regroupant toutes les organisations confondues (plus de detail par organisation :
    # l'ancienne case « organisation gestionnaire » est definitivement supprimee).
    functional_with_management_ids = functional_own_ids if user_org_id else functional_with_any_modalite_ids
    functional_without_management_ids = functional_none_ids
    non_functional_with_management_ids = non_functional_own_ids if user_org_id else non_functional_with_any_modalite_ids
    non_functional_without_management_ids = non_functional_none_ids

    total_habitants = _sum_habitants(summary["all_ids"], habitants_by_village)
    served_habitants = _sum_habitants(summary["served_ids"], habitants_by_village)
    non_served_habitants = _sum_habitants(summary["non_served_ids"], habitants_by_village)
    functional_habitants = _sum_habitants(summary["functional_ids"], habitants_by_village)
    non_functional_habitants = _sum_habitants(summary["non_functional_ids"], habitants_by_village)
    requested_habitants = _sum_habitants(summary["requested_ids"], habitants_by_village)
    without_request_habitants = _sum_habitants(summary["without_request_ids"], habitants_by_village)
    functional_with_management_habitants = _sum_habitants(functional_with_management_ids, habitants_by_village)
    functional_without_management_habitants = _sum_habitants(functional_without_management_ids, habitants_by_village)
    non_functional_with_management_habitants = _sum_habitants(non_functional_with_management_ids, habitants_by_village)
    non_functional_without_management_habitants = _sum_habitants(non_functional_without_management_ids, habitants_by_village)

    detail_registry = {}
    filter_params = {
        "region": region_id,
        "district": district_id,
        "commune": commune_id,
        "fokontany": fokontany_id,
    }
    base_url = reverse("core:analyse_villages_desserte")

    tree_root = _build_segment_node(
        key="total",
        title="Villages",
        level_label="Niveau 1",
        village_ids=summary["all_ids"],
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"] or 1,
        parent_habitants=total_habitants or 1,
        tone="root",
        icon_class="fas fa-house-user",
        subtitle="Base de calcul du diagramme",
    )

    served_node = _build_segment_node(
        key="served",
        title="Villages desservis",
        level_label="Niveau 2",
        village_ids=summary["served_ids"],
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="success",
        icon_class="fas fa-water",
        subtitle="Au moins un point d eau deja branche",
    )
    non_served_node = _build_segment_node(
        key="non_served",
        title="Villages non desservis",
        level_label="Niveau 2",
        village_ids=summary["non_served_ids"],
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="warning",
        icon_class="fas fa-ban",
        subtitle="Aucun point d eau branche",
    )
    tree_root["children"] = [served_node, non_served_node]

    functional_node = _build_segment_node(
        key="functional",
        title="Ouvrages fonctionnels",
        level_label="Niveau 3",
        village_ids=summary["functional_ids"],
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="info",
        icon_class="fas fa-check-circle",
        subtitle="Au moins un point encore en eau",
    )
    non_functional_node = _build_segment_node(
        key="non_functional",
        title="Ouvrages dysfonctionnels",
        level_label="Niveau 3",
        village_ids=summary["non_functional_ids"],
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="error",
        icon_class="fas fa-triangle-exclamation",
        subtitle="Villages desservis mais sans point encore en eau",
    )
    served_node["children"] = [functional_node, non_functional_node]

    requested_node = _build_segment_node(
        key="requested",
        title="Avec demande deposee",
        level_label="Niveau 3",
        village_ids=summary["requested_ids"],
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="secondary",
        icon_class="fas fa-file-signature",
        subtitle="Au moins une DemandeVillage",
    )
    without_request_node = _build_segment_node(
        key="without_request",
        title="Sans demande",
        level_label="Niveau 3",
        village_ids=summary["without_request_ids"],
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="base",
        icon_class="fas fa-folder-open",
        subtitle="Aucun suivi chantier enregistre",
    )
    non_served_node["children"] = [requested_node, without_request_node]

    title_with_mgmt = f"Geree par {user_org_label}" if user_org_id and user_org_label else "Avec modalite de gestion"
    subtitle_with_mgmt = (
        f"Modalite active de {user_org_label}" if user_org_id and user_org_label
        else "Modalite active de gestion sur un ouvrage du village"
    )
    functional_with_management_node = _build_segment_node(
        key="functional_with_management",
        title=title_with_mgmt,
        level_label="Niveau 4",
        village_ids=functional_with_management_ids,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="success",
        icon_class="fas fa-building-flag",
        subtitle=subtitle_with_mgmt,
    )
    functional_without_management_node = _build_segment_node(
        key="functional_without_management",
        title="Pas de gestion",
        level_label="Niveau 4",
        village_ids=functional_without_management_ids,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="warning",
        icon_class="fas fa-unlink",
        subtitle="Aucune organisation n a de modalite active sur ce village",
    )
    functional_other_management_node = None
    if user_org_id:
        functional_other_management_node = _build_segment_node(
            key="functional_other_management",
            title="Geree par une autre organisation",
            level_label="Niveau 4",
            village_ids=functional_other_org_ids,
            habitants_by_village=habitants_by_village,
            village_names=village_names,
            base_url=base_url,
            filter_params=filter_params,
            detail_registry=detail_registry,
            parent_count=summary["total_count"],
            parent_habitants=total_habitants,
            tone="info",
            icon_class="fas fa-building-circle-exclamation",
            subtitle="Modalite active, mais pas de l organisation connectee",
        )
    functional_node["children"] = [
        node for node in (
            functional_with_management_node,
            functional_other_management_node,
            functional_without_management_node,
        ) if node is not None
    ]

    non_functional_with_management_node = _build_segment_node(
        key="non_functional_with_management",
        title=title_with_mgmt,
        level_label="Niveau 4",
        village_ids=non_functional_with_management_ids,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="secondary",
        icon_class="fas fa-building-flag",
        subtitle=subtitle_with_mgmt,
    )
    non_functional_without_management_node = _build_segment_node(
        key="non_functional_without_management",
        title="Pas de gestion",
        level_label="Niveau 4",
        village_ids=non_functional_without_management_ids,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"],
        parent_habitants=total_habitants,
        tone="base",
        icon_class="fas fa-unlink",
        subtitle="Aucune organisation n a de modalite active sur ce village",
    )
    non_functional_other_management_node = None
    if user_org_id:
        non_functional_other_management_node = _build_segment_node(
            key="non_functional_other_management",
            title="Geree par une autre organisation",
            level_label="Niveau 4",
            village_ids=non_functional_other_org_ids,
            habitants_by_village=habitants_by_village,
            village_names=village_names,
            base_url=base_url,
            filter_params=filter_params,
            detail_registry=detail_registry,
            parent_count=summary["total_count"],
            parent_habitants=total_habitants,
            tone="secondary",
            icon_class="fas fa-building-circle-exclamation",
            subtitle="Modalite active, mais pas de l organisation connectee",
        )
    non_functional_node["children"] = [
        node for node in (
            non_functional_with_management_node,
            non_functional_other_management_node,
            non_functional_without_management_node,
        ) if node is not None
    ]

    # Villages desservis mais non fonctionnels : avec / sans demande (DemandeVillage,
    # la même liste que /chantiers/demandes/). Segments de détail, hors arbre :
    # l'arbre partitionne déjà ces villages par modalité de gestion.
    non_functional_requested_ids = summary["non_functional_ids"] & {str(v) for v in requested_ids}
    non_functional_without_request_ids = summary["non_functional_ids"] - non_functional_requested_ids
    non_functional_requested_habitants = _sum_habitants(non_functional_requested_ids, habitants_by_village)
    non_functional_without_request_habitants = _sum_habitants(
        non_functional_without_request_ids, habitants_by_village)
    for seg_key, seg_title, seg_ids, seg_tone, seg_icon, seg_subtitle in (
        ("non_functional_requested", "Dysfonctionnels avec demande",
         non_functional_requested_ids, "secondary", "fas fa-file-signature",
         "Villages desservis sans point en eau, avec au moins une DemandeVillage"),
        ("non_functional_without_request", "Dysfonctionnels sans demande",
         non_functional_without_request_ids, "base", "fas fa-folder-open",
         "Villages desservis sans point en eau, sans aucune demande"),
    ):
        _build_segment_node(
            key=seg_key, title=seg_title, level_label="Detail", village_ids=seg_ids,
            habitants_by_village=habitants_by_village, village_names=village_names,
            base_url=base_url, filter_params=filter_params, detail_registry=detail_registry,
            parent_count=summary["non_functional_count"] or 1,
            parent_habitants=non_functional_habitants or 1,
            tone=seg_tone, icon_class=seg_icon, subtitle=seg_subtitle,
        )

    selected_detail = detail_registry.get(selected_detail_key)
    if not selected_detail and summary["total_count"]:
        selected_detail_key = "total"
        selected_detail = detail_registry.get(selected_detail_key)

    detail_rows = []
    if selected_detail:
        detail_rows = _build_detail_rows(selected_detail["village_ids"], village_stats)

    demand_status_counter = Counter()
    for village_id in summary["non_served_ids"]:
        stat = village_stats.get(village_id)
        if not stat:
            continue
        for statut, total in stat["demande_status_counts"].items():
            demand_status_counter[statut] += total

    demand_status_rows = [
        {
            "statut": statut,
            "label": DEMANDE_STATUS_LABELS.get(statut, statut),
            "total": total,
        }
        for statut, total in sorted(
            demand_status_counter.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    total_demandes_non_desservis = sum(row["total"] for row in demand_status_rows)

    regions = Region.objects.all().order_by("nom_region")

    districts = _geo_children(District, region_id, district_id, commune_id).order_by("nom_district")
    # Listes complètes dans la région / le district choisi (on peut cocher d'autres communes)
    communes = _geo_children(Commune, region_id, district_id, commune_id).order_by("nom_commune")

    fokontanys = _geo_children(Fokontany, region_id, district_id, commune_id).order_by("nom_fokontany")

    selected_region = Region.objects.filter(id=region_id).first() if region_id else None
    selected_district = list(District.objects.filter(id__in=_split_ids(district_id)).order_by("nom_district")) if district_id else None
    selected_commune = list(Commune.objects.filter(id__in=_split_ids(commune_id)).order_by("nom_commune")) if commune_id else None
    selected_fokontany = Fokontany.objects.filter(id=fokontany_id).first() if fokontany_id else None

    context = {
        "title": "Diagramme villages : desserte et suivi",
        "reference_date": today,
        "scope_label": _build_scope_label(
            region=selected_region,
            district=selected_district,
            commune=selected_commune,
            fokontany=selected_fokontany,
        ),
        "summary": {
            **summary,
            "habitants_total": total_habitants,
            "habitants_served": served_habitants,
            "habitants_non_served": non_served_habitants,
            "habitants_functional": functional_habitants,
            "habitants_non_functional": non_functional_habitants,
            "habitants_requested": requested_habitants,
            "habitants_without_request": without_request_habitants,
            "functional_pct_total": _percentage(summary["functional_count"], summary["total_count"]),
            "non_functional_pct_total": _percentage(summary["non_functional_count"], summary["total_count"]),
            "requested_pct_total": _percentage(summary["requested_count"], summary["total_count"]),
            "without_request_pct_total": _percentage(summary["without_request_count"], summary["total_count"]),
            "habitants_served_pct_total": _percentage(served_habitants, total_habitants),
            "habitants_non_served_pct_total": _percentage(non_served_habitants, total_habitants),
            "habitants_functional_pct_served": _percentage(functional_habitants, served_habitants),
            "habitants_non_functional_pct_served": _percentage(non_functional_habitants, served_habitants),
            "habitants_requested_pct_non_served": _percentage(requested_habitants, non_served_habitants),
            "habitants_without_request_pct_non_served": _percentage(without_request_habitants, non_served_habitants),
            "habitants_functional_pct_total": _percentage(functional_habitants, total_habitants),
            "habitants_non_functional_pct_total": _percentage(non_functional_habitants, total_habitants),
            "habitants_requested_pct_total": _percentage(requested_habitants, total_habitants),
            "habitants_without_request_pct_total": _percentage(without_request_habitants, total_habitants),
            "non_functional_requested_count": len(non_functional_requested_ids),
            "non_functional_without_request_count": len(non_functional_without_request_ids),
            "habitants_non_functional_requested": non_functional_requested_habitants,
            "habitants_non_functional_without_request": non_functional_without_request_habitants,
            "functional_with_management_count": len(functional_with_management_ids),
            "functional_without_management_count": len(functional_without_management_ids),
            "non_functional_with_management_count": len(non_functional_with_management_ids),
            "non_functional_without_management_count": len(non_functional_without_management_ids),
            "functional_with_management_pct_total": _percentage(
                len(functional_with_management_ids),
                summary["total_count"],
            ),
            "functional_without_management_pct_total": _percentage(
                len(functional_without_management_ids),
                summary["total_count"],
            ),
            "non_functional_with_management_pct_total": _percentage(
                len(non_functional_with_management_ids),
                summary["total_count"],
            ),
            "non_functional_without_management_pct_total": _percentage(
                len(non_functional_without_management_ids),
                summary["total_count"],
            ),
            "functional_with_management_pct_functional": _percentage(
                len(functional_with_management_ids),
                summary["functional_count"],
            ),
            "functional_without_management_pct_functional": _percentage(
                len(functional_without_management_ids),
                summary["functional_count"],
            ),
            "non_functional_with_management_pct_non_functional": _percentage(
                len(non_functional_with_management_ids),
                summary["non_functional_count"],
            ),
            "non_functional_without_management_pct_non_functional": _percentage(
                len(non_functional_without_management_ids),
                summary["non_functional_count"],
            ),
            "habitants_functional_with_management": functional_with_management_habitants,
            "habitants_functional_without_management": functional_without_management_habitants,
            "habitants_non_functional_with_management": non_functional_with_management_habitants,
            "habitants_non_functional_without_management": non_functional_without_management_habitants,
            "habitants_functional_with_management_pct_total": _percentage(
                functional_with_management_habitants,
                total_habitants,
            ),
            "habitants_functional_without_management_pct_total": _percentage(
                functional_without_management_habitants,
                total_habitants,
            ),
            "habitants_non_functional_with_management_pct_total": _percentage(
                non_functional_with_management_habitants,
                total_habitants,
            ),
            "habitants_non_functional_without_management_pct_total": _percentage(
                non_functional_without_management_habitants,
                total_habitants,
            ),
            "habitants_functional_with_management_pct_functional": _percentage(
                functional_with_management_habitants,
                functional_habitants,
            ),
            "habitants_functional_without_management_pct_functional": _percentage(
                functional_without_management_habitants,
                functional_habitants,
            ),
            "habitants_non_functional_with_management_pct_non_functional": _percentage(
                non_functional_with_management_habitants,
                non_functional_habitants,
            ),
            "habitants_non_functional_without_management_pct_non_functional": _percentage(
                non_functional_without_management_habitants,
                non_functional_habitants,
            ),
        },
        "tree_root": tree_root,
        "detail_urls": {
            "total": _build_detail_url(base_url, filter_params, "total"),
            "served": _build_detail_url(base_url, filter_params, "served"),
            "functional": _build_detail_url(base_url, filter_params, "functional"),
            "requested": _build_detail_url(base_url, filter_params, "requested"),
            "without_request": _build_detail_url(base_url, filter_params, "without_request"),
            "non_functional_requested": _build_detail_url(base_url, filter_params, "non_functional_requested"),
            "non_functional_without_request": _build_detail_url(
                base_url, filter_params, "non_functional_without_request"),
        },
        "selected_detail_key": selected_detail_key,
        "selected_detail": selected_detail,
        "detail_rows": detail_rows,
        "detail_rows_grouped": _group_detail_rows_by_geo(detail_rows),
        "demand_status_rows": demand_status_rows,
        "total_demandes_non_desservis": total_demandes_non_desservis,
        "regions": regions,
        "districts": districts,
        "communes": communes,
        "fokontanys": fokontanys,
        "region_id": region_id,
        "district_id": district_id,
        "commune_id": commune_id,
        "selected_commune_ids": _split_ids(commune_id),
        "selected_district_ids": _split_ids(district_id),
        "fokontany_id": fokontany_id,
        "filtres_sauvegardes_data": [
            {"id": str(f.id), "nom": f.nom, "parametres": f.parametres}
            for f in FiltreSauvegarde.objects.filter(page_key="villages_desserte").order_by("nom")
        ],
    }
    return context


@login_required
def analyse_villages_desserte(request):
    context = _compute_analyse_villages_desserte_context(request)
    return render(request, "core/analyse_villages_desserte.html", context)


@login_required
def analyse_villages_desserte_export_excel(request):
    """
    Export Excel du tableau "Details" de la page analyse villages desserte,
    avec les memes filtres / la meme case selectionnee que ce qui est affiche
    a l'ecran. Les villages sont regroupes par Region > District > Commune
    (en-tetes de groupe), ces colonnes ne sont donc pas repetees sur chaque ligne.
    """
    context = _compute_analyse_villages_desserte_context(request)
    selected_detail = context.get("selected_detail")
    grouped_regions = context.get("detail_rows_grouped") or []

    columns = [
        ("village", "Village", 30),
        ("fokontany", "Fokontany", 22),
        ("habitants", "Habitants", 12),
        ("desserte_label", "Desserte", 14),
        ("fonctionnalite_label", "Fonctionnalite", 16),
        ("points_served_count", "Points", 10),
        ("points_functional_count", "Points en eau", 14),
        ("demande_count", "Demandes", 12),
        ("has_management_modalite", "Modalite", 10),
        ("management_types", "Types gestion", 22),
        ("management_payments", "Paiement", 20),
        ("management_primary_org", "Gestionnaire principal", 26),
    ]
    nb_cols = len(columns)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Villages desserte"

    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    region_font = Font(bold=True, size=12, color="FFFFFF")
    region_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    district_font = Font(bold=True, size=11, color="FFFFFF")
    district_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    commune_font = Font(bold=True, size=10)
    commune_fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")

    title_text = f"Villages - {selected_detail['title']}" if selected_detail else "Villages"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=nb_cols)
    title_cell = ws.cell(row=1, column=1, value=title_text)
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal="left", vertical="center")

    row_idx = 3
    for col_idx, (_key, label, _width) in enumerate(columns, start=1):
        cell = ws.cell(row=row_idx, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
    ws.freeze_panes = f"A{row_idx + 1}"
    row_idx += 1

    for region in grouped_regions:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=nb_cols)
        cell = ws.cell(
            row=row_idx, column=1,
            value=f"Region : {region['nom']} ({region['count']} village{'s' if region['count'] != 1 else ''}, {region['habitants']} habitants)",
        )
        cell.font = region_font
        cell.fill = region_fill
        cell.alignment = Alignment(horizontal="left", vertical="center")
        row_idx += 1

        for district in region["districts"]:
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=nb_cols)
            cell = ws.cell(
                row=row_idx, column=1,
                value=f"District : {district['nom']} ({district['count']} village{'s' if district['count'] != 1 else ''}, {district['habitants']} habitants)",
            )
            cell.font = district_font
            cell.fill = district_fill
            cell.alignment = Alignment(horizontal="left", vertical="center")
            row_idx += 1

            for commune in district["communes"]:
                ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=nb_cols)
                cell = ws.cell(
                    row=row_idx, column=1,
                    value=f"Commune : {commune['nom']} ({commune['count']} village{'s' if commune['count'] != 1 else ''}, {commune['habitants']} habitants)",
                )
                cell.font = commune_font
                cell.fill = commune_fill
                cell.alignment = Alignment(horizontal="left", vertical="center")
                row_idx += 1

                for village_row in commune["rows"]:
                    for col_idx, (key, _label, _width) in enumerate(columns, start=1):
                        value = village_row.get(key, "")
                        cell = ws.cell(row=row_idx, column=col_idx, value=value)
                        cell.border = thin_border
                        if key in ("habitants", "points_served_count", "points_functional_count", "demande_count"):
                            cell.alignment = Alignment(horizontal="right")
                    row_idx += 1

    for col_idx, (_key, _label, width) in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    filename = f"Villages_desserte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def analyse_villages_desserte_json(request):
    """
    API JSON pour le graphique camembert interactif
    Retourne la structure hiérarchique des villages en JSON
    """
    # Récupérer les filtres depuis la requête
    region_id = _normalize_filter_value(request.GET.get("region"))
    district_id = _get_district_param(request)
    commune_id = _get_commune_param(request)
    fokontany_id = _normalize_filter_value(request.GET.get("fokontany"))

    # Construire les paramètres de filtre
    filter_params = {
        "region": region_id,
        "district": district_id,
        "commune": commune_id,
        "fokontany": fokontany_id,
    }

    # Base URL pour les liens de détails
    base_url = request.build_absolute_uri(reverse("core:analyse_villages_desserte"))

    # Récupérer tous les villages avec filtres géographiques appliqués
    villages_qs = Village.objects.all()
    villages_qs = _apply_geo_filters(villages_qs, region_id, district_id, commune_id, fokontany_id)

    village_rows = list(
        villages_qs.values(
            "id",
            "nom_village",
        )
    )
    all_village_ids = {str(row["id"]) for row in village_rows}
    village_names = {str(row["id"]): row["nom_village"] for row in village_rows}

    # Habitants par village
    habitants_by_village = {
        str(row["village_id"]): int(row["total"] or 0)
        for row in Parcelle.objects.filter(
            village_id__in=all_village_ids,
        ).values(
            "village_id",
        ).annotate(
            total=Sum("nombre_habitants"),
        )
    }

    # Villages desservis (avec au moins un point d'eau branché)
    point_rows = PointEau.objects.filter(
        parcelle__village_id__in=all_village_ids,
        datebranchement__isnull=False,
    ).exclude(
        parcelle__village_id__isnull=True,
    ).values(
        "parcelle__village_id",
        "ouvrage_id",
    )

    served_ids = set()
    ouvrages_by_village = {}
    for row in point_rows:
        village_id = str(row["parcelle__village_id"])
        served_ids.add(village_id)
        if row.get("ouvrage_id"):
            ouvrages_by_village.setdefault(village_id, set()).add(str(row["ouvrage_id"]))
    dysfunctional_ouvrages = _dysfunctional_ouvrage_ids(
        {o for ids in ouvrages_by_village.values() for o in ids})
    functional_ids = {
        v for v in served_ids
        if _village_is_functional(True, ouvrages_by_village.get(v, set()), dysfunctional_ouvrages)
    }

    # Villages avec demande
    demand_rows = DemandeVillage.objects.filter(
        village_id__in=all_village_ids,
    ).values_list("village_id", flat=True).distinct()
    requested_ids = {str(village_id) for village_id in demand_rows}

    # Résumé avec intersections
    summary = _summarize_village_desserte(
        all_village_ids,
        served_ids,
        functional_ids,
        requested_ids,
    )

    # Total habitants
    total_habitants = _sum_habitants(summary["all_ids"], habitants_by_village)

    # Registry pour les détails
    detail_registry = {}

    # Construire l'arbre complet (réutilise la logique existante)
    tree_root = _build_segment_node(
        key="total",
        title="Tous les villages",
        level_label="Niveau 1",
        village_ids=summary["all_ids"],
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"] or 1,
        parent_habitants=total_habitants or 1,
        tone="root",
        icon_class="fas fa-house-user",
        subtitle="Base de calcul",
    )

    # Niveau 2: Servis vs Non servis
    served_ids_set = summary["served_ids"]
    served_count = len(served_ids_set)
    served_habitants = _sum_habitants(served_ids_set, habitants_by_village)

    served_node = _build_segment_node(
        key="served",
        title="Villages desservis",
        level_label="Niveau 2",
        village_ids=served_ids_set,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"] or 1,
        parent_habitants=total_habitants or 1,
        tone="success",
        icon_class="fas fa-check-circle",
    )

    non_served_ids_set = summary["non_served_ids"]
    non_served_count = len(non_served_ids_set)
    non_served_habitants = _sum_habitants(non_served_ids_set, habitants_by_village)

    non_served_node = _build_segment_node(
        key="non_served",
        title="Villages non desservis",
        level_label="Niveau 2",
        village_ids=non_served_ids_set,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=summary["total_count"] or 1,
        parent_habitants=total_habitants or 1,
        tone="warning",
        icon_class="fas fa-times-circle",
    )

    tree_root["children"] = [served_node, non_served_node]

    # Niveau 3 sous "servis": Fonctionnels vs Non fonctionnels
    functional_ids_set = summary["functional_ids"]
    functional_node = _build_segment_node(
        key="functional",
        title="Ouvrages fonctionnels",
        level_label="Niveau 3",
        village_ids=functional_ids_set,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=served_count or 1,
        parent_habitants=served_habitants or 1,
        tone="info",
        icon_class="fas fa-tools",
    )

    non_functional_ids_set = summary["non_functional_ids"]
    non_functional_node = _build_segment_node(
        key="non_functional",
        title="Ouvrages dysfonctionnels",
        level_label="Niveau 3",
        village_ids=non_functional_ids_set,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=served_count or 1,
        parent_habitants=served_habitants or 1,
        tone="error",
        icon_class="fas fa-exclamation-triangle",
    )

    served_node["children"] = [functional_node, non_functional_node]

    # Niveau 3 sous "non servis": Demandés vs Sans demande
    requested_ids_set = summary["requested_ids"]
    requested_node = _build_segment_node(
        key="requested",
        title="Villages avec demande",
        level_label="Niveau 3",
        village_ids=requested_ids_set,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=non_served_count or 1,
        parent_habitants=non_served_habitants or 1,
        tone="secondary",
        icon_class="fas fa-envelope",
    )

    without_request_ids_set = summary["without_request_ids"]
    without_request_node = _build_segment_node(
        key="without_request",
        title="Villages sans demande",
        level_label="Niveau 3",
        village_ids=without_request_ids_set,
        habitants_by_village=habitants_by_village,
        village_names=village_names,
        base_url=base_url,
        filter_params=filter_params,
        detail_registry=detail_registry,
        parent_count=non_served_count or 1,
        parent_habitants=non_served_habitants or 1,
        tone="base",
        icon_class="fas fa-minus-circle",
    )

    non_served_node["children"] = [requested_node, without_request_node]

    # Retourner la structure en JSON
    return JsonResponse({
        "success": True,
        "tree": tree_root,
        "summary": {
            "total_count": summary["total_count"],
            "total_habitants": total_habitants,
            "served_count": served_count,
            "non_served_count": non_served_count,
        }
    })


def _compute_village_flux(
    region_id, district_id, commune_id, fokontany_id, base_url,
    user_org_id="", user_org_label="",
):
    """
    Données du diagramme de flux (villages -> ... -> organisation -> ouvrages).

    Reprend les règles de la page (desservi / fonctionnel / demande / modalité
    active / organisation principale) puis prolonge chaque organisation vers les
    ouvrages qu'elle gère et qui desservent ses villages, classés comme dans le
    diagramme des ouvrages du widget (modalité -> factures non pointées ->
    réparations). Chaque ouvrage n'est rattaché qu'à une seule organisation
    (branche « fonctionnels » prioritaire).

    Quand `user_org_id` est connu, la case « avec modalite » de chaque branche
    (fonctionnels / dysfonctionnels) se scinde d'abord en « geree par
    [user_org_label] » / « geree par une autre organisation », puis le detail
    par organisation reste disponible sous cette seconde case.
    """
    from apps.core.views_widget import classify_ouvrages, _mois_facture_label

    today = timezone.localdate()
    filter_params = {
        "region": region_id, "district": district_id,
        "commune": commune_id, "fokontany": fokontany_id,
    }
    villages_qs = _apply_geo_filters(
        Village.objects.all(), region_id=region_id, district_id=district_id,
        commune_id=commune_id, fokontany_id=fokontany_id,
    ).order_by("nom_village")
    village_rows = list(villages_qs.values(
        "id", "nom_village", "fokontany__nom_fokontany", "fokontany__commune__nom_commune",
        "fokontany__commune__district__nom_district",
        "fokontany__commune__district__region__nom_region",
    ))
    all_village_ids = {str(row["id"]) for row in village_rows}
    village_names = {str(row["id"]): row["nom_village"] for row in village_rows}
    village_stats = {str(row["id"]): _make_empty_village_stat(row) for row in village_rows}

    habitants_by_village = {
        str(row["village_id"]): int(row["total"] or 0)
        for row in Parcelle.objects.filter(village_id__in=all_village_ids)
        .values("village_id").annotate(total=Sum("nombre_habitants"))
    }
    for village_id, habitants in habitants_by_village.items():
        if village_id in village_stats:
            village_stats[village_id]["habitants"] = habitants

    point_rows = PointEau.objects.filter(
        parcelle__village_id__in=all_village_ids, datebranchement__isnull=False,
    ).exclude(parcelle__village_id__isnull=True).values(
        "parcelle__village_id", "ouvrage_id", "datearretbranchement",
    )
    for row in point_rows:
        stat = village_stats.get(str(row["parcelle__village_id"]))
        if not stat:
            continue
        stat["has_served"] = True
        stat["points_served_count"] += 1
        ouvrage_id = row.get("ouvrage_id")
        if ouvrage_id:
            stat["served_ouvrage_ids"].add(str(ouvrage_id))
        if row.get("datearretbranchement") is None:
            stat["has_functional"] = True
            stat["points_functional_count"] += 1
            if ouvrage_id:
                stat["functional_ouvrage_ids"].add(str(ouvrage_id))

    for row in DemandeVillage.objects.filter(village_id__in=all_village_ids).values(
        "village_id", "statut",
    ).annotate(total=Count("id")):
        stat = village_stats.get(str(row["village_id"]))
        if not stat:
            continue
        total = int(row["total"] or 0)
        stat["demande_count"] += total
        stat["demande_status_counts"][row["statut"]] += total
        stat["demande_status_labels"].add(DEMANDE_STATUS_LABELS.get(row["statut"], row["statut"]))

    dysfunctional_ouvrages = _dysfunctional_ouvrage_ids(
        {o for s in village_stats.values() for o in s["served_ouvrage_ids"]})
    for s in village_stats.values():
        s["has_functional"] = _village_is_functional(
            s["has_served"], s["served_ouvrage_ids"], dysfunctional_ouvrages)
    served_ids = {v for v, s in village_stats.items() if s["has_served"]}
    functional_ids = {v for v, s in village_stats.items() if s["has_functional"]}
    requested_ids = {v for v, s in village_stats.items() if s["demande_count"] > 0}
    summary = _summarize_village_desserte(all_village_ids, served_ids, functional_ids, requested_ids)

    all_served_ouvrage_ids = {o for s in village_stats.values() for o in s["served_ouvrage_ids"]}
    modalites_by_ouvrage = {}
    if all_served_ouvrage_ids:
        active = ModaliteGestion.objects.filter(
            ouvrage_id__in=all_served_ouvrage_ids, statut="actif", date_debut__lte=today,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=today)).select_related("gestionnaire")
        for modalite in active:
            if modalite.type_gestion == "pas_de_gestion":
                continue
            modalites_by_ouvrage.setdefault(str(modalite.ouvrage_id), []).append({
                "org_key": str(modalite.gestionnaire_id) if modalite.gestionnaire_id else "none",
                "org_label": (modalite.gestionnaire.nom_organisation if modalite.gestionnaire_id
                              else "Gestionnaire non renseigne"),
                "type_gestion_label": TYPE_GESTION_LABELS.get(modalite.type_gestion, modalite.type_gestion),
                "modalite_paiement_code": modalite.modalitepaiement,
                "modalite_paiement_label": MODALITE_PAIEMENT_LABELS.get(
                    modalite.modalitepaiement, modalite.modalitepaiement or "Non specifie"),
            })

    for stat in village_stats.values():
        if not stat["served_ouvrage_ids"]:
            continue
        org_counter, org_labels = Counter(), {}
        for ouvrage_id in stat["served_ouvrage_ids"]:
            for m in modalites_by_ouvrage.get(str(ouvrage_id), []):
                stat["has_management_modalite"] = True
                stat["management_org_labels"].add(m["org_label"])
                stat["management_org_ids"].add(m["org_key"])
                stat["management_type_labels"].add(m["type_gestion_label"])
                stat["management_payment_labels"].add(m["modalite_paiement_label"])
                org_counter[m["org_key"]] += 1
                org_labels[m["org_key"]] = m["org_label"]
        if org_counter:
            key = sorted(org_counter.items(), key=lambda it: (-it[1], org_labels[it[0]].lower()))[0][0]
            stat["primary_org_key"], stat["primary_org_label"] = key, org_labels[key]

    with_mgmt = {v for v, s in village_stats.items() if s["has_management_modalite"]}
    f_with_any = summary["functional_ids"] & with_mgmt
    f_none = summary["functional_ids"] - with_mgmt
    nf_with_any = summary["non_functional_ids"] & with_mgmt
    nf_none = summary["non_functional_ids"] - with_mgmt

    # Comme dans l'arbre principal : quand l'organisation connectee est connue, on obtient 3
    # cases au meme niveau (geree par nous / geree par une autre organisation / pas de
    # gestion) au lieu de la case intermediaire « organisation gestionnaire ».
    f_own_other = _own_other_org_split(f_with_any, village_stats, user_org_id)
    f_own, f_other = f_own_other if f_own_other else (set(), set())
    f_with = f_own if user_org_id else f_with_any
    f_without = f_none
    nf_own_other = _own_other_org_split(nf_with_any, village_stats, user_org_id)
    nf_own, nf_other = nf_own_other if nf_own_other else (set(), set())
    nf_with = nf_own if user_org_id else nf_with_any
    nf_without = nf_none

    total_habitants = _sum_habitants(summary["all_ids"], habitants_by_village)
    served_habitants = _sum_habitants(summary["served_ids"], habitants_by_village)
    registry = {}

    def node(key, title, ids, tone, parent_ids=None):
        parent_ids = parent_ids if parent_ids is not None else summary["all_ids"]
        return _build_segment_node(
            key=key, title=title, level_label="", village_ids=ids,
            habitants_by_village=habitants_by_village, village_names=village_names,
            base_url=base_url, filter_params=filter_params, detail_registry=registry,
            parent_count=len(parent_ids) or 1,
            parent_habitants=_sum_habitants(parent_ids, habitants_by_village) or 1, tone=tone,
        )

    # Chantiers en cours (workflow non clôturé) rattachés aux villages par les points d'eau de l'ouvrage
    from apps.chantiers.models_workflow import ChantierWorkflow
    chantiers = []
    workflows = list(ChantierWorkflow.objects.exclude(statut="cloture").select_related("ouvrage"))
    if workflows:
        villages_by_ouvrage = {}
        for village_id, ouvrage_id in PointEau.objects.filter(
            ouvrage_id__in={w.ouvrage_id for w in workflows},
            parcelle__village_id__in=all_village_ids,
        ).values_list("parcelle__village_id", "ouvrage_id").distinct():
            villages_by_ouvrage.setdefault(ouvrage_id, set()).add(str(village_id))
        for w in workflows:
            vids = villages_by_ouvrage.get(w.ouvrage_id)
            if not vids:
                continue
            chantiers.append({
                "code": w.code,
                "o": w.ouvrage.nom_ouvrage,
                "t": w.get_type_travaux_display() if w.type_travaux else "",
                "s": w.get_statut_chantier_display(),
                "d": w.description or "",
                "v": sorted(village_names.get(v, "") for v in vids),
                "village_ids": vids,
            })
    chantier_ids = {v for c in chantiers for v in c["village_ids"]}

    root = node("total", "Villages", summary["all_ids"], "root")
    served = node("served", "Villages desservis", summary["served_ids"], "success")
    non_served = node("non_served", "Villages non desservis", summary["non_served_ids"], "warning")
    root["children"] = [served, non_served]
    functional = node("functional", "Ouvrages fonctionnels", summary["functional_ids"], "info")
    non_functional = node("non_functional", "Ouvrages dysfonctionnels", summary["non_functional_ids"], "error")
    served["children"] = [functional, non_functional]
    requested_node = node("requested", "Avec demande deposee", summary["requested_ids"], "secondary")
    without_request_node = node("without_request", "Sans demande", summary["without_request_ids"], "base")
    non_served["children"] = [requested_node, without_request_node]
    # Étape « chantier en cours » (construction / réhabilitation), après la demande
    for parent, prefix in ((requested_node, "requested"), (without_request_node, "without_request")):
        ids = parent["village_ids"] if "village_ids" in parent else registry[parent["key"]]["village_ids"]
        parent["children"] = [
            node(f"{prefix}_chantier", "Chantier en cours", ids & chantier_ids, "info", parent_ids=ids),
            node(f"{prefix}_sans_chantier", "Pas de chantier en cours", ids - chantier_ids, "base",
                 parent_ids=ids),
        ]
    title_with_mgmt = f"Geree par {user_org_label}" if user_org_id and user_org_label else "Avec modalite de gestion"
    f_with_node = node("functional_with_management", title_with_mgmt, f_with, "success")
    f_without_node = node("functional_without_management", "Pas de gestion", f_without, "warning")
    nf_with_node = node("non_functional_with_management", title_with_mgmt, nf_with, "secondary")
    nf_without_node = node("non_functional_without_management", "Pas de gestion", nf_without, "base")
    # Les cases « geree par une autre organisation » (si l'organisation connectee est
    # connue) sont ajoutees comme 3e sœur juste apres, une fois construites plus bas.

    # Organisations, puis prolongement vers les ouvrages gérés (un ouvrage = une seule organisation).
    assigned = set()
    org_nodes = []

    def _ouvrages_for(village_ids, org_key_check):
        found = set()
        for village_id in village_ids:
            for ouvrage_id in village_stats[village_id]["served_ouvrage_ids"]:
                if ouvrage_id in assigned:
                    continue
                if any(org_key_check(m["org_key"]) for m in modalites_by_ouvrage.get(ouvrage_id, [])):
                    found.add(ouvrage_id)
        return found

    # `f_with`/`nf_with` representent deja NOS villages uniquement (quand l'organisation
    # connectee est connue) : la case « avec modalite » (niveau 4) en herite directement,
    # sans sous-niveau, tout comme « pas de gestion » et « geree par une autre
    # organisation » qui deviennent des sœurs directes (plus de case intermediaire
    # « organisation gestionnaire »).
    for parent_node, management_node, without_node, with_ids, other_ids, prefix, tone_other in (
        (functional, f_with_node, f_without_node, f_with, f_other, "functional", "info"),
        (non_functional, nf_with_node, nf_without_node, nf_with, nf_other, "non_functional", "secondary"),
    ):
        own_ouvrages = _ouvrages_for(with_ids, (lambda k: k == user_org_id) if user_org_id else (lambda k: True))
        assigned |= own_ouvrages
        management_node["_ouvrages"] = own_ouvrages
        org_nodes.append(management_node)

        other_node = None
        if user_org_id:
            other_ouvrages = _ouvrages_for(other_ids, lambda k: k != user_org_id)
            other_node = node(f"{prefix}_other_management", "Geree par une autre organisation", other_ids, tone_other)
            assigned |= other_ouvrages
            other_node["_ouvrages"] = other_ouvrages
            org_nodes.append(other_node)

        parent_node["children"] = [
            n for n in (management_node, other_node, without_node) if n is not None
        ]

    classification = classify_ouvrages(assigned)
    # Ouvrages geres par une autre organisation que celle connectee : Hydria n'a pas
    # les donnees de facturation (tarifs/releves) de ces organisations tierces, donc
    # `classify_ouvrages` les classe systematiquement "sans_tarif". On recupere plutot
    # la modalite de paiement declaree dans ModaliteGestion.modalitepaiement.
    modalite_paiement_to_cat = {
        "forfaitaire": "forfait",
        "au_volume": "volume",
        "mixte": "mixte",
    }
    if user_org_id:
        for ouvrage_id, info in classification.items():
            if info.get("cat") != "sans_tarif":
                continue
            infos_gestion = modalites_by_ouvrage.get(ouvrage_id) or []
            if not infos_gestion:
                continue
            org_key = infos_gestion[0]["org_key"]
            if org_key == user_org_id:
                continue
            cat = modalite_paiement_to_cat.get(infos_gestion[0].get("modalite_paiement_code"))
            if cat:
                info["cat"] = cat
    ouvrage_names = dict(
        Ouvrage.objects.filter(id__in=assigned).values_list("id", "nom_ouvrage")
    ) if assigned else {}
    ouvrage_names = {str(k): v or "Ouvrage sans nom" for k, v in ouvrage_names.items()}
    for org_node in org_nodes:
        leaves = {}
        for ouvrage_id in org_node.pop("_ouvrages"):
            info = classification.get(ouvrage_id)
            if not info:
                continue
            key = (info["cat"], info["per"], info["avec"])
            leaf = leaves.setdefault(key, {
                "cat": info["cat"], "per": info["per"], "avec": info["avec"],
                "ouvrages": 0, "points": 0, "noms": [],
            })
            leaf["ouvrages"] += 1
            leaf["points"] += info["points"]
            leaf["noms"].append(ouvrage_names.get(ouvrage_id, ""))
        for leaf in leaves.values():
            leaf["noms"].sort(key=str.lower)
        org_node["ouvrage_stage"] = list(leaves.values())

    # Liste compacte des villages + indices par nœud (pour l'affichage des bulles).
    order = sorted(
        village_stats, key=lambda v: (
            village_stats[v]["region"], village_stats[v]["district"],
            village_stats[v]["commune"], village_stats[v]["nom_village"].lower()))
    index = {v: i for i, v in enumerate(order)}
    villages = []
    for v in order:
        s = village_stats[v]
        # Combinaisons (modalite de paiement, facture non pointee, reparation) des ouvrages
        # du village deja classes, pour permettre au front-end de prolonger le chemin de
        # recherche au-dela de l'organisation, jusqu'aux etapes ouvrages du diagramme flux.
        combos = set()
        for ouvrage_id in s["served_ouvrage_ids"]:
            info = classification.get(str(ouvrage_id))
            if info:
                combos.add(f"{info['cat']}|{info['per']}|{'1' if info['avec'] else '0'}")
        villages.append({
            "n": s["nom_village"], "r": s["region"], "d": s["district"], "c": s["commune"],
            "f": s["fokontany"], "h": s["habitants"],
            "s": 1 if s["has_served"] else 0, "fn": 1 if s["has_functional"] else 0,
            "ps": s["points_served_count"], "pf": s["points_functional_count"],
            "no": len(s["served_ouvrage_ids"]), "dm": s["demande_count"],
            "ds": _join_display(s["demande_status_labels"], ""),
            "mt": _join_display(s["management_type_labels"], ""),
            "mp": _join_display(s["management_payment_labels"], ""),
            "mo": _join_display(s["management_org_labels"], ""),
            "mc": sorted(combos),
        })
    ids_by_key = {key: sorted(index[v] for v in entry["village_ids"] if v in index)
                  for key, entry in registry.items()}

    chantiers_out = [{k: v for k, v in c.items() if k != "village_ids"} for c in chantiers]

    def attach(n):
        n["vi"] = ids_by_key.get(n["key"], [])
        # Cases « chantier en cours » (villages non desservis) et cases « avec / sans modalité de
        # gestion » (villages desservis) : on y rattache les chantiers dont un village est dans la case.
        if n["key"].endswith("_chantier") or n["key"].endswith("_management"):
            node_ids = registry[n["key"]]["village_ids"]
            n["ci"] = [i for i, c in enumerate(chantiers) if c["village_ids"] & node_ids]
            if n["key"].endswith("_management"):
                # Villages de la case ayant déposé au moins une demande (détail par village au clic)
                # requested_ids = tous les villages avec demande (summary["requested_ids"] est
                # restreint aux villages non desservis, donc vide ici).
                n["nd"] = len(node_ids & requested_ids)
        for child in n["children"]:
            attach(child)
    attach(root)
    return {
        "tree": root,
        "villages": villages,
        "chantiers": chantiers_out,
        "mois_facture_courant_label": _mois_facture_label(today.replace(day=1)),
    }


@login_required
def analyse_villages_desserte_flux_json(request):
    """JSON du diagramme de flux : villages -> organisations -> ouvrages."""
    user_organisation = get_user_organisation(request.user)
    data = _compute_village_flux(
        _normalize_filter_value(request.GET.get("region")),
        _get_district_param(request),
        _get_commune_param(request),
        _normalize_filter_value(request.GET.get("fokontany")),
        request.build_absolute_uri(reverse("core:analyse_villages_desserte")),
        user_org_id=str(user_organisation.id) if user_organisation else "",
        user_org_label=user_organisation.nom_organisation if user_organisation else "",
    )
    return JsonResponse({"success": True, **data})
