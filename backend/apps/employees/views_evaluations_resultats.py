"""
Vues pour l'évaluation métier des employés.

Le score dépend du rôle :
- Mpikojakoja ifotony : réparations terminées vs non terminées
- Agent de recouvrement : recouvrement volume + forfaitaire
- Supérieur hiérarchique : agrégation des scores des subordonnés contributeurs
"""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import json
import unicodedata

from django.db import OperationalError, ProgrammingError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.billing.models import PaiementForfaitaire, Releve
from apps.organization.models import Base
from apps.planning.models import Planning
from apps.planning.repair_classification import get_planning_repair_classification

from .models import Employe, EmployeOuvrages, HierarchieEmploye
from .models_evaluation_resultats import EvaluationResultats


DECIMAL_ZERO = Decimal("0.00")
DECIMAL_HUNDRED = Decimal("100")
VALID_STATUTS = {"provisoire", "validee"}
REPAIR_FAMILIES = {"reparation", "rehabilitation", "panne"}
MODE_LABELS = {
    "recouvrement": "Recouvrement",
    "reparations": "Réparations",
    "hierarchie": "Hiérarchie",
    "aucun": "Aucune règle",
}


def _get_user_organisation(request):
    if getattr(request.user, "is_superuser", False):
        return None
    if hasattr(request.user, "employe") and request.user.employe and request.user.employe.base:
        return request.user.employe.base.organisation
    return None


def _scoped_employes_queryset(request):
    queryset = Employe.objects.select_related("poste", "base", "base__organisation").all()
    organisation = _get_user_organisation(request)
    if organisation:
        queryset = queryset.filter(base__organisation=organisation)
    return queryset


def _scoped_bases_queryset(request):
    queryset = Base.objects.select_related("organisation").all()
    organisation = _get_user_organisation(request)
    if organisation:
        queryset = queryset.filter(organisation=organisation)
    return queryset


def _scoped_evaluations_queryset(request):
    queryset = EvaluationResultats.objects.select_related(
        "employe",
        "employe__poste",
        "employe__base",
        "employe__base__organisation",
    )
    organisation = _get_user_organisation(request)
    if organisation:
        queryset = queryset.filter(employe__base__organisation=organisation)
    return queryset


def _decimal(value):
    if value in (None, ""):
        return DECIMAL_ZERO
    return Decimal(str(value))


def _score_percent(score_obtenu, score_maximum):
    if not score_maximum:
        return DECIMAL_ZERO
    return (
        (Decimal(str(score_obtenu)) / Decimal(str(score_maximum))) * DECIMAL_HUNDRED
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_date(value, field_name):
    if not value:
        raise ValueError(f'Le champ "{field_name}" est obligatoire.')
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f'Format de date invalide pour "{field_name}".') from exc


def _read_payload(request):
    if request.content_type and "application/json" in request.content_type:
        if not request.body:
            return {}
        try:
            return json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("JSON invalide.") from exc
    return request.POST.dict()


def _schema_error_response(exc):
    return JsonResponse(
        {
            "success": False,
            "error": "Les tables d'évaluation par résultats ne sont pas encore disponibles. Exécutez `python manage.py migrate employees`.",
            "details": str(exc),
        },
        status=500,
    )


def _normalize_text(value):
    normalized = unicodedata.normalize("NFD", (value or "").strip().lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return " ".join(normalized.split())


def _get_poste_name(employe):
    poste = getattr(employe, "poste", None)
    return getattr(poste, "nom_poste", "") or ""


def _is_mpikojakoja_ifotony(employe):
    poste_name = _normalize_text(_get_poste_name(employe))
    return "mpikojakoja" in poste_name and "ifotony" in poste_name


def _is_agent_recouvrement(employe):
    poste_name = _normalize_text(_get_poste_name(employe))
    return "agent de recouvrement" in poste_name or ("recouvrement" in poste_name and "agent" in poste_name)


def _get_active_subordinate_employe_ids(root_employe_id, reference_date=None):
    reference_date = reference_date or timezone.now().date()
    employe_ids = {root_employe_id}
    frontier_ids = {root_employe_id}

    while frontier_ids:
        child_ids = set(
            HierarchieEmploye.objects.filter(
                superieur_id__in=frontier_ids,
                date_debut__lte=reference_date,
            )
            .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date))
            .values_list("employe_id", flat=True)
        )
        child_ids -= employe_ids
        if not child_ids:
            break
        employe_ids.update(child_ids)
        frontier_ids = child_ids

    return employe_ids


