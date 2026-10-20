import random
from datetime import date

from django.db.models import Count, Q
from django.utils import timezone

from apps.billing.models import ModaliteGestion, PointEau
from apps.employees.models import Employe, EmployeOuvrages
from apps.geography.models import Village
from apps.organization.models import Ouvrage


def _shuffle_choices(correct_value, distractors):
    choices = [str(correct_value)]
    for value in distractors:
        value_str = str(value)
        if value_str not in choices:
            choices.append(value_str)
    random.shuffle(choices)
    return choices


def _build_numeric_distractors(value):
    try:
        base = int(value)
    except (TypeError, ValueError):
        return []

    offsets = [1, 2, 3, 4, 5]
    candidates = []
    for offset in offsets:
        candidates.extend([
            max(0, base - offset),
            max(0, base - (offset * 2)),
            base + offset,
            base + (offset * 2),
        ])
    unique = [candidate for candidate in dict.fromkeys(candidates) if candidate != base]
    return unique[:3]


def _normalize_person_name(employe):
    if not employe:
        return ""
    return employe.nom_affichage or employe.nom_complet or employe.nom_employe or str(employe)


def _active_modalites_for_year(year):
    year_end = date(year, 12, 31)
    return ModaliteGestion.objects.filter(
        date_debut__lte=year_end,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=date(year, 1, 1))
    )


def _active_points_queryset():
    return PointEau.objects.filter(
        datebranchement__isnull=False,
        datearretbranchement__isnull=True,
    )


def generate_nombre_ouvrages_par_annee():
    current_year = timezone.localdate().year
    years = list(range(max(2020, current_year - 3), current_year + 1))
    random.shuffle(years)

    qs = ModaliteGestion.objects.select_related("gestionnaire")
    soakojas = qs.filter(gestionnaire__nom_organisation__icontains="SOAKOJA")

    source_qs = soakojas if soakojas.exists() else qs
    for year in years:
        count = _active_modalites_for_year(year).filter(
            id__in=source_qs.values_list("id", flat=True)
        ).values("ouvrage_id").distinct().count()
        if count:
            return {
                "question": f"Combien d'ouvrages gérés par SOAKOJA sont actifs en {year} dans Hydria ?",
                "type": "numerique",
                "bonne_reponse": str(count),
                "choix": _shuffle_choices(count, _build_numeric_distractors(count)),
                "explication": f"Le calcul prend les modalités de gestion actives sur l'année {year}.",
            }
    return None


def generate_points_eau_par_village():
    village = (
        Village.objects.annotate(
            total_points=Count(
                "parcelles__pointeau",
                filter=Q(
                    parcelles__pointeau__datebranchement__isnull=False,
                    parcelles__pointeau__datearretbranchement__isnull=True,
                ),
                distinct=True,
            )
        )
        .filter(total_points__gt=0)
        .order_by("?")
        .first()
    )
    if not village:
        return None

    count = int(village.total_points or 0)
    return {
        "question": f"Combien de points d'eau actifs sont enregistrés dans le village {village.nom_village} ?",
        "type": "numerique",
        "bonne_reponse": str(count),
        "choix": _shuffle_choices(count, _build_numeric_distractors(count)),
        "explication": "Le total compte les points d'eau branchés et non arrêtés rattachés aux parcelles du village.",
    }


def generate_points_eau_par_ouvrage():
    ouvrage = (
        Ouvrage.objects.annotate(
            total_points=Count(
                "pointeau",
                filter=Q(
                    pointeau__datebranchement__isnull=False,
                    pointeau__datearretbranchement__isnull=True,
                ),
                distinct=True,
            )
        )
        .filter(total_points__gt=0)
        .order_by("?")
        .first()
    )
    if not ouvrage:
        return None

    count = int(ouvrage.total_points or 0)
    return {
        "question": f"Combien de points d'eau actifs sont rattachés à l'ouvrage {ouvrage.nom_ouvrage} ?",
        "type": "numerique",
        "bonne_reponse": str(count),
        "choix": _shuffle_choices(count, _build_numeric_distractors(count)),
        "explication": "Le calcul utilise les points d'eau actifs liés directement à cet ouvrage.",
    }


def generate_ouvrages_par_responsable():
    relation = (
        EmployeOuvrages.objects.filter(Q(date_fin__isnull=True) | Q(date_fin__gte=timezone.localdate()))
        .values("employe")
        .annotate(total_ouvrages=Count("ouvrage", distinct=True))
        .filter(total_ouvrages__gt=0)
        .order_by("?")
        .first()
    )
    if not relation:
        return None

    employe = Employe.objects.filter(id=relation["employe"]).first()
    if not employe:
        return None

    count = int(relation["total_ouvrages"] or 0)
    nom = _normalize_person_name(employe)
    return {
        "question": f"Combien d'ouvrages actifs sont affectés à {nom} ?",
        "type": "numerique",
        "bonne_reponse": str(count),
        "choix": _shuffle_choices(count, _build_numeric_distractors(count)),
        "explication": "Le calcul utilise les responsabilités d'ouvrage actives à la date du quiz.",
    }


def generate_responsable_ouvrage():
    relation = (
        EmployeOuvrages.objects.select_related("ouvrage", "employe")
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=timezone.localdate()))
        .order_by("-est_responsable_principal", "?")
        .first()
    )
    if not relation:
        return None

    correct_name = _normalize_person_name(relation.employe)
    distractors = list(
        Employe.objects.exclude(id=relation.employe_id)
        .values_list("nom_employe", flat=True)[:20]
    )
    random.shuffle(distractors)

    return {
        "question": f"Qui est responsable de l'ouvrage {relation.ouvrage.nom_ouvrage} ?",
        "type": "qcm",
        "bonne_reponse": correct_name,
        "choix": _shuffle_choices(correct_name, distractors[:3]),
        "explication": "La bonne réponse vient de la table des responsabilités d'ouvrages actives.",
    }


GENERATOR_REGISTRY = {
    "generate_nombre_ouvrages_par_annee": generate_nombre_ouvrages_par_annee,
    "generate_points_eau_par_village": generate_points_eau_par_village,
    "generate_points_eau_par_ouvrage": generate_points_eau_par_ouvrage,
    "generate_ouvrages_par_responsable": generate_ouvrages_par_responsable,
    "generate_responsable_ouvrage": generate_responsable_ouvrage,
}
