"""
Helpers de grading pour le workflow de suivi des reparations.

Regle metier:
- un ouvrage n'est en Grading A que s'il n'a aucune reparation ouverte
  (planning non valide) dans le perimetre filtre;
- les reparations deja validees ne degradent plus le grading.
"""

from apps.planning.repair_classification import (
    get_planning_repair_classification,
    get_repair_classification,
)


def _planning_is_validated(planning):
    if isinstance(planning, dict):
        return bool(planning.get("estvalide"))
    return bool(getattr(planning, "estvalide", False))


def _planning_classification(planning, fiche_poste_to_activite_nom=None):
    fiche_poste_to_activite_nom = fiche_poste_to_activite_nom or {}

    if isinstance(planning, dict):
        fiche_poste_id = planning.get("fiche_poste_id")
        type_name = (
            fiche_poste_to_activite_nom.get(fiche_poste_id)
            or fiche_poste_to_activite_nom.get(str(fiche_poste_id))
            or ""
        )
        return get_repair_classification(
            type_name=type_name,
            fiche_label=planning.get("fiche_label", "") or "",
            remarque=planning.get("remarque", "") or "",
        )

    fiche_poste_id = getattr(planning, "fiche_poste_id", None)
    type_name = (
        fiche_poste_to_activite_nom.get(fiche_poste_id)
        or fiche_poste_to_activite_nom.get(str(fiche_poste_id))
        or ""
    )
    if type_name:
        return get_repair_classification(
            type_name=type_name,
            fiche_label=getattr(getattr(planning, "fiche_poste", None), "tache", "") or "",
            remarque=getattr(planning, "remarque", "") or "",
        )
    return get_planning_repair_classification(planning)


def get_open_repair_flags(plannings, fiche_poste_to_activite_nom=None):
    has_repair = False
    has_rehab = False
    has_panne = False

    for planning in plannings:
        if _planning_is_validated(planning):
            continue

        classification = _planning_classification(planning, fiche_poste_to_activite_nom)
        family = classification.get("family")
        if not family:
            continue

        has_panne = has_panne or bool(classification.get("is_panne"))
        if family == "rehabilitation":
            has_rehab = True
        elif family == "reparation":
            has_repair = True

    return {
        "has_repair": has_repair,
        "has_rehab": has_rehab,
        "has_panne": has_panne,
    }


def get_repair_workflow_grading_from_flags(has_repair=False, has_rehab=False, has_panne=False):
    if not has_repair and not has_rehab and not has_panne:
        return {
            "code": "A",
            "upper_code": "A",
            "short_label": "A",
            "long_label": "Grading A",
            "badge": "success",
            "description": "Aucune reparation non terminee",
        }
    if has_rehab and has_panne:
        return {
            "code": "D_panne",
            "upper_code": "D_PANNE",
            "short_label": "D Panne",
            "long_label": "Grading D (panne)",
            "badge": "error",
            "description": "Rehabilitation non terminee avec panne",
        }
    if has_rehab:
        return {
            "code": "D",
            "upper_code": "D",
            "short_label": "D",
            "long_label": "Grading D",
            "badge": "error",
            "description": "Rehabilitation non terminee",
        }
    if has_repair and has_panne:
        return {
            "code": "B_panne",
            "upper_code": "B_PANNE",
            "short_label": "B Panne",
            "long_label": "Grading B (panne)",
            "badge": "warning",
            "description": "Reparation non terminee avec panne",
        }
    if has_repair:
        return {
            "code": "B",
            "upper_code": "B",
            "short_label": "B",
            "long_label": "Grading B",
            "badge": "warning",
            "description": "Reparation non terminee",
        }
    return {
        "code": "C",
        "upper_code": "C",
        "short_label": "C",
        "long_label": "Grading C",
        "badge": "info",
        "description": "Cas a analyser",
    }


def get_repair_workflow_grading_from_plannings(plannings, fiche_poste_to_activite_nom=None):
    flags = get_open_repair_flags(plannings, fiche_poste_to_activite_nom)
    return get_repair_workflow_grading_from_flags(**flags)