def _has_active_subordinates(employe, reference_date=None):
    reference_date = reference_date or timezone.now().date()
    return HierarchieEmploye.objects.filter(
        superieur=employe,
        date_debut__lte=reference_date,
    ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)).exists()


def _active_ouvrage_relations(employe, periode_debut, periode_fin):
    relations = (
        EmployeOuvrages.objects.filter(
            employe=employe,
            date_debut__lte=periode_fin,
        )
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=periode_debut))
        .select_related("ouvrage")
        .order_by("ouvrage__nom_ouvrage", "-est_responsable_principal", "-date_debut")
    )

    unique_relations = {}
    for relation in relations:
        unique_relations.setdefault(relation.ouvrage_id, relation)
    return list(unique_relations.values())


def _get_active_ouvrage_ids(employe, periode_debut, periode_fin):
    return [relation.ouvrage_id for relation in _active_ouvrage_relations(employe, periode_debut, periode_fin)]


def _make_base_snapshot(mode):
    return {
        "mode_evaluation": mode,
        "mode_evaluation_label": MODE_LABELS.get(mode, mode.title()),
        "nb_ouvrages": 0,
        "score_obtenu": 0,
        "score_maximum": 0,
        "montant_collecte_forfaitaire": DECIMAL_ZERO,
        "montant_collecte_volume": DECIMAL_ZERO,
        "montant_prevu_forfaitaire": DECIMAL_ZERO,
        "montant_prevu_volume": DECIMAL_ZERO,
        "details": [],
        "metrics": {},
        "_ouvrage_ids": set(),
    }


def _merge_detail(detail_map, point_totals, point_eau, ouvrage, type_paiement, montant_prevu, montant_paye):
    if not point_eau or not ouvrage:
        return
    if montant_prevu == DECIMAL_ZERO and montant_paye == DECIMAL_ZERO:
        return

    key = (str(point_eau.id), type_paiement)
    detail = detail_map.setdefault(
        key,
        {
            "point_eau_id": str(point_eau.id),
            "point_eau_nom": point_eau.nomabonne or f"Point d'eau {point_eau.id}",
            "ouvrage_id": str(ouvrage.id),
            "ouvrage_nom": ouvrage.nom_ouvrage or "Sans nom",
            "type_paiement": type_paiement,
            "montant_prevu": DECIMAL_ZERO,
            "montant_paye": DECIMAL_ZERO,
        },
    )
    detail["montant_prevu"] += montant_prevu
    detail["montant_paye"] += montant_paye

    point_total = point_totals[str(point_eau.id)]
    point_total["montant_prevu"] += montant_prevu
    point_total["montant_paye"] += montant_paye


