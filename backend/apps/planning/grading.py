"""
Logique de calcul du grading des ouvrages.
Base sur les interventions de reparation / rehabilitation planifiees.
"""

from datetime import datetime

import pytz
from django.db.models import Q

from apps.planning.repair_classification import get_planning_repair_classification


def get_ouvrage_grading(ouvrage_id, date_reference=None):
    """
    Calcule le grading d'un ouvrage a une date donnee.
    """
    from django.utils import timezone

    from .models import Planning

    tz_madagascar = pytz.timezone("Indian/Antananarivo")
    if date_reference is None:
        date_ref = timezone.now().astimezone(tz_madagascar)
    else:
        if isinstance(date_reference, str):
            date_naive = datetime.strptime(date_reference, "%Y-%m-%d")
            date_ref = tz_madagascar.localize(date_naive)
        else:
            date_ref = (
                date_reference.astimezone(tz_madagascar)
                if date_reference.tzinfo
                else tz_madagascar.localize(date_reference)
            )

    del date_ref

    plannings_ouvrage = (
        Planning.objects
        .filter(Q(estvalide__isnull=True) | Q(estvalide=False), ouvrage_id=ouvrage_id)
        .select_related("fiche_poste", "fiche_poste__type_activites", "type_activite")
    )

    has_repair = False
    has_rehab = False
    has_panne = False

    for planning in plannings_ouvrage.iterator():
        classification = get_planning_repair_classification(planning)
        family = classification.get("family")
        if not family:
            continue

        has_panne = has_panne or classification.get("is_panne", False)
        if family == "rehabilitation":
            has_rehab = True
        elif family in ("reparation", "panne"):
            has_repair = True

    if has_rehab and has_panne:
        return {
            "grade": "D_PANNE",
            "label": "Grading D (panne)",
            "color": "error",
            "badge_class": "badge-error",
            "description": "Rehabilitation prevue avec panne",
        }
    if has_rehab:
        return {
            "grade": "D",
            "label": "Grading D",
            "color": "error",
            "badge_class": "badge-error",
            "description": "Rehabilitation prevue",
        }
    if has_repair and has_panne:
        return {
            "grade": "B_PANNE",
            "label": "Grading B (panne)",
            "color": "warning",
            "badge_class": "badge-warning",
            "description": "Reparation prevue avec panne",
        }
    if has_repair:
        return {
            "grade": "B",
            "label": "Grading B",
            "color": "warning",
            "badge_class": "badge-warning",
            "description": "Reparation prevue",
        }

    return {
        "grade": "A",
        "label": "Grading A",
        "color": "success",
        "badge_class": "badge-success",
        "description": "Aucune intervention prevue",
    }


def get_gradings_statistics(ouvrage_ids, date_reference=None):
    """
    Calcule les statistiques de grading pour une liste d'ouvrages.
    """
    stats = {
        "A": 0,
        "B": 0,
        "B_PANNE": 0,
        "D": 0,
        "D_PANNE": 0,
        "total": len(ouvrage_ids),
    }

    for ouvrage_id in ouvrage_ids:
        grading = get_ouvrage_grading(ouvrage_id, date_reference)
        grade = grading["grade"]
        stats[grade] = stats.get(grade, 0) + 1

    return stats
