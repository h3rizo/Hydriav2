import unicodedata

from apps.employees.models import FichePoste

EXPLICIT_REPAIR_TYPE_NAMES = {
    "reparation",
    "entretien",
    "maintenance",
    "nettoyage",
    "cloture",
    "maconnerie",
    "pmh",
    "protection bv",
}


def normalize_repair_text(value):
    text = (value or "").strip().lower()
    replacements = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "ä": "a",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return " ".join(text.split())


EXCLUDED_REPAIR_ACTIVITY_LABELS = {
    "trajet retour",
    "visite de l'ouvrage",
    "visite de l’ouvrage",
    "reunion technique mensuelle avec mi",
    "appui technique aux mi",
    "contre-visite mensuelle sur le terrain",
    "contre visite mensuelle sur le terrain",
    "ag fokonolona",
    "appui agent de maintenance",
    "au cas ou reparation",
    "collecte paiement volumetrique",
    "distribution des cartes sociales",
    "entretien avec les usagers pour comprendre les habitudes de consommation",
    "entretien candidat",
    "entretien des relations avec les communes rurales (maitres d'ouvrage)",
    "entretien des relations avec les communes rurales (maîtres d'ouvrage)",
    "informer et prevenir les usagers sur les activites realises",
    "livraison des pieces terrain au mi",
    "mis a jour cahiers fanarahamaso",
    "rectification om",
    "recuperation facture",
    "rencontre",
    "reparation bureau",
    "repos sur terrain",
    "suivi de la qualite du travail-social des ar et des agents de maintenance mixtes dans les cas particuliers - pilotage operationnel et qualite de la gestion",
    "suivi des depenses associees a l'entretien des motos",
}

EXCLUDED_REPAIR_ACTIVITY_PREFIXES = (
    "releve des compteurs",
    "distribution des factures selon les repartitions prevues",
    "reception client",
)

# These labels can receive variable suffixes (role, punctuation, etc.).
EXCLUDED_REPAIR_ACTIVITY_CONTAINS = (
    "entretien des relations avec les communes rurales",
)

NORMALIZED_EXCLUDED_REPAIR_ACTIVITY_LABELS = {
    normalize_repair_text(item).replace("’", "'")
    for item in EXCLUDED_REPAIR_ACTIVITY_LABELS
}
NORMALIZED_EXCLUDED_REPAIR_ACTIVITY_CONTAINS = tuple(
    normalize_repair_text(item).replace("’", "'")
    for item in EXCLUDED_REPAIR_ACTIVITY_CONTAINS
)


def is_excluded_repair_activity(activity_label):
    """Vrai pour une activité opérationnelle qui ne doit jamais compter comme réparation."""
    label = normalize_repair_text(activity_label).replace("’", "'")
    return (
        label in NORMALIZED_EXCLUDED_REPAIR_ACTIVITY_LABELS
        or label.startswith(EXCLUDED_REPAIR_ACTIVITY_PREFIXES)
        or any(fragment in label for fragment in NORMALIZED_EXCLUDED_REPAIR_ACTIVITY_CONTAINS)
    )


def get_repair_classification(type_name="", fiche_label="", remarque=""):
    normalized_type = normalize_repair_text(type_name)
    fallback_text = normalize_repair_text(f"{fiche_label} {remarque}")
    is_panne = "panne" in normalized_type or "panne" in fallback_text

    family = ""
    maintenance_keywords = ("entretien", "maintenance", "nettoyage")
    if any(keyword in normalized_type for keyword in maintenance_keywords):
        family = "reparation"
    elif "habilitation" in normalized_type and "preparation" not in normalized_type:
        family = "rehabilitation"
    elif normalized_type in EXPLICIT_REPAIR_TYPE_NAMES:
        family = "reparation"
    elif (
        "paration" in normalized_type
        and "preparation" not in normalized_type
        and "au cas ou" not in normalized_type
    ):
        family = "reparation"
    elif any(keyword in fallback_text for keyword in maintenance_keywords):
        family = "reparation"
    elif "habilitation" in fallback_text and "preparation" not in fallback_text:
        family = "rehabilitation"
    elif (
        "paration" in fallback_text
        and "preparation" not in fallback_text
        and "au cas ou" not in fallback_text
    ):
        family = "reparation"

    if not family and is_panne:
        family = "panne"

    return {
        "family": family,
        "is_panne": is_panne,
        "is_rehabilitation": family == "rehabilitation",
        "is_reparation": family == "reparation",
    }