def _build_recouvrement_snapshot(employe, periode_debut, periode_fin):
    snapshot = _make_base_snapshot("recouvrement")
    relations = _active_ouvrage_relations(employe, periode_debut, periode_fin)
    ouvrage_ids = [relation.ouvrage_id for relation in relations]

    detail_map = {}
    point_totals = defaultdict(lambda: {"montant_prevu": DECIMAL_ZERO, "montant_paye": DECIMAL_ZERO})

    if ouvrage_ids:
        releves = (
            Releve.objects.select_related("point_eau", "point_eau__ouvrage")
            .filter(
                point_eau__ouvrage_id__in=ouvrage_ids,
                datereleve__gte=periode_debut,
                datereleve__lte=periode_fin,
            )
        )
        for releve in releves:
            montant_prevu = _decimal(releve.montant)
            montant_paye = _decimal(releve.montantpaye)
            if montant_paye == DECIMAL_ZERO and (releve.est_paye or releve.statut == "paye"):
                montant_paye = montant_prevu
            _merge_detail(
                detail_map,
                point_totals,
                releve.point_eau,
                releve.point_eau.ouvrage if releve.point_eau else None,
                "volume",
                montant_prevu,
                montant_paye,
            )

        paiements_forfaitaires = (
            PaiementForfaitaire.objects.select_related("point_eau", "point_eau__ouvrage")
            .filter(
                point_eau__ouvrage_id__in=ouvrage_ids,
                date_facture__gte=periode_debut,
                date_facture__lte=periode_fin,
            )
        )
        for paiement in paiements_forfaitaires:
            montant_prevu = _decimal(paiement.montant)
            montant_paye = montant_prevu if paiement.est_paye else DECIMAL_ZERO
            _merge_detail(
                detail_map,
                point_totals,
                paiement.point_eau,
                paiement.point_eau.ouvrage if paiement.point_eau else None,
                "forfaitaire",
                montant_prevu,
                montant_paye,
            )

    raw_details = sorted(
        detail_map.values(),
        key=lambda item: (
            item["ouvrage_nom"].casefold(),
            item["point_eau_nom"].casefold(),
            item["type_paiement"],
        ),
    )

    montant_collecte_forfaitaire = DECIMAL_ZERO
    montant_collecte_volume = DECIMAL_ZERO
    montant_prevu_forfaitaire = DECIMAL_ZERO
    montant_prevu_volume = DECIMAL_ZERO
    details = []

    for detail in raw_details:
        point_obtenu = detail["montant_prevu"] > DECIMAL_ZERO and detail["montant_paye"] >= detail["montant_prevu"]
        if detail["type_paiement"] == "forfaitaire":
            montant_prevu_forfaitaire += detail["montant_prevu"]
            montant_collecte_forfaitaire += detail["montant_paye"]
        else:
            montant_prevu_volume += detail["montant_prevu"]
            montant_collecte_volume += detail["montant_paye"]

        details.append(
            {
                "detail_kind": "recouvrement",
                "source_mode": "recouvrement",
                "employe_id": str(employe.id),
                "employe_nom": employe.nom_affichage,
                "employe_poste": _get_poste_name(employe) or "-",
                "libelle": detail["point_eau_nom"],
                "ouvrage_id": detail["ouvrage_id"],
                "ouvrage_nom": detail["ouvrage_nom"],
                "point_eau_id": detail["point_eau_id"],
                "point_eau_nom": detail["point_eau_nom"],
                "nature_label": "Paiement forfaitaire" if detail["type_paiement"] == "forfaitaire" else "Paiement volume",
                "type_paiement": detail["type_paiement"],
                "montant_prevu": float(detail["montant_prevu"]),
                "montant_paye": float(detail["montant_paye"]),
                "score_obtenu": 1 if point_obtenu else 0,
                "score_maximum": 1,
                "point_obtenu": point_obtenu,
                "resume": "Conforme" if point_obtenu else "Non conforme",
            }
        )

    score_maximum = len(point_totals)
    score_obtenu = sum(
        1
        for totals in point_totals.values()
        if totals["montant_prevu"] > DECIMAL_ZERO and totals["montant_paye"] >= totals["montant_prevu"]
    )

    snapshot.update(
        {
            "nb_ouvrages": len(relations),
            "score_obtenu": score_obtenu,
            "score_maximum": score_maximum,
            "montant_collecte_forfaitaire": montant_collecte_forfaitaire,
            "montant_collecte_volume": montant_collecte_volume,
            "montant_prevu_forfaitaire": montant_prevu_forfaitaire,
            "montant_prevu_volume": montant_prevu_volume,
            "details": details,
            "metrics": {
                "points_eau_total": score_maximum,
                "points_eau_conformes": score_obtenu,
                "points_eau_non_conformes": max(score_maximum - score_obtenu, 0),
            },
            "_ouvrage_ids": set(ouvrage_ids),
        }
    )
    return snapshot


def _get_repair_plannings_queryset(employe, periode_debut, periode_fin, ouvrage_ids=None):
    queryset = (
        Planning.objects.select_related("ouvrage", "fiche_poste", "fiche_poste__type_activites")
        .filter(date__date__gte=periode_debut, date__date__lte=periode_fin)
        .filter(Q(employe=employe) | Q(planning_employees__employee=employe))
        .distinct()
    )
    if ouvrage_ids is not None:
        queryset = queryset.filter(ouvrage_id__in=ouvrage_ids)
    return queryset


def _build_reparations_snapshot(employe, periode_debut, periode_fin):
    snapshot = _make_base_snapshot("reparations")
    relations = _active_ouvrage_relations(employe, periode_debut, periode_fin)
    ouvrage_ids = [relation.ouvrage_id for relation in relations]
    if not ouvrage_ids:
        return snapshot

    grouped = {}
    total_terminees = 0
    total_non_terminees = 0

    for planning in _get_repair_plannings_queryset(employe, periode_debut, periode_fin, ouvrage_ids):
        classification = get_planning_repair_classification(planning)
        if classification.get("family") not in REPAIR_FAMILIES:
            continue

        ouvrage = getattr(planning, "ouvrage", None)
        if not ouvrage:
            continue

        key = str(ouvrage.id)
        row = grouped.setdefault(
            key,
            {
                "ouvrage_id": key,
                "ouvrage_nom": ouvrage.nom_ouvrage or "Sans nom",
                "terminees": 0,
                "non_terminees": 0,
                "total": 0,
            },
        )
        row["total"] += 1
        if planning.estvalide:
            row["terminees"] += 1
            total_terminees += 1
        else:
            row["non_terminees"] += 1
            total_non_terminees += 1

    details = []
    for row in sorted(grouped.values(), key=lambda item: item["ouvrage_nom"].casefold()):
        details.append(
            {
                "detail_kind": "reparation",
                "source_mode": "reparations",
                "employe_id": str(employe.id),
                "employe_nom": employe.nom_affichage,
                "employe_poste": _get_poste_name(employe) or "-",
                "libelle": row["ouvrage_nom"],
                "ouvrage_id": row["ouvrage_id"],
                "ouvrage_nom": row["ouvrage_nom"],
                "point_eau_id": "",
                "point_eau_nom": "-",
                "nature_label": "Réparations",
                "type_paiement": "reparations",
                "montant_prevu": float(row["total"]),
                "montant_paye": float(row["terminees"]),
                "score_obtenu": row["terminees"],
                "score_maximum": row["total"],
                "point_obtenu": row["non_terminees"] == 0 and row["total"] > 0,
                "terminees": row["terminees"],
                "non_terminees": row["non_terminees"],
                "resume": f"{row['terminees']} terminée(s) / {row['non_terminees']} non terminée(s)",
            }
        )

    score_maximum = total_terminees + total_non_terminees
    snapshot.update(
        {
            "nb_ouvrages": len(relations),
            "score_obtenu": total_terminees,
            "score_maximum": score_maximum,
            "details": details,
            "metrics": {
                "reparations_total": score_maximum,
                "reparations_terminees": total_terminees,
                "reparations_non_terminees": total_non_terminees,
            },
            "_ouvrage_ids": set(ouvrage_ids),
        }
    )
    return snapshot


def _has_repair_activity(employe, periode_debut, periode_fin):
    ouvrage_ids = _get_active_ouvrage_ids(employe, periode_debut, periode_fin)
    if not ouvrage_ids:
        return False
    for planning in _get_repair_plannings_queryset(employe, periode_debut, periode_fin, ouvrage_ids):
        if get_planning_repair_classification(planning).get("family") in REPAIR_FAMILIES:
            return True
    return False


def _has_recouvrement_activity(employe, periode_debut, periode_fin):
    ouvrage_ids = _get_active_ouvrage_ids(employe, periode_debut, periode_fin)
    if not ouvrage_ids:
        return False
    return (
        Releve.objects.filter(
            point_eau__ouvrage_id__in=ouvrage_ids,
            datereleve__gte=periode_debut,
            datereleve__lte=periode_fin,
        ).exists()
        or PaiementForfaitaire.objects.filter(
            point_eau__ouvrage_id__in=ouvrage_ids,
            date_facture__gte=periode_debut,
            date_facture__lte=periode_fin,
        ).exists()
    )


def _infer_evaluation_mode(employe, periode_debut, periode_fin, allow_hierarchy=True):
    if allow_hierarchy and _has_active_subordinates(employe, periode_fin):
        return "hierarchie"
    if _is_mpikojakoja_ifotony(employe):
        return "reparations"
    if _is_agent_recouvrement(employe):
        return "recouvrement"
    if _has_repair_activity(employe, periode_debut, periode_fin):
        return "reparations"
    if _has_recouvrement_activity(employe, periode_debut, periode_fin):
        return "recouvrement"
    return "aucun"