def classify_repair_family(type_name="", fiche_label="", remarque=""):
    return get_repair_classification(
        type_name=type_name,
        fiche_label=fiche_label,
        remarque=remarque,
    )["family"]


def get_planning_repair_classification(planning):
    fiche_poste = getattr(planning, "fiche_poste", None)
    fiche_type = getattr(fiche_poste, "type_activites", None) if fiche_poste else None
    planning_type = getattr(planning, "type_activite", None)
    type_name = ""

    if fiche_type and getattr(fiche_type, "nomtype", None):
        type_name = fiche_type.nomtype
    elif planning_type and getattr(planning_type, "nomtype", None):
        type_name = planning_type.nomtype

    fiche_label = getattr(fiche_poste, "tache", "") if fiche_poste else ""
    remarque = getattr(planning, "remarque", "")
    return get_repair_classification(
        type_name=type_name,
        fiche_label=fiche_label,
        remarque=remarque,
    )


def get_planning_repair_family(planning):
    return get_planning_repair_classification(planning)["family"]


def is_installation_type(type_name):
    """Vrai pour le type d'activité « Installation » (le nom peut porter un suffixe)."""
    return "installation" in normalize_repair_text(type_name)


def is_remplacement_type(type_name):
    """Vrai pour le type d'activité « Remplacement » (le nom peut porter un suffixe)."""
    return "remplacement" in normalize_repair_text(type_name)


def get_repair_fiches_queryset(include_installation=False):
    """
    Fiches d'activité de réparation / réhabilitation / panne.

    include_installation=True ajoute les fiches des types « Installation » et « Remplacement ».
    Elles n'ont volontairement AUCUNE famille de réparation (classify_repair_family reste vide) :
    la notation des ouvrages et les évaluations, qui se basent sur la famille, ne les comptent
    donc pas comme des pannes.
    """
    candidate_fiches = list(
        FichePoste.objects
        .filter(type_activites__isnull=False)
        .select_related("type_activites")
    )

    repair_ids = []
    for fiche in candidate_fiches:
        if is_excluded_repair_activity(fiche.tache or ""):
            continue
        type_name = getattr(getattr(fiche, "type_activites", None), "nomtype", "")
        family = classify_repair_family(type_name=type_name, fiche_label=fiche.tache or "")
        if family in ("reparation", "rehabilitation", "panne"):
            repair_ids.append(fiche.id)
        elif include_installation and (
            is_installation_type(type_name) or is_remplacement_type(type_name)
        ):
            repair_ids.append(fiche.id)

    return FichePoste.objects.filter(id__in=repair_ids).select_related("type_activites")


def get_reparations_fiches_queryset():
    """Fiches gérées par la page « Suivi des réparations » : réparations, installations ET remplacements."""
    return get_repair_fiches_queryset(include_installation=True)


def is_works_operations_group(group_name):
    """Vrai pour le groupe « Opération(s) sur les ouvrages » (accents, casse et pluriel ignorés)."""
    name = normalize_repair_text(group_name)
    return name.startswith("operation") and "ouvrage" in name


def get_mobile_repair_fiches_queryset():
    """
    Activités proposées dans les réparations de l'app terrain (Android + Windows) :
    celles de la page « Suivi des réparations » (réparations, installations, remplacements)
    PLUS toutes les activités du groupe « Opérations sur les ouvrages » (ex. Construction),
    hors activités explicitement exclues des réparations.
    """
    ids = set(get_reparations_fiches_queryset().values_list("id", flat=True))
    for fiche in (FichePoste.objects.filter(type_activites__groupe__isnull=False)
                  .select_related("type_activites__groupe")):
        if is_excluded_repair_activity(fiche.tache or ""):
            continue
        if is_works_operations_group(fiche.type_activites.groupe.nom):
            ids.add(fiche.id)
    return FichePoste.objects.filter(id__in=ids).select_related("type_activites")


def get_repair_fiche_ids():
    return list(get_repair_fiches_queryset().values_list("id", flat=True))


def get_repair_fiche_family_map():
    mapping = {}
    for fiche in get_repair_fiches_queryset():
        mapping[str(fiche.id)] = classify_repair_family(
            type_name=getattr(getattr(fiche, "type_activites", None), "nomtype", ""),
            fiche_label=fiche.tache or "",
        )
    return mapping