def _build_hierarchy_snapshot(employe, periode_debut, periode_fin):
    snapshot = _make_base_snapshot("hierarchie")
    descendant_ids = _get_active_subordinate_employe_ids(employe.id, periode_fin)
    descendant_ids.discard(employe.id)

    if not descendant_ids:
        return snapshot

    descendants = list(
        Employe.objects.select_related("poste", "base")
        .filter(id__in=descendant_ids)
        .order_by("surnom", "nom", "prenom")
    )

    normalized_score_total = DECIMAL_ZERO
    montant_collecte_forfaitaire = DECIMAL_ZERO
    montant_collecte_volume = DECIMAL_ZERO
    montant_prevu_forfaitaire = DECIMAL_ZERO
    montant_prevu_volume = DECIMAL_ZERO
    ouvrage_ids = set()
    details = []
    sub_reparations = 0
    sub_recouvrement = 0

    for descendant in descendants:
        child_mode = _infer_evaluation_mode(descendant, periode_debut, periode_fin, allow_hierarchy=False)
        if child_mode == "reparations":
            child_snapshot = _build_reparations_snapshot(descendant, periode_debut, periode_fin)
            sub_reparations += 1
        elif child_mode == "recouvrement":
            child_snapshot = _build_recouvrement_snapshot(descendant, periode_debut, periode_fin)
            sub_recouvrement += 1
        else:
            continue

        if (
            child_snapshot["score_maximum"] == 0
            and child_snapshot["montant_prevu_forfaitaire"] == DECIMAL_ZERO
            and child_snapshot["montant_prevu_volume"] == DECIMAL_ZERO
        ):
            continue

        child_score_percent = _score_percent(
            child_snapshot["score_obtenu"],
            child_snapshot["score_maximum"],
        )
        normalized_score_total += child_score_percent
        montant_collecte_forfaitaire += child_snapshot["montant_collecte_forfaitaire"]
        montant_collecte_volume += child_snapshot["montant_collecte_volume"]
        montant_prevu_forfaitaire += child_snapshot["montant_prevu_forfaitaire"]
        montant_prevu_volume += child_snapshot["montant_prevu_volume"]
        ouvrage_ids.update(child_snapshot.get("_ouvrage_ids", set()))

        child_metrics = child_snapshot.get("metrics", {})
        details.append(
            {
                "detail_kind": "subordonne",
                "source_mode": child_snapshot["mode_evaluation"],
                "employe_id": str(descendant.id),
                "employe_nom": descendant.nom_affichage,
                "employe_poste": _get_poste_name(descendant) or "-",
                "libelle": descendant.nom_affichage,
                "ouvrage_id": "",
                "ouvrage_nom": "-",
                "point_eau_id": "",
                "point_eau_nom": "-",
                "nature_label": child_snapshot["mode_evaluation_label"],
                "type_paiement": child_snapshot["mode_evaluation"],
                "montant_prevu": float(
                    child_snapshot["montant_prevu_forfaitaire"] + child_snapshot["montant_prevu_volume"]
                ),
                "montant_paye": float(
                    child_snapshot["montant_collecte_forfaitaire"] + child_snapshot["montant_collecte_volume"]
                ),
                  "score_obtenu": child_snapshot["score_obtenu"],
                  "score_maximum": child_snapshot["score_maximum"],
                  "point_obtenu": child_snapshot["score_maximum"] > 0
                  and child_snapshot["score_obtenu"] >= child_snapshot["score_maximum"],
                  "normalized_score_percent": float(child_score_percent),
                  "terminees": child_metrics.get("reparations_terminees", 0),
                  "non_terminees": child_metrics.get("reparations_non_terminees", 0),
                  "resume": (
                      f"{child_metrics.get('reparations_terminees', 0)} terminée(s) / "
                      f"{child_metrics.get('reparations_non_terminees', 0)} non terminée(s)"
                      if child_snapshot["mode_evaluation"] == "reparations"
                      else f"{child_snapshot['score_obtenu']}/{child_snapshot['score_maximum']} points"
                  ),
              }
          )

    contributor_count = len(details)
    if contributor_count:
        average_score_percent = (
            normalized_score_total / Decimal(str(contributor_count))
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        score_obtenu = int(average_score_percent)
        score_maximum = 100
    else:
        score_obtenu = 0
        score_maximum = 0

    snapshot.update(
        {
            "nb_ouvrages": len(ouvrage_ids),
            "score_obtenu": score_obtenu,
            "score_maximum": score_maximum,
            "montant_collecte_forfaitaire": montant_collecte_forfaitaire,
            "montant_collecte_volume": montant_collecte_volume,
            "montant_prevu_forfaitaire": montant_prevu_forfaitaire,
            "montant_prevu_volume": montant_prevu_volume,
            "details": details,
            "metrics": {
                "subordonnes_contributeurs": contributor_count,
                "subordonnes_reparations": sub_reparations,
                "subordonnes_recouvrement": sub_recouvrement,
                "score_moyen_sur_100": score_obtenu,
            },
            "_ouvrage_ids": ouvrage_ids,
        }
    )
    return snapshot


def _build_evaluation_snapshot(employe, periode_debut, periode_fin, allow_hierarchy=True):
    mode = _infer_evaluation_mode(employe, periode_debut, periode_fin, allow_hierarchy=allow_hierarchy)
    if mode == "reparations":
        return _build_reparations_snapshot(employe, periode_debut, periode_fin)
    if mode == "hierarchie":
        return _build_hierarchy_snapshot(employe, periode_debut, periode_fin)
    if mode == "recouvrement":
        return _build_recouvrement_snapshot(employe, periode_debut, periode_fin)
    return _make_base_snapshot("aucun")


def _legacy_details_payload(evaluation):
    details = evaluation.details.select_related("point_eau", "ouvrage").all()
    payload = []
    for detail in details:
        payload.append(
            {
                "detail_kind": "recouvrement",
                "source_mode": "recouvrement",
                "employe_id": str(evaluation.employe_id),
                "employe_nom": evaluation.employe.nom_affichage,
                "employe_poste": evaluation.employe.poste.nom_poste if evaluation.employe.poste else "-",
                "libelle": detail.point_eau.nomabonne if detail.point_eau else "-",
                "ouvrage_id": str(detail.ouvrage_id),
                "ouvrage_nom": detail.ouvrage.nom_ouvrage if detail.ouvrage else "-",
                "point_eau_id": str(detail.point_eau_id),
                "point_eau_nom": detail.point_eau.nomabonne if detail.point_eau else "-",
                "nature_label": detail.get_type_paiement_display(),
                "type_paiement": detail.type_paiement,
                "montant_prevu": float(detail.montant_prevu or 0),
                "montant_paye": float(detail.montant_paye or 0),
                "score_obtenu": 1 if detail.point_obtenu else 0,
                "score_maximum": 1,
                "point_obtenu": detail.point_obtenu,
                "resume": "Conforme" if detail.point_obtenu else "Non conforme",
            }
        )
    return payload


def _build_resume_court(mode, metrics, montant_total_prevu, montant_total_collecte):
    metrics = metrics or {}
    if mode == "reparations":
        return (
            f"{metrics.get('reparations_terminees', 0)} terminée(s) · "
            f"{metrics.get('reparations_non_terminees', 0)} non terminée(s)"
        )
    if mode == "hierarchie":
        return (
            f"{metrics.get('subordonnes_contributeurs', 0)} contributeur(s) · "
            f"moyenne {metrics.get('score_moyen_sur_100', 0)}/100 · "
            f"{metrics.get('subordonnes_reparations', 0)} technique(s) · "
            f"{metrics.get('subordonnes_recouvrement', 0)} recouvrement"
        )
    if mode == "recouvrement":
        return (
            f"Prévu {int(montant_total_prevu):,} Ar · "
            f"Collecté {int(montant_total_collecte):,} Ar"
        ).replace(",", " ")
    return "Aucune règle applicable"


def _serialize_evaluation(evaluation):
    mode = evaluation.mode_evaluation or "recouvrement"
    metrics = evaluation.metrics_snapshot or {}
    return {
        "id": str(evaluation.id),
        "employe_id": str(evaluation.employe_id),
        "employe_nom": evaluation.employe.nom_affichage,
        "employe_poste": evaluation.employe.poste.nom_poste if evaluation.employe.poste else "-",
        "base_nom": evaluation.employe.base.nom_base if evaluation.employe.base else "-",
        "periode_debut": evaluation.periode_debut.isoformat(),
        "periode_fin": evaluation.periode_fin.isoformat(),
        "date_calcul": evaluation.date_calcul.isoformat() if evaluation.date_calcul else "",
        "score_obtenu": evaluation.score_obtenu,
        "score_maximum": evaluation.score_maximum,
        "pourcentage": float(evaluation.pourcentage or 0),
        "nb_ouvrages": evaluation.nb_ouvrages,
        "montant_collecte_forfaitaire": float(evaluation.montant_collecte_forfaitaire or 0),
        "montant_collecte_volume": float(evaluation.montant_collecte_volume or 0),
        "montant_prevu_forfaitaire": float(evaluation.montant_prevu_forfaitaire or 0),
        "montant_prevu_volume": float(evaluation.montant_prevu_volume or 0),
        "montant_total_collecte": float(evaluation.montant_total_collecte or 0),
        "montant_total_prevu": float(evaluation.montant_total_prevu or 0),
        "taux_recouvrement": float(evaluation.taux_recouvrement or 0),
        "statut": evaluation.statut,
        "commentaire": evaluation.commentaire or "",
        "mode_evaluation": mode,
        "mode_evaluation_label": MODE_LABELS.get(mode, mode.title()),
        "metrics_snapshot": metrics,
        "resume_court": _build_resume_court(
            mode,
            metrics,
            evaluation.montant_total_prevu,
            evaluation.montant_total_collecte,
        ),
    }


def evaluations_resultats_list(request):
    """Page de liste des évaluations par résultats."""
    employes = _scoped_employes_queryset(request).filter(date_debauchage__isnull=True).order_by("surnom", "nom", "prenom")
    bases = _scoped_bases_queryset(request).order_by("nom_base")

    return render(
        request,
        "employees/evaluations_resultats_list.html",
        {
            "employes": employes,
            "bases": bases,
        },
    )


@csrf_exempt
@require_http_methods(["GET"])
def api_evaluations_resultats_list(request):
    """Liste des évaluations résultats avec filtres."""
    try:
        employe_id = request.GET.get("employe_id")
        base_id = request.GET.get("base_id")
        statut = request.GET.get("statut")
        annee = request.GET.get("annee")

        evaluations = _scoped_evaluations_queryset(request)

        if base_id:
            evaluations = evaluations.filter(employe__base_id=base_id)
        if employe_id:
            evaluations = evaluations.filter(employe_id=employe_id)
        if statut:
            evaluations = evaluations.filter(statut=statut)
        if annee:
            evaluations = evaluations.filter(periode_fin__year=annee)

        data = [_serialize_evaluation(evaluation) for evaluation in evaluations]

        return JsonResponse(
            {
                "success": True,
                "evaluations": data,
                "count": len(data),
            }
        )
    except (OperationalError, ProgrammingError) as exc:
        return _schema_error_response(exc)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_evaluation_resultats_detail(request, evaluation_id):
    """Détail d'une évaluation résultats."""
    try:
        evaluation = get_object_or_404(_scoped_evaluations_queryset(request), id=evaluation_id)
        details_data = evaluation.details_snapshot or _legacy_details_payload(evaluation)

        return JsonResponse(
            {
                "success": True,
                "evaluation": _serialize_evaluation(evaluation),
                "details": details_data,
            }
        )
    except (OperationalError, ProgrammingError) as exc:
        return _schema_error_response(exc)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_resultats_create(request):
    """Crée ou recalcule une évaluation résultats pour un employé et une période."""
    try:
        payload = _read_payload(request)
        employe_id = payload.get("employe_id")
        commentaire = (payload.get("commentaire") or "").strip()
        statut = payload.get("statut") or "provisoire"
        if statut not in VALID_STATUTS:
            statut = "provisoire"

        periode_debut = _parse_date(payload.get("periode_debut"), "periode_debut")
        periode_fin = _parse_date(payload.get("periode_fin"), "periode_fin")
        if periode_fin < periode_debut:
            return JsonResponse(
                {
                    "success": False,
                    "error": "La date de fin doit être supérieure ou égale à la date de début.",
                },
                status=400,
            )

        employe = get_object_or_404(_scoped_employes_queryset(request), id=employe_id)
        snapshot = _build_evaluation_snapshot(employe, periode_debut, periode_fin)

        with transaction.atomic():
            evaluation, created = EvaluationResultats.objects.update_or_create(
                employe=employe,
                periode_debut=periode_debut,
                periode_fin=periode_fin,
                defaults={
                    "date_calcul": date.today(),
                    "score_obtenu": snapshot["score_obtenu"],
                    "score_maximum": snapshot["score_maximum"],
                    "nb_ouvrages": snapshot["nb_ouvrages"],
                    "montant_collecte_forfaitaire": snapshot["montant_collecte_forfaitaire"],
                    "montant_collecte_volume": snapshot["montant_collecte_volume"],
                    "montant_prevu_forfaitaire": snapshot["montant_prevu_forfaitaire"],
                    "montant_prevu_volume": snapshot["montant_prevu_volume"],
                    "statut": statut,
                    "commentaire": commentaire,
                    "mode_evaluation": snapshot["mode_evaluation"],
                    "details_snapshot": snapshot["details"],
                    "metrics_snapshot": snapshot["metrics"],
                },
            )
            evaluation.details.all().delete()

        return JsonResponse(
            {
                "success": True,
                "created": created,
                "evaluation": _serialize_evaluation(evaluation),
                "message": "Évaluation créée." if created else "Évaluation recalculée.",
            }
        )
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except (OperationalError, ProgrammingError) as exc:
        return _schema_error_response(exc)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_resultats_update(request, evaluation_id):
    """Met à jour une évaluation résultats ou force un recalcul."""
    try:
        payload = _read_payload(request)
        evaluation = get_object_or_404(_scoped_evaluations_queryset(request), id=evaluation_id)

        recalculate = str(payload.get("recalculate", "")).lower() in {"1", "true", "yes", "on"}
        statut = payload.get("statut")
        commentaire = payload.get("commentaire")

        with transaction.atomic():
            if recalculate:
                snapshot = _build_evaluation_snapshot(
                    evaluation.employe,
                    evaluation.periode_debut,
                    evaluation.periode_fin,
                )
                evaluation.date_calcul = date.today()
                evaluation.score_obtenu = snapshot["score_obtenu"]
                evaluation.score_maximum = snapshot["score_maximum"]
                evaluation.nb_ouvrages = snapshot["nb_ouvrages"]
                evaluation.montant_collecte_forfaitaire = snapshot["montant_collecte_forfaitaire"]
                evaluation.montant_collecte_volume = snapshot["montant_collecte_volume"]
                evaluation.montant_prevu_forfaitaire = snapshot["montant_prevu_forfaitaire"]
                evaluation.montant_prevu_volume = snapshot["montant_prevu_volume"]
                evaluation.mode_evaluation = snapshot["mode_evaluation"]
                evaluation.details_snapshot = snapshot["details"]
                evaluation.metrics_snapshot = snapshot["metrics"]

            if statut in VALID_STATUTS:
                evaluation.statut = statut
            if commentaire is not None:
                evaluation.commentaire = commentaire.strip()

            evaluation.save()

            if recalculate:
                evaluation.details.all().delete()

        return JsonResponse(
            {
                "success": True,
                "evaluation": _serialize_evaluation(evaluation),
                "message": "Évaluation mise à jour.",
            }
        )
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except (OperationalError, ProgrammingError) as exc:
        return _schema_error_response(exc)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_resultats_delete(request, evaluation_id):
    """Supprime une évaluation résultats."""
    try:
        evaluation = get_object_or_404(_scoped_evaluations_queryset(request), id=evaluation_id)
        evaluation.delete()
        return JsonResponse({"success": True, "message": "Évaluation supprimée."})
    except (OperationalError, ProgrammingError) as exc:
        return _schema_error_response(exc)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
