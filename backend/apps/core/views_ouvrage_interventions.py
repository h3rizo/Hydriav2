import json
import base64
import binascii
import os
import re
import tempfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlencode
from uuid import UUID

from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.cache.backends.filebased import FileBasedCache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Max, OuterRef, Prefetch, Q, Subquery, Sum
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.billing.models import PointEau, TypePointEau
from apps.core.views_mobile_auth import mobile_auth_required
from apps.core.models import (
    ExplicationDepassementIndemnite,
    RepairActivityEquipmentPolicy,
    RepairActivityPointTypePolicy,
)
from apps.employees.models import Employe, EmployeOuvrages, FichePoste
from apps.employees.permissions import is_directeur_poste
from apps.infrastructure.models import EquipementConstitutif, TypeEquipement
from apps.organization.models import Ouvrage
from apps.geography.models import Commune, District, Region
from apps.organization.scoping import (
    current_modalite_q,
    get_user_accessible_gestionnaire_ids,
    get_user_responsable_ouvrage_ids,
)
from apps.planning.doublons_reparations import calculer_doublons_securise
from apps.planning.reparation_composants import (
    ComposantsError,
    apply_repair_target,
    parse_composants_ids,
    regles_fiche,
    verifier_regles_fiche,
)
from apps.planning.models import Activite, DebitSourceMesure, Designation, Planning, PlanningDetail
from apps.planning.repair_classification import (
    get_planning_repair_classification,
    get_repair_fiche_family_map,
    get_repair_fiches_queryset,
    is_excluded_repair_activity,
    normalize_repair_text,
)


MAX_ATTACHMENTS = 20
MAX_ATTACHMENT_PAYLOAD = 45 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/3gpp",
    "video/mpeg",
    "video/ogg",
    "video/x-m4v",
    "video/x-msvideo",
    "video/x-matroska",
}
ALLOWED_INTERVENTION_EMPLOYEE_POSTES = (
    "Agent de maintenance",
    "Agent de recouvrement",
    "Agent de recouvrement Superviseur technique",
    "Superviseur technique",
    "Responsable opérationnel",
    "Responsable operationnel",
    "Directeur",
    "Mpikojakoja ifotony",
)

OUVRAGE_SCORE_EMPLOYEE_POSTES = (
    "Mpikojakoja Ifotony",
    "Superviseur technique",
    "Agent de maintenance",
)

ACTIVE_INTERVENTION_STATUSES = ("en_cours", "reporte")


def _calculate_ouvrage_contribution_score(score_rows):
    """Cinq points par ouvrage avec contribution et sans activité non terminée."""
    rows = list(score_rows)
    scored_ouvrages_count = sum(
        1 for row in rows
        if int(row.get("contribution_count") or 0) > 0
        and int(row.get("unfinished_count") or 0) == 0
    )
    max_points = len(rows) * 5
    points = scored_ouvrages_count * 5
    return {
        "points": points,
        "max_points": max_points,
        "percentage": round((points / max_points) * 100, 1) if max_points else 0,
        "scored_ouvrages_count": scored_ouvrages_count,
        "total_ouvrages_count": len(rows),
    }

OUVRAGE_CARD_CACHE = FileBasedCache(
    os.path.join(tempfile.gettempdir(), "hydria_ouvrage_card_cache"),
    {
        "TIMEOUT": None,
        "OPTIONS": {"MAX_ENTRIES": 30},
    },
)


def _has_photos(value):
    """Indique si un champ JSON de photos contient au moins une photo exploitable."""
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, str):
        return value.strip() not in {"", "[]", "{}", "null"}
    return False


def _format_relative_day_duration(value, reference_date=None):
    """Durée relative calendaire, arrondie au jour, en français."""
    if not value:
        return ""
    if isinstance(value, datetime):
        localized = timezone.localtime(value) if timezone.is_aware(value) else value
        value_date = localized.date()
    elif isinstance(value, date):
        value_date = value
    else:
        return ""

    reference_date = reference_date or timezone.localdate()
    day_delta = (value_date - reference_date).days
    if day_delta == 0:
        return "aujourd'hui"
    if day_delta == -1:
        return "hier"
    if day_delta == 1:
        return "demain"

    start_date, end_date = (
        (value_date, reference_date)
        if day_delta < 0
        else (reference_date, value_date)
    )
    delta = relativedelta(end_date, start_date)
    weeks, days = divmod(delta.days, 7)
    parts = []
    if delta.years:
        parts.append(f"{delta.years} an{'s' if delta.years > 1 else ''}")
    if delta.months:
        parts.append(f"{delta.months} mois")
    if weeks:
        parts.append(f"{weeks} semaine{'s' if weeks > 1 else ''}")
    if days:
        parts.append(f"{days} jour{'s' if days > 1 else ''}")
    if not parts:
        parts.append("1 jour")

    if len(parts) == 1:
        duration = parts[0]
    else:
        duration = ", ".join(parts[:-1]) + " et " + parts[-1]
    return f"il y a {duration}" if day_delta < 0 else f"dans {duration}"


def _active_intervention_employees(user):
    """Employes actifs autorises : meme base, ou toute l'organisation pour le Directeur."""
    actor = getattr(user, "employe", None)
    if not actor or not actor.base_id:
        return Employe.objects.none()

    queryset = Employe.objects.filter(
        date_debauchage__isnull=True,
    ).select_related("base", "base__organisation", "poste")
    allowed_postes = Q()
    for poste_name in ALLOWED_INTERVENTION_EMPLOYEE_POSTES:
        allowed_postes |= Q(poste__nom_poste__iexact=poste_name)
    queryset = queryset.filter(allowed_postes)
    if is_directeur_poste(user):
        return queryset.filter(base__organisation_id=actor.base.organisation_id)
    return queryset.filter(base_id=actor.base_id)


def _planning_attachments(raw_value):
    """Normalise les images et videos JSON jointes a une intervention."""
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []

    attachments = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            continue
        source = str(item.get("data") or item.get("url") or "").strip()
        content_type = str(item.get("type") or item.get("content_type") or "").lower()
        if source.startswith("data:"):
            source_type = source[5:].split(";", 1)[0].lower()
            content_type = source_type or content_type
        elif source.startswith(("http://", "https://", "/media/")):
            if content_type not in ALLOWED_ATTACHMENT_TYPES:
                content_type = "image/jpeg"
        elif source:
            if content_type not in ALLOWED_ATTACHMENT_TYPES:
                continue
            source = f"data:{content_type};base64,{source}"
        if not source or content_type not in ALLOWED_ATTACHMENT_TYPES:
            continue
        attachments.append({
            "data": source,
            "name": str(item.get("name") or f"Piece jointe {index}"),
            "type": content_type,
            "is_video": content_type.startswith("video/"),
        })
    return attachments

EQUIPMENT_TYPE_MATCH_STOPWORDS = {
    "autre", "equipement", "equipements", "installation", "systeme",
    "eau", "de", "du", "des", "la", "le", "les", "a",
}


def _activity_target_metadata(activity_label, equipment_types):
    """Infer explicit targets mentioned in an activity label."""
    normalized_label = normalize_repair_text(activity_label).replace("’", "'")
    point_eau_only = "point d'eau" in normalized_label or "point eau" in normalized_label
    equipment_type_ids = []

    for equipment_type in equipment_types:
        type_name = normalize_repair_text(equipment_type["nom_type"])
        significant_words = {
            word for word in type_name.replace("'", " ").split()
            if len(word) >= 4 and word not in EQUIPMENT_TYPE_MATCH_STOPWORDS
        }
        if type_name and (
            type_name in normalized_label
            or any(word in normalized_label.split() for word in significant_words)
        ):
            equipment_type_ids.append(str(equipment_type["id"]))

    return {
        "point_eau_only": point_eau_only,
        "equipment_type_ids": equipment_type_ids,
    }


def _activity_matches_target(metadata, target_type, equipment_type_id=None):
    equipment_type_ids = metadata["equipment_type_ids"]
    if target_type == "point_eau":
        return not equipment_type_ids
    if target_type == "equipement":
        return (
            not metadata["point_eau_only"]
            and (not equipment_type_ids or str(equipment_type_id or "") in equipment_type_ids)
        )
    return False


def _policy_text(value):
    normalized = normalize_repair_text(value).replace("’", "'")
    return " ".join(
        "".join(char if char.isalnum() else " " for char in normalized).split()
    )


def _is_pmh_ouvrage(ouvrage_type_name):
    normalized = _policy_text(ouvrage_type_name)
    return any(marker in normalized for marker in ("ppmh", "fpmh", "pmh"))


def _requires_signalement_date(activity_label):
    """La date de signalement est obligatoire pour l'activité Réparation panne."""
    return _policy_text(activity_label) == _policy_text("Réparation panne")


PMH_ACTIVITY_FRAGMENTS = tuple(map(_policy_text, (
    "Contrôle des travaux et paiement",
    "Diagnostique réparation",
    "Mise à jour des cahiers fanarahamaso",
    "Mis à jour cahiers fanarahamaso",
    "Prélèvement échantillon eau pour analyse",
    "Réception définitive",
    "Réception provisoire",
    "Réception technique",
    "Réhabilitation",
    "Réparation maçonnerie",
    "Réparation panne",
    "Réparation simple",
    "Travaux lourds sous la supervision du ST",
    "Passer de l'anti-rouille sur les fers",
)))

POINT_EAU_ACTIVITY_FRAGMENTS = tuple(map(_policy_text, (
    "Diagnostique réparation",
    "Réparation fuite",
    "Réparation maçonnerie",
    "Réparation panne",
    "Réparation : Réamenagement BF",
    "Réparation : Remplacement des robinets, manchons, vanne d'arrêt",
    "Réparation simple",
    "Travaux lourds sous la supervision du ST",
    "Entretien et réparation évacuation BF",
    "Installation kiosques, BP",
    "Passer de l'anti-rouille sur les fers",
)))

CAPTAGE_ACTIVITY_FRAGMENTS = tuple(map(_policy_text, (
    "Entretien clôture",
    "Nettoyage des citernes et boîtes",
    "Diagnostique réparation",
    "Réhabilitation",
    "Réparation maçonnerie",
    "Réparation panne",
    "Réparation simple",
    "Suivi des travaux effectués par IA",
    "Travaux lourds sous la supervision du ST",
    "Vérification débit",
    "Vérification de la maintenance, propreté et état des ouvrages avec l'aide du cahier Fanarahamaso",
    "Passer de l'anti-rouille sur les fers",
    "Protection BV",
    "Réception provisoire",
    "Réception technique",
)))

ADDUCTION_DISTRIBUTION_ACTIVITY_FRAGMENTS = tuple(map(_policy_text, (
    "Diagnostique réparation",
    "Enterrement des tuyaux",
    "Réparation : Suppression des bulles d'air",
    "Réparation fuites",
    "Réparation panne",
    "Suivi des travaux effectués par IA",
    "Travaux lourds sous la supervision du ST",
    "Vérification de la maintenance, propreté et état des ouvrages avec l'aide du cahier Fanarahamaso",
)))

BRISE_CHARGE_ACTIVITY_FRAGMENTS = tuple(map(_policy_text, (
    "Diagnostique réparation",
    "Nettoyage des citernes et boîtes",
    "Réhabilitation",
    "Réparation maçonnerie",
    "Réparation panne",
    "Réparation simple",
    "Suivi des travaux effectués par IA",
    "Travaux lourds sous la supervision du ST",
    "Vérification débit",
    "Vérification de la maintenance, propreté et état des ouvrages avec l'aide du cahier Fanarahamaso",
    "Passer de l'anti-rouille sur les fers",
)))

EXPLICIT_QUICK_REPAIR_ACTIVITY_FRAGMENTS = tuple(set(
    PMH_ACTIVITY_FRAGMENTS
    + POINT_EAU_ACTIVITY_FRAGMENTS
    + CAPTAGE_ACTIVITY_FRAGMENTS
    + ADDUCTION_DISTRIBUTION_ACTIVITY_FRAGMENTS
    + BRISE_CHARGE_ACTIVITY_FRAGMENTS
))


def _matches_activity_fragments(activity_label, fragments):
    normalized = _policy_text(activity_label)
    return any(fragment in normalized for fragment in fragments)


def _get_quick_repair_fiches_queryset():
    """Include repair fiches plus explicitly authorized operational activities."""
    repair_ids = set(get_repair_fiches_queryset().values_list("id", flat=True))
    explicit_ids = []
    for fiche in FichePoste.objects.filter(type_activites__isnull=False).only("id", "tache"):
        if is_excluded_repair_activity(fiche.tache or ""):
            continue
        activity = _policy_text(fiche.tache or "")
        if (
            "pmh" in activity
            or "captage" in activity
            or _matches_activity_fragments(activity, EXPLICIT_QUICK_REPAIR_ACTIVITY_FRAGMENTS)
        ):
            explicit_ids.append(fiche.id)

    return (
        FichePoste.objects
        .filter(id__in=repair_ids.union(explicit_ids))
        .select_related("type_activites")
    )


def _activity_allowed_for_target(
    activity_label,
    ouvrage_type_name,
    target_type,
    equipment_type_name="",
    equipment_type_id=None,
    fallback_metadata=None,
):
    """Apply the repair activity policy for an ouvrage and its selected target."""
    activity = _policy_text(activity_label)
    is_pmh = _is_pmh_ouvrage(ouvrage_type_name)

    if "pmh" in activity and not is_pmh:
        return False
    if is_pmh:
        if "citerne" in activity:
            return False
        return target_type == "point_eau" and (
            "pmh" in activity or _matches_activity_fragments(activity, PMH_ACTIVITY_FRAGMENTS)
        )
    if target_type == "point_eau":
        return _matches_activity_fragments(activity, POINT_EAU_ACTIVITY_FRAGMENTS)
    if target_type != "equipement":
        return False

    equipment_type = _policy_text(equipment_type_name)
    if "captage" in equipment_type:
        return "captage" in activity or _matches_activity_fragments(activity, CAPTAGE_ACTIVITY_FRAGMENTS)
    if "adduction" in equipment_type or "distribution" in equipment_type:
        return _matches_activity_fragments(activity, ADDUCTION_DISTRIBUTION_ACTIVITY_FRAGMENTS)
    if any(name in equipment_type for name in ("brise charge", "regard", "repartiteur", "dessableur")):
        return _matches_activity_fragments(activity, BRISE_CHARGE_ACTIVITY_FRAGMENTS)

    return _activity_matches_target(fallback_metadata or {
        "point_eau_only": False,
        "equipment_type_ids": [],
    }, target_type, equipment_type_id)


def _is_staff_user(user):
    return bool(user.is_authenticated and (user.is_staff or user.is_superuser))


def _quick_point_eau_label(point):
    idxls = _formatted_point_eau_idxls(point)
    subscriber_name = str(getattr(point, "nomabonne", "") or "").strip()
    if idxls and subscriber_name:
        return f"{idxls} — {subscriber_name}"
    return idxls or subscriber_name or str(getattr(point, "code_point_eau", "") or point.id)


def _formatted_point_eau_idxls(point):
    raw_idxls = str(getattr(point, "idxls", "") or "").strip()
    if not raw_idxls:
        return ""
    without_prefix = re.sub(r"^\s*idx(?:ls?|l)?[\s:#_-]*", "", raw_idxls, flags=re.IGNORECASE)
    number_match = re.search(r"\d+", without_prefix)
    if number_match:
        return f"{int(number_match.group()):02d}"
    return without_prefix.strip()


def _quick_point_eau_sort_key(point):
    formatted_idxls = _formatted_point_eau_idxls(point)
    if formatted_idxls.isdigit():
        idxls_key = (0, int(formatted_idxls))
    elif formatted_idxls:
        idxls_key = (1, formatted_idxls.casefold())
    else:
        idxls_key = (2, "")
    return (*idxls_key, str(getattr(point, "nomabonne", "") or "").casefold())


@login_required
@user_passes_test(_is_staff_user)
def repair_activity_equipment_permissions(request):
    """Manage allowed repair activities by equipment or water-point type."""
    target_kind = request.POST.get("target_kind") or request.GET.get("target") or "equipement"
    if target_kind == "point_eau":
        target_types = list(TypePointEau.objects.filter(actif=True).order_by("nom_type"))
        policy_model = RepairActivityPointTypePolicy
        policy_field = "type_point_eau"
        target_label = "point d'eau"
    else:
        target_kind = "equipement"
        target_types = list(TypeEquipement.objects.filter(is_active=True).order_by("nom_type"))
        policy_model = RepairActivityEquipmentPolicy
        policy_field = "type_equipement"
        target_label = "équipement"

    selected_type_id = request.POST.get("target_type_id") or request.GET.get("type")
    selected_type = next(
        (item for item in target_types if str(item.id) == str(selected_type_id)),
        target_types[0] if target_types else None,
    )

    candidates = list(
        _get_quick_repair_fiches_queryset()
        .order_by("type_activites__nomtype", "tache")
    )
    candidate_ids = {str(fiche.id) for fiche in candidates}
    policy = None

    if selected_type:
        policy = (
            policy_model.objects
            .filter(**{policy_field: selected_type})
            .prefetch_related("allowed_activities")
            .first()
        )

    if request.method == "POST" and selected_type:
        action = request.POST.get("action", "save")
        if action == "reset":
            if policy:
                policy.delete()
            messages.success(
                request,
                f"Les règles initiales ont été restaurées pour {selected_type.nom_type}.",
            )
        else:
            selected_ids = [
                activity_id
                for activity_id in request.POST.getlist("activities")
                if activity_id in candidate_ids
            ]
            policy, _ = policy_model.objects.get_or_create(
                **{policy_field: selected_type},
            )
            policy.allowed_activities.set(selected_ids)
            policy.updated_by = request.user
            policy.save(update_fields=["updated_by", "updated_at"])
            messages.success(
                request,
                f"{len(selected_ids)} activité(s) autorisée(s) pour {selected_type.nom_type}.",
            )

        query = urlencode({"target": target_kind, "type": str(selected_type.id)})
        return redirect(f"{reverse('core:repair_activity_equipment_permissions')}?{query}")

    if policy:
        selected_activity_ids = set(policy.allowed_activities.values_list("id", flat=True))
    elif selected_type:
        selected_activity_ids = set()
        equipment_type_values = [
            {"id": item.id, "nom_type": item.nom_type}
            for item in target_types
        ] if target_kind == "equipement" else []
        for fiche in candidates:
            if target_kind == "point_eau":
                is_allowed = _activity_allowed_for_target(
                    fiche.tache or "",
                    "AEPG",
                    "point_eau",
                )
            else:
                metadata = _activity_target_metadata(fiche.tache or "", equipment_type_values)
                is_allowed = _activity_allowed_for_target(
                    fiche.tache or "",
                    "AEPG",
                    "equipement",
                    selected_type.nom_type,
                    selected_type.id,
                    metadata,
                )
            if is_allowed:
                selected_activity_ids.add(fiche.id)
    else:
        selected_activity_ids = set()

    activity_groups = []
    for fiche in candidates:
        group_label = fiche.type_activites.nomtype if fiche.type_activites else "Sans type"
        if not activity_groups or activity_groups[-1]["label"] != group_label:
            activity_groups.append({"label": group_label, "activities": []})
        activity_groups[-1]["activities"].append(fiche)

    return render(request, "core/repair_activity_equipment_permissions.html", {
        "title": "Activités permises par type de cible",
        "target_kind": target_kind,
        "target_label": target_label,
        "target_types": target_types,
        "selected_type": selected_type,
        "activity_groups": activity_groups,
        "selected_activity_ids": selected_activity_ids,
        "is_customized": policy is not None,
        "policy": policy,
    })


def _accessible_ouvrages(user, include_other_bases=False):
    """Ouvrages à modalité non expirée de l'organisation et périmètre responsable."""
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    modalite_filters = {
        "modalites_gestion__gestionnaire__isnull": False,
    }
    if gestionnaire_ids is not None and not gestionnaire_ids:
        return Ouvrage.objects.none()
    if gestionnaire_ids is not None:
        # Meme jointure : la modalite non expiree appartient a CETTE organisation.
        modalite_filters["modalites_gestion__gestionnaire_id__in"] = gestionnaire_ids

    ouvrages = Ouvrage.objects.filter(**modalite_filters).filter(
        current_modalite_q('modalites_gestion')
    )

    if not include_other_bases:
        responsable_ids = get_user_responsable_ouvrage_ids(user)
        if responsable_ids is not None:
            ouvrages = ouvrages.filter(id__in=responsable_ids)

    return ouvrages.distinct()


def _accessible_intervention_ouvrages(user, include_other_bases=False):
    """Perimetre historique sans transformer un contrat futur en affectation.

    Les ouvrages actuellement geres restent accessibles. On ajoute uniquement
    les ouvrages ayant deja une publication de reparation saisie par un
    employe d'une organisation autorisee. Cette extension sert aux pages et
    widgets d'historique, jamais aux compteurs d'ouvrages affectes.
    """
    current_ids = _accessible_ouvrages(
        user,
        include_other_bases=include_other_bases,
    ).values_list('id', flat=True)
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    historical = Planning.objects.filter(
        fiche_poste_id__in=_get_quick_repair_fiches_queryset().values_list('id', flat=True),
        ouvrage_id__isnull=False,
    )
    if gestionnaire_ids is not None:
        if not gestionnaire_ids:
            historical = historical.none()
        else:
            historical = historical.filter(
                employe__base__organisation_id__in=gestionnaire_ids,
            )
    return Ouvrage.objects.filter(
        Q(id__in=current_ids)
        | Q(id__in=historical.values_list('ouvrage_id', flat=True))
    ).distinct()


def _intervention_statistics(plannings):
    """Statistiques des interventions accessibles ayant au moins une photo."""
    now = timezone.localtime(timezone.now())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    # Planning.photo est un texte JSON. Les deux conditions couvrent les
    # pièces jointes normalisées et les anciennes images stockées en data URL.
    photo_plannings = plannings.filter(
        Q(photo__iregex=r'"type"\s*:\s*"image/')
        | Q(photo__icontains="data:image/")
    )

    def top_contributors(queryset):
        rows = (
            queryset
            .filter(employe_id__isnull=False)
            .values(
                "employe_id",
                "employe__surnom",
                "employe__prenom",
                "employe__nom",
                "employe__nom_employe",
            )
            .annotate(contribution_count=Count("id"))
            .order_by(
                "-contribution_count",
                "employe__surnom",
                "employe__prenom",
                "employe__nom",
            )[:5]
        )
        contributors = []
        for row in rows:
            full_name = " ".join(filter(None, [
                row["employe__prenom"],
                row["employe__nom"],
            ])).strip()
            contributors.append({
                "id": row["employe_id"],
                "label": (
                    row["employe__surnom"]
                    or full_name
                    or row["employe__nom_employe"]
                    or "Employe sans nom"
                ),
                "count": row["contribution_count"],
            })
        return contributors

    repair_or_rehabilitation_fiche_ids = [
        fiche_id
        for fiche_id, family in get_repair_fiche_family_map().items()
        if family in {"reparation", "rehabilitation"}
    ]

    def top_ouvrages(queryset):
        rows = (
            queryset
            .filter(
                ouvrage_id__isnull=False,
                fiche_poste_id__in=repair_or_rehabilitation_fiche_ids,
            )
            .values("ouvrage_id", "ouvrage__nom_ouvrage")
            .annotate(contribution_count=Count("id"))
            .order_by("-contribution_count", "ouvrage__nom_ouvrage")[:5]
        )
        return [
            {
                "id": row["ouvrage_id"],
                "label": row["ouvrage__nom_ouvrage"] or "Ouvrage sans nom",
                "count": row["contribution_count"],
            }
            for row in rows
        ]

    current_month_plannings = photo_plannings.filter(created_at__gte=month_start)
    current_year_plannings = photo_plannings.filter(created_at__gte=year_start)
    updated_ouvrage_count = (
        photo_plannings
        .filter(updated_at__gte=month_start, ouvrage_id__isnull=False)
        .values("ouvrage_id")
        .distinct()
        .count()
    )
    return {
        "month_start": month_start,
        "year_start": year_start,
        "current_year": now.year,
        "updated_ouvrage_count": updated_ouvrage_count,
        "month_contribution_count": current_month_plannings.count(),
        "year_contribution_count": current_year_plannings.count(),
        "month_contributors": top_contributors(current_month_plannings),
        "year_contributors": top_contributors(current_year_plannings),
        "month_ouvrages": top_ouvrages(current_month_plannings),
        "year_ouvrages": top_ouvrages(current_year_plannings),
    }


def _annual_diamex_totals_by_ouvrage(annee):
    """Montants encaisses par ouvrage, avec les memes sources que les dashboards."""
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
    from apps.accounting.models import BaseDiameX
    from apps.accounting.views_verification_ouvrages import diviser_paiement_volume_multi

    volume_source = BaseDiameX.objects.filter(
        compte_code="707401",
        montant_in__gt=0,
    )
    forfait_source = BaseDiameX.objects.filter(
        compte_code="748411",
        date_m__year=annee,
        montant_in__gt=0,
    )
    volume_fingerprint = volume_source.aggregate(
        count=Count("id"), max_id=Max("id"), total=Sum("montant_in")
    )
    forfait_fingerprint = forfait_source.aggregate(
        count=Count("id"), max_id=Max("id"), total=Sum("montant_in")
    )
    cache_key = (
        f"diamex-v2-{annee}-"
        f"{volume_fingerprint['count']}-{volume_fingerprint['max_id']}-"
        f"{volume_fingerprint['total']}-"
        f"{forfait_fingerprint['count']}-{forfait_fingerprint['max_id']}-"
        f"{forfait_fingerprint['total']}"
    )
    cached_totals = OUVRAGE_CARD_CACHE.get(cache_key)
    if cached_totals is not None:
        return {
            str(ouvrage_id): Decimal(str(montant or 0))
            for ouvrage_id, montant in cached_totals.items()
        }

    totals = defaultdict(lambda: Decimal("0.00"))

    # Forfaitaire : le dashboard rattache l'encaissement a l'annee du mouvement.
    forfait_entries = forfait_source.only("description", "compte_code", "montant_in")
    for entry in forfait_entries.iterator(chunk_size=500):
        extraction = extraire_ouvrage_et_mois_generique(
            entry.description or "", entry.compte_code
        )
        ouvrage_obj = extraction.get("ouvrage_obj") if extraction else None
        if ouvrage_obj:
            totals[str(ouvrage_obj.id)] += Decimal(str(entry.montant_in or 0))

    # Volume : l'annee et le mois de facturation sont extraits du libelle DiameX.
    volume_entries = volume_source.only("description", "compte_code", "montant_in")
    for entry in volume_entries.iterator(chunk_size=500):
        segments = []
        if entry.description and ";" in entry.description:
            segments = diviser_paiement_volume_multi(
                entry.description,
                entry.compte_code,
                entry.montant_in or 0,
            )

        if segments:
            for segment in segments:
                extraction = segment.get("extraction") or {}
                ouvrage_obj = extraction.get("ouvrage_obj")
                if ouvrage_obj and extraction.get("annee") == annee:
                    totals[str(ouvrage_obj.id)] += Decimal(
                        str(segment.get("montant") or 0)
                    )
            continue

        extraction = extraire_ouvrage_et_mois_generique(
            entry.description or "", entry.compte_code
        )
        ouvrage_obj = extraction.get("ouvrage_obj") if extraction else None
        if ouvrage_obj and extraction.get("annee") == annee:
            totals[str(ouvrage_obj.id)] += Decimal(str(entry.montant_in or 0))

    serializable_totals = {
        ouvrage_id: str(montant) for ouvrage_id, montant in totals.items()
    }
    OUVRAGE_CARD_CACHE.set(cache_key, serializable_totals, timeout=None)
    return dict(totals)


COMPTE_INDEMNITES_RBF = "621102"


def _can_see_indemnities(user):
    """Les indemnites nomment des beneficiaires : reservees aux utilisateurs internes (pas aux comptes clients)."""
    return not bool(getattr(user, "client", None)) or user.is_staff


def _indemnity_point_id(extraction, ouvrage_obj, sole_point_cache=None):
    """
    Id du point d'eau visé par un libelle d'indemnite (chaine vide si inconnu) -> (id point, IDXLS lu).

    L'extracteur retombe sur "le premier point d'eau de l'ouvrage" quand l'IDXLS du libelle n'existe pas :
    on ne retient le point que s'il correspond a l'IDXLS lu, ou s'il est le seul possible (libelle sans IDXLS).
    """
    point_obj = extraction.get("point_eau_obj")
    idxls = str(extraction.get("point_eau_idxls") or "").strip()
    if not point_obj:
        return "", idxls
    if idxls:
        return (str(point_obj.id) if str(getattr(point_obj, "idxls", "") or "").strip() == idxls else ""), idxls
    cache = sole_point_cache if sole_point_cache is not None else {}
    if ouvrage_obj.id not in cache:
        # Vrai si l'ouvrage n'a qu'un seul point d'eau susceptible de recevoir une indemnite (BF / PMH / PMHI).
        from apps.accounting.resolution_memoire import nombre_points_indemnite

        actif, nombre = nombre_points_indemnite(ouvrage_obj.id)
        if actif:
            cache[ouvrage_obj.id] = nombre == 1
        else:
            cache[ouvrage_obj.id] = PointEau.objects.filter(
                ouvrage_id=ouvrage_obj.id, type_point_eau__nom_type__in=["BF", "PMH", "PMHI"]).count() == 1
    return (str(point_obj.id) if cache[ouvrage_obj.id] else ""), idxls


def _descriptions_digest(source):
    """
    Condensé des libellés d'un queryset BaseDiameX, pour la clé de cache : corriger un libellé ne change ni le
    nombre de lignes, ni le dernier id, ni le total, mais change le rattachement à l'ouvrage / au point d'eau.
    """
    import hashlib

    digest = hashlib.md5()
    for entry_id, description in source.order_by("id").values_list("id", "description").iterator(chunk_size=2000):
        digest.update(f"{entry_id}\x1f{description or ''}\x1e".encode("utf-8"))
    return digest.hexdigest()[:16]


def _rbf_indemnity_lines_by_ouvrage():
    """
    Lignes d'indemnites payees (compte 621102, sorties) rattachees a chaque ouvrage :
    {ouvrage_id: [(id de la ligne BaseDiameX, type "RBF"|"BF"|"PPMH"|"Autre", annee du mouvement, Decimal,
                   id du point d'eau ("" si inconnu), IDXLS lu dans le libelle ("" si absent))]}.

    L'ouvrage est retrouve dans le libelle DiameX comme sur les autres pages comptables ; l'annee est celle du
    libelle ("Indemnite RBF2 2025") quand elle y figure, sinon celle du mouvement (date_m). Les lignes dont l'ouvrage n'est pas reconnu (ou ambigu) ne sont rattachees a aucun ouvrage.
    """
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
    from apps.accounting.indemnites_points import annee_exercice
    from apps.accounting.models import BaseDiameX

    source = BaseDiameX.objects.filter(compte_code=COMPTE_INDEMNITES_RBF, montant_out__gt=0)
    fingerprint = source.aggregate(count=Count("id"), max_id=Max("id"), total=Sum("montant_out"))
    cache_key = (
        f"indemnites-rbf-v7-{fingerprint['count']}-{fingerprint['max_id']}-{fingerprint['total']}"
        f"-{_descriptions_digest(source)}"
    )
    cached = OUVRAGE_CARD_CACHE.get(cache_key)
    if cached is not None:
        return {
            ouvrage_id: [(int(i), kind, year, Decimal(amount), point_id, idxls)
                         for i, kind, year, amount, point_id, idxls in rows]
            for ouvrage_id, rows in cached.items()
        }

    lines = defaultdict(list)
    sole_point_cache = {}

    # Chaque libellé était résolu par plusieurs requêtes (ouvrage, alias, point d'eau) :
    # sur un journal réel, l'index complet prenait plus de dix minutes. Les référentiels
    # sont désormais chargés une fois et résolus en mémoire.
    from apps.accounting.resolution_memoire import resolution_memoire

    with resolution_memoire():
        for entry in source.only("description", "compte_code", "montant_out", "date_m").iterator(chunk_size=500):
            extraction = extraire_ouvrage_et_mois_generique(entry.description or "", entry.compte_code)
            if isinstance(extraction, list):
                # Ligne multi-ouvrages : la repartition du montant est inconnue, on ne devine pas.
                continue
            ouvrage_obj = (extraction or {}).get("ouvrage_obj")
            if not ouvrage_obj:
                continue
            kind = (extraction.get("type_indemnite") or "Autre")
            # Annee d'exercice : celle du libelle quand elle differe de la date compta (indemnite de 2025 payee en 2026).
            year = annee_exercice(entry.description, entry.date_m.year if entry.date_m else None)
            point_id, idxls = _indemnity_point_id(extraction, ouvrage_obj, sole_point_cache)
            lines[str(ouvrage_obj.id)].append((
                entry.id, kind, year, Decimal(str(entry.montant_out or 0)), point_id, idxls,
            ))

    OUVRAGE_CARD_CACHE.set(cache_key, {
        ouvrage_id: [[i, kind, year, str(amount), point_id, idxls] for i, kind, year, amount, point_id, idxls in rows]
        for ouvrage_id, rows in lines.items()
    }, timeout=None)
    return dict(lines)


COMPTE_PAIEMENT_FORFAITAIRE = "748411"


def _forfait_receipt_lines_by_ouvrage(year):
    """
    Encaissements forfaitaires (compte 748411, entrees) de l'annee, rattaches a chaque ouvrage par le libelle DiameX :
    {ouvrage_id: [(id de la ligne BaseDiameX, "AAAA-MM-JJ", Decimal)]}. Meme source que « Collecte » des cartes.
    Le libelle forfaitaire ne nomme pas le point d'eau : le rapprochement avec les indemnites se fait par ouvrage et par mois.
    """
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
    from apps.accounting.models import BaseDiameX

    source = BaseDiameX.objects.filter(compte_code=COMPTE_PAIEMENT_FORFAITAIRE, date_m__year=year, montant_in__gt=0)
    fingerprint = source.aggregate(count=Count("id"), max_id=Max("id"), total=Sum("montant_in"))
    cache_key = (
        f"forfait-recus-v2-{year}-{fingerprint['count']}-{fingerprint['max_id']}-{fingerprint['total']}"
        f"-{_descriptions_digest(source)}"
    )
    cached = OUVRAGE_CARD_CACHE.get(cache_key)
    if cached is not None:
        return {
            ouvrage_id: [(int(i), day, Decimal(amount)) for i, day, amount in rows]
            for ouvrage_id, rows in cached.items()
        }

    lines = defaultdict(list)
    from apps.accounting.resolution_memoire import resolution_memoire

    with resolution_memoire():
        for entry in source.only("description", "compte_code", "montant_in", "date_m").iterator(chunk_size=500):
            extraction = extraire_ouvrage_et_mois_generique(entry.description or "", entry.compte_code)
            if isinstance(extraction, list):
                continue
            ouvrage_obj = (extraction or {}).get("ouvrage_obj")
            if not ouvrage_obj:
                continue
            lines[str(ouvrage_obj.id)].append((
                entry.id, entry.date_m.isoformat()[:10] if entry.date_m else "", Decimal(str(entry.montant_in or 0)),
            ))

    OUVRAGE_CARD_CACHE.set(cache_key, {
        ouvrage_id: [[i, day, str(amount)] for i, day, amount in rows] for ouvrage_id, rows in lines.items()
    }, timeout=None)
    return dict(lines)


def _rbf_groups_by_point(year, rows, year_lines):
    """
    Indemnites de l'annee regroupees par point d'eau (deja identifie par l'extraction du libelle), avec en regard
    les paiements forfaitaires POINTES (numero + base DiameX renseignes) de ce meme point d'eau, factures dans l'annee.
    `rows` : lignes serialisees du modal ; `year_lines` : tuples de `_rbf_indemnity_lines_by_ouvrage`.
    """
    from apps.billing.models import PaiementForfaitaire

    meta = {line[0]: (line[4], line[5]) for line in year_lines}     # id ligne -> (id point, IDXLS lu)
    groups = {}
    for row in rows:
        point_id, idxls = meta.get(row["id"], ("", ""))
        key = point_id or (f"idxls:{idxls}" if idxls else "aucun")
        group = groups.setdefault(key, {
            "key": key, "point_id": point_id, "idxls": idxls, "rbf_rows": [], "rbf_total": Decimal("0.00")})
        group["rbf_rows"].append(row)
        group["rbf_total"] += Decimal(str(row["amount"]))

    point_ids = [group["point_id"] for group in groups.values() if group["point_id"]]
    points = {str(point.id): point for point in
              PointEau.objects.filter(id__in=point_ids).select_related("type_point_eau")}
    pointed, unpointed = defaultdict(list), defaultdict(list)
    for paiement in PaiementForfaitaire.objects.filter(
        point_eau_id__in=point_ids, date_facture__year=year, montant__gt=0,
    ).order_by("date_facture", "id"):
        is_pointed = bool(str(paiement.numeroDiameX or "").strip() and str(paiement.baseDiameX or "").strip())
        (pointed if is_pointed else unpointed)[str(paiement.point_eau_id)].append(paiement)

    result = []
    for key, group in groups.items():
        point = points.get(group["point_id"])
        forfaits = pointed.get(group["point_id"], [])
        forfait_total = sum((Decimal(str(p.montant)) for p in forfaits), Decimal("0.00"))
        if point:
            label = _quick_point_eau_label(point)
            sort_key = (0, *_quick_point_eau_sort_key(point))
        elif group["idxls"]:
            label = f"IDXLS {group['idxls']} (point d'eau introuvable)"
            sort_key = (1, 0, group["idxls"], "")
        else:
            label, sort_key = "Point d'eau non identifié dans le libellé", (2, 0, "", "")
        if not group["point_id"]:
            status = "unlinked"
        elif not forfaits:
            status = "no_forfait"
        elif group["rbf_total"] > forfait_total:
            status = "over"
        else:
            status = "ok"
        result.append((sort_key, {
            "key": key,
            "label": label,
            "type": point.type_point_eau.nom_type if point and point.type_point_eau else "",
            "status": status,
            "rbf_total": float(group["rbf_total"]),
            "forfait_total": float(forfait_total),
            "gap": float(forfait_total - group["rbf_total"]),
            "rbf_rows": group["rbf_rows"],
            "forfaits": [{
                "id": str(p.id),
                "date_facture": p.date_facture.isoformat(),
                "date_paiement": p.date_paiement.isoformat() if p.date_paiement else "",
                "quantite": p.quantite,
                "amount": float(p.montant),
                "numero_diamex": str(p.numeroDiameX or "").strip(),
                "base_diamex": str(p.baseDiameX or "").strip(),
            } for p in forfaits],
            "unpointed_count": len(unpointed.get(group["point_id"], [])),
            "unpointed_total": float(sum((Decimal(str(p.montant)) for p in unpointed.get(group["point_id"], [])),
                                         Decimal("0.00"))),
        }))
    return [item for _, item in sorted(result, key=lambda pair: pair[0])]


def _rbf_year_summary(lines, year):
    """
    Lignes d'un ouvrage -> (total de l'annee, ventilation par type triee par montant decroissant, lignes de l'annee).
    """
    year_lines = [line for line in lines if line[2] == year]
    total = sum((line[3] for line in year_lines), Decimal("0.00"))
    by_type = defaultdict(lambda: Decimal("0.00"))
    for line in year_lines:
        by_type[line[1]] += line[3]
    ordered = sorted(({"type": kind, "amount": amount} for kind, amount in by_type.items()),
                     key=lambda item: -item["amount"])
    return total, ordered, year_lines


# Plafond des indemnites RBF : 40 000 Ar par point d'eau public et par an ; au-dela, une explication est demandee.
PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC = Decimal("40000")
EXPLICATION_LONGUEUR_MIN = 10
EXPLICATION_LONGUEUR_MAX = 2000


def _public_points_by_ouvrage(ouvrage_ids):
    """
    Nombre de points d'eau publics par ouvrage : branches, hors branchements prives / BP, non arretes.
    Meme definition que l'analyse des couts par ouvrage (apps.accounting.services.analyse_couts_ouvrages).
    """
    rows = (
        PointEau.objects.filter(ouvrage_id__in=list(ouvrage_ids), datebranchement__isnull=False)
        .exclude(type_point_eau__nom_type__icontains="priv\u00e9")
        .exclude(type_point_eau__nom_type__icontains="prive")
        .exclude(type_point_eau__nom_type__iexact="bp")
        .exclude(datearretbranchement__isnull=False)
        .order_by()
        .values("ouvrage_id")
        .annotate(total=Count("id"))
    )
    return {str(row["ouvrage_id"]): int(row["total"]) for row in rows}


def _latest_explanations(ouvrage_ids, year):
    """Derniere explication de chaque ouvrage pour l'annee : {ouvrage_id: ExplicationDepassementIndemnite}."""
    latest = {}
    for explanation in ExplicationDepassementIndemnite.objects.filter(
        ouvrage_id__in=list(ouvrage_ids), annee=year,
    ).select_related("created_by").order_by("-created_at"):
        latest.setdefault(str(explanation.ouvrage_id), explanation)
    return latest


def _rbf_cap_status(total, public_points, explanation):
    """
    Situation d'un ouvrage face au plafond. Une explication ne couvre le depassement que tant que le montant paye
    n'a pas augmente depuis sa saisie.
    """
    cap = PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC * public_points
    over = total > cap
    explained = bool(over and explanation and explanation.montant_paye >= total)
    return {
        "per_point": PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC,
        "public_points": public_points,
        "cap": cap,
        "over": over,
        "excess": max(total - cap, Decimal("0.00")),
        "explained": explained,
        "needs_explanation": over and not explained,
        "explanation": explanation if explained else None,
    }


def _rbf_cap_by_ouvrage(ouvrage_ids, year, indemnity_lines):
    """{ouvrage_id: {"total", "by_type", "year_lines", **_rbf_cap_status}} pour les ouvrages demandes."""
    ids = [str(ouvrage_id) for ouvrage_id in ouvrage_ids]
    points = _public_points_by_ouvrage(ids)
    explanations = _latest_explanations(ids, year)
    result = {}
    for ouvrage_id in ids:
        total, by_type, year_lines = _rbf_year_summary(indemnity_lines.get(ouvrage_id, []), year)
        result[ouvrage_id] = {
            "total": total, "by_type": by_type, "year_lines": year_lines,
            **_rbf_cap_status(total, points.get(ouvrage_id, 0), explanations.get(ouvrage_id)),
        }
    return result


# Les depassements sont suivis sur plusieurs annees a la fois : annee en cours + les precedentes de cette fenetre.
RBF_ANNEES_SUIVIES = 3


def _rbf_tracked_years(today_year=None):
    """Annees suivies, de la plus recente a la plus ancienne."""
    current = today_year or timezone.localdate().year
    return [current - offset for offset in range(RBF_ANNEES_SUIVIES)]


def _rbf_cap_statuses_by_year(ouvrage_ids, years, lines=None):
    """{annee: {ouvrage_id: statut}} pour les ouvrages ayant au moins un paiement cette annee-la."""
    lines = lines if lines is not None else _rbf_indemnity_lines_by_ouvrage()
    result = {}
    for year in years:
        paid = [
            str(ouvrage_id) for ouvrage_id in ouvrage_ids
            if any(line[2] == year for line in lines.get(str(ouvrage_id), []))
        ]
        result[year] = _rbf_cap_by_ouvrage(paid, year, lines) if paid else {}
    return result


def _rbf_over_cap_ouvrage_ids(ouvrage_ids, years):
    """
    (ids en depassement, ids en depassement sans explication valable) parmi `ouvrage_ids`, sur une annee ou sur
    plusieurs : un ouvrage compte des qu'il depasse le plafond une seule de ces annees.
    """
    years = [years] if isinstance(years, int) else list(years)
    over, unexplained = set(), set()
    for statuses in _rbf_cap_statuses_by_year(ouvrage_ids, years).values():
        for oid, status in statuses.items():
            if status["over"]:
                over.add(oid)
                if status["needs_explanation"]:
                    unexplained.add(oid)
    return over, unexplained


def _rbf_past_year_alerts(ouvrage_ids, current_year):
    """{ouvrage_id: [{year, total, excess, explained}]} : depassements des annees precedentes suivies."""
    years = [y for y in _rbf_tracked_years(current_year) if y != current_year]
    alerts = defaultdict(list)
    for year, statuses in _rbf_cap_statuses_by_year(ouvrage_ids, years).items():
        for oid, status in statuses.items():
            if status["over"]:
                alerts[oid].append({
                    "year": year, "total": status["total"], "excess": status["excess"],
                    "explained": status["explained"]})
    return alerts


def _overdue_invoice_items_by_ouvrage(ouvrage_ids, today=None):
    """Factures echues et recouvrables, groupees par ouvrage."""
    from apps.billing.models import PaiementForfaitaire, Releve

    today = today or timezone.localdate()
    current_year = today.year
    items_by_ouvrage = defaultdict(list)

    releves = Releve.objects.filter(
        point_eau__ouvrage_id__in=ouvrage_ids,
        montant__gt=0,
        montant__isnull=False,
    ).exclude(
        Q(remarque__icontains="coupe") | Q(remarque__icontains="coupé")
    ).select_related("point_eau", "point_eau__type_point_eau").only(
        "datereleve",
        "montant",
        "numeroDiameX",
        "baseDiameX",
        "point_eau__ouvrage_id",
        "point_eau__datearretbranchement",
        "point_eau__code_point_eau",
        "point_eau__idxls",
        "point_eau__nomabonne",
        "point_eau__type_point_eau__nom_type",
    )
    for releve in releves.iterator(chunk_size=500):
        if not releve.datereleve:
            continue
        facture_year = (
            releve.datereleve.year + 1
            if releve.datereleve.month == 12
            else releve.datereleve.year
        )
        facture_month = 1 if releve.datereleve.month == 12 else releve.datereleve.month + 1
        if facture_year != current_year or facture_month > today.month:
            continue
        is_pointed = bool(
            str(releve.numeroDiameX or "").strip()
            and str(releve.baseDiameX or "").strip()
        )
        if releve.point_eau.datearretbranchement and not is_pointed:
            continue
        point_label = _quick_point_eau_label(releve.point_eau)
        items_by_ouvrage[str(releve.point_eau.ouvrage_id)].append({
            "date": date(facture_year, facture_month, 1),
            "source": "Au volume",
            "point": point_label,
            "point_type": (
                releve.point_eau.type_point_eau.nom_type
                if releve.point_eau.type_point_eau else ""
            ),
            "point_sort": _quick_point_eau_sort_key(releve.point_eau),
            "amount": Decimal(str(releve.montant or 0)),
        })

    forfait_due = PaiementForfaitaire.objects.filter(
        point_eau__ouvrage_id__in=ouvrage_ids,
        date_facture__year=current_year,
        date_facture__lte=today,
        montant__gt=0,
    ).select_related("point_eau", "point_eau__type_point_eau").only(
        "date_facture",
        "montant",
        "numeroDiameX",
        "baseDiameX",
        "point_eau__ouvrage_id",
        "point_eau__datearretbranchement",
        "point_eau__code_point_eau",
        "point_eau__idxls",
        "point_eau__nomabonne",
        "point_eau__type_point_eau__nom_type",
    )
    for paiement in forfait_due.iterator(chunk_size=500):
        is_pointed = bool(
            str(paiement.numeroDiameX or "").strip()
            and str(paiement.baseDiameX or "").strip()
        )
        if paiement.point_eau.datearretbranchement and not is_pointed:
            continue
        point_label = _quick_point_eau_label(paiement.point_eau)
        items_by_ouvrage[str(paiement.point_eau.ouvrage_id)].append({
            "date": paiement.date_facture,
            "source": "Forfaitaire",
            "point": point_label,
            "point_type": (
                paiement.point_eau.type_point_eau.nom_type
                if paiement.point_eau.type_point_eau else ""
            ),
            "point_sort": _quick_point_eau_sort_key(paiement.point_eau),
            "amount": Decimal(str(paiement.montant or 0)),
        })

    for items in items_by_ouvrage.values():
        # Conserver l'ordre chronologique pour l'imputation DiameX, mais trier
        # numeriquement les IDXLS lorsque plusieurs factures ont la meme date.
        items.sort(key=lambda item: (item["date"], item["point_sort"], item["source"]))
    return items_by_ouvrage


def _attach_ouvrage_card_metrics(page_or_ouvrages, include_indemnities=True):
    """Ajoute les indicateurs des cartes en un nombre constant de requetes."""
    from apps.billing.models import PaiementForfaitaire

    if hasattr(page_or_ouvrages, "object_list"):
        ouvrages = list(page_or_ouvrages.object_list)
        page_or_ouvrages.object_list = ouvrages
    else:
        ouvrages = list(page_or_ouvrages)
    ouvrage_ids = [ouvrage.id for ouvrage in ouvrages]
    if not ouvrage_ids:
        return ouvrages

    ouvrage_ids_set = {str(ouvrage_id) for ouvrage_id in ouvrage_ids}
    point_types = defaultdict(list)
    total_points = defaultdict(int)
    cut_points = defaultdict(int)

    point_rows = (
        PointEau.objects.filter(
            ouvrage_id__in=ouvrage_ids,
        )
        .values("ouvrage_id", "type_point_eau__nom_type")
        .annotate(total=Count("id"))
        .order_by("ouvrage_id", "type_point_eau__nom_type")
    )
    for row in point_rows:
        ouvrage_key = str(row["ouvrage_id"])
        count = int(row["total"] or 0)
        point_types[ouvrage_key].append({
            "label": row["type_point_eau__nom_type"] or "Non defini",
            "count": count,
        })
        total_points[ouvrage_key] += count

    for row in (
        PointEau.objects.filter(
            ouvrage_id__in=ouvrage_ids,
            datebranchement__isnull=False,
            datearretbranchement__isnull=False,
        )
        .values("ouvrage_id")
        .annotate(total=Count("id"))
    ):
        cut_points[str(row["ouvrage_id"])] = int(row["total"] or 0)

    today = timezone.localdate()
    current_year = today.year
    overdue_items = _overdue_invoice_items_by_ouvrage(ouvrage_ids, today=today)
    due_by_ouvrage = {
        ouvrage_id: sum(
            (item["amount"] for item in items), Decimal("0.00")
        )
        for ouvrage_id, items in overdue_items.items()
    }

    collected_all = _annual_diamex_totals_by_ouvrage(current_year)
    collected = {
        ouvrage_id: collected_all.get(ouvrage_id, Decimal("0.00"))
        for ouvrage_id in ouvrage_ids_set
    }
    outstanding = {
        ouvrage_id: max(
            due_by_ouvrage.get(ouvrage_id, Decimal("0.00"))
            - collected.get(ouvrage_id, Decimal("0.00")),
            Decimal("0.00"),
        )
        for ouvrage_id in ouvrage_ids_set
    }

    try:
        indemnities = (
            _rbf_cap_by_ouvrage(ouvrage_ids_set, current_year, _rbf_indemnity_lines_by_ouvrage())
            if include_indemnities else {}
        )
    except Exception:  # noqa: BLE001 - indicateur secondaire : ne jamais casser la page de recherche
        import logging
        logging.getLogger(__name__).exception("Calcul des indemnites RBF par ouvrage impossible")
        indemnities = {}

    try:
        past_alerts = _rbf_past_year_alerts(ouvrage_ids_set, current_year) if include_indemnities else {}
    except Exception:  # noqa: BLE001 - indicateur secondaire
        import logging
        logging.getLogger(__name__).exception("Calcul des depassements d'indemnites des annees precedentes impossible")
        past_alerts = {}

    try:
        forfait_receipts = _forfait_receipt_lines_by_ouvrage(current_year) if indemnities else {}
    except Exception:  # noqa: BLE001 - indicateur secondaire : ne jamais casser la page de recherche
        import logging
        logging.getLogger(__name__).exception("Calcul des encaissements forfaitaires par ouvrage impossible")
        forfait_receipts = {}

    next_collections = {}

    # Echeances forfaitaires futures deja creees.
    future_forfait_rows = (
        PaiementForfaitaire.objects.filter(
            point_eau__ouvrage_id__in=ouvrage_ids,
            date_facture__gt=today,
        )
        .exclude(
            Q(numeroDiameX__isnull=False)
            & ~Q(numeroDiameX="")
            & Q(baseDiameX__isnull=False)
            & ~Q(baseDiameX="")
        )
        .values("point_eau__ouvrage_id", "date_facture")
        .annotate(total=Sum("montant"))
        .order_by("point_eau__ouvrage_id", "date_facture")
    )
    for row in future_forfait_rows:
        ouvrage_key = str(row["point_eau__ouvrage_id"])
        if ouvrage_key not in next_collections:
            next_collections[ouvrage_key] = {
                "date": row["date_facture"],
                "amount": Decimal(str(row["total"] or 0)),
            }

    # Plannings futurs de collecte. En l'absence de montant detaille, la cible
    # est le solde actuellement echu de l'ouvrage.
    future_plannings = (
        Planning.objects.filter(
            ouvrage_id__in=ouvrage_ids,
            date__date__gte=today,
        )
        .filter(
            Q(fiche_poste__tache__icontains="collect")
            | Q(type_activite__nomtype__icontains="collect")
        )
        .exclude(statut__in=("annule", "termine"))
        .values("ouvrage_id", "date")
        .order_by("ouvrage_id", "date")
    )
    for row in future_plannings:
        ouvrage_key = str(row["ouvrage_id"])
        planning_value = row["date"]
        planning_date = (
            timezone.localtime(planning_value).date()
            if timezone.is_aware(planning_value)
            else planning_value.date()
        )
        existing = next_collections.get(ouvrage_key)
        if existing and existing["date"] <= planning_date:
            continue
        next_collections[ouvrage_key] = {
            "date": planning_date,
            "amount": outstanding.get(ouvrage_key, Decimal("0.00")),
        }

    for ouvrage in ouvrages:
        ouvrage_key = str(ouvrage.id)
        ouvrage.card_point_types = point_types.get(ouvrage_key, [])
        ouvrage.card_total_points = total_points.get(ouvrage_key, 0)
        ouvrage.card_cut_points = cut_points.get(ouvrage_key, 0)
        ouvrage.card_collected_current_year = collected.get(
            ouvrage_key, Decimal("0.00")
        )
        ouvrage.card_outstanding_due = outstanding.get(
            ouvrage_key, Decimal("0.00")
        )
        ouvrage.card_next_collection = next_collections.get(ouvrage_key)
        rbf = indemnities.get(ouvrage_key)
        ouvrage.card_rbf_past_alerts = past_alerts.get(ouvrage_key, [])
        ouvrage.card_rbf_current_year = rbf["total"] if rbf else Decimal("0.00")
        ouvrage.card_rbf_by_type = rbf["by_type"] if rbf else []
        ouvrage.card_rbf_lines_count = len(rbf["year_lines"]) if rbf else 0
        ouvrage.card_rbf_per_point = PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC
        ouvrage.card_rbf_public_points = rbf["public_points"] if rbf else 0
        ouvrage.card_rbf_cap = rbf["cap"] if rbf else Decimal("0.00")
        ouvrage.card_rbf_over = bool(rbf and rbf["over"])
        ouvrage.card_rbf_excess = rbf["excess"] if rbf else Decimal("0.00")
        ouvrage.card_rbf_needs_explanation = bool(rbf and rbf["needs_explanation"])
        ouvrage.card_rbf_explained = bool(rbf and rbf["explained"])
        # Lecture croisee : indemnites payees vs forfaitaire recu (meme ouvrage, meme annee).
        forfait_received = sum((line[2] for line in forfait_receipts.get(ouvrage_key, [])), Decimal("0.00"))
        ouvrage.card_forfait_received = forfait_received
        ouvrage.card_rbf_forfait_pct = (
            int(ouvrage.card_rbf_current_year * 100 / forfait_received) if forfait_received > 0 else None
        )
        ouvrage.card_rbf_exceeds_forfait = bool(
            ouvrage.card_rbf_current_year > 0 and ouvrage.card_rbf_current_year > forfait_received)
    return ouvrages


def _explanation_author(user):
    if not user:
        return "Utilisateur supprime"
    employe = getattr(user, "employe", None)
    return (
        (getattr(employe, "nom_affichage", "") if employe else "")
        or user.get_full_name() or user.get_username()
    )


def _serialize_explanation(explanation):
    return {
        "id": str(explanation.id),
        "date": timezone.localtime(explanation.created_at).strftime("%d/%m/%Y %H:%M"),
        "author": _explanation_author(explanation.created_by),
        "text": explanation.explication,
        "amount": float(explanation.montant_paye),
        "cap": float(explanation.plafond),
    }


def _requested_rbf_year(request):
    """Annee demandee (?annee=) si elle fait partie des annees suivies, sinon l'annee en cours."""
    tracked = _rbf_tracked_years()
    raw = request.GET.get("annee", "")
    return int(raw) if raw.isdigit() and int(raw) in tracked else tracked[0]


@login_required
@require_POST
def enregistrer_explication_indemnite_ouvrage(request, ouvrage_id):
    """Enregistre l'explication demandee quand les indemnites RBF de l'annee depassent le plafond de l'ouvrage."""
    if not _can_see_indemnities(request.user):
        return JsonResponse(
            {"success": False, "error": "Acces reserve aux utilisateurs internes."}, status=403)
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Donnees JSON invalides."}, status=400)
    text = str(data.get("explication") or "").strip()
    if len(text) < EXPLICATION_LONGUEUR_MIN:
        return JsonResponse({
            "success": False,
            "error": f"L'explication doit contenir au moins {EXPLICATION_LONGUEUR_MIN} caracteres.",
        }, status=400)
    if len(text) > EXPLICATION_LONGUEUR_MAX:
        return JsonResponse({
            "success": False,
            "error": f"L'explication ne doit pas depasser {EXPLICATION_LONGUEUR_MAX} caracteres.",
        }, status=400)

    include_other_bases = request.GET.get("all_bases", "").lower() in {"1", "true", "on", "yes"}
    ouvrage = get_object_or_404(
        _accessible_ouvrages(request.user, include_other_bases=include_other_bases), id=ouvrage_id)
    year = _requested_rbf_year(request)
    status = _rbf_cap_by_ouvrage([ouvrage.id], year, _rbf_indemnity_lines_by_ouvrage())[str(ouvrage.id)]
    if not status["over"]:
        return JsonResponse({
            "success": False,
            "error": f"Aucun depassement du plafond en {year} : pas d'explication necessaire.",
        }, status=400)

    explanation = ExplicationDepassementIndemnite.objects.create(
        ouvrage=ouvrage, annee=year, montant_paye=status["total"], plafond=status["cap"],
        nb_points_publics=status["public_points"], explication=text, created_by=request.user)
    return JsonResponse({"success": True, "explication": _serialize_explanation(explanation)})


@login_required
@require_GET
def details_indemnites_rbf_ouvrage(request, ouvrage_id):
    """Detail AJAX des lignes DiameX (compte 621102) de l'annee en cours pour un ouvrage (carte ouvrage)."""
    if not _can_see_indemnities(request.user):
        return JsonResponse(
            {"success": False, "error": "Acces reserve aux utilisateurs internes."}, status=403)
    include_other_bases = request.GET.get("all_bases", "").lower() in {"1", "true", "on", "yes"}
    ouvrage = get_object_or_404(
        _accessible_ouvrages(request.user, include_other_bases=include_other_bases),
        id=ouvrage_id,
    )
    from apps.accounting.models import BaseDiameX

    current_year = _requested_rbf_year(request)
    status = _rbf_cap_by_ouvrage([ouvrage.id], current_year, _rbf_indemnity_lines_by_ouvrage())[str(ouvrage.id)]
    total, by_type, year_lines = status["total"], status["by_type"], status["year_lines"]
    types_by_id = {line[0]: line[1] for line in year_lines}
    entries = BaseDiameX.objects.filter(id__in=list(types_by_id)).order_by("-date_m", "-id")

    rows = [{
        "id": entry.id,
        "id_access": entry.id_access,
        "date": entry.date_m.isoformat() if entry.date_m else "",
        "date_rec": entry.date_rec.isoformat() if entry.date_rec else "",
        "description": entry.description or "",
        "type": types_by_id.get(entry.id, "Autre"),
        "amount": float(entry.montant_out or 0),
        "prog": entry.prog or "",
        "source": entry.fichier_source or "",
    } for entry in entries]

    # Encaissements DiameX 748411 de l'ouvrage (indicateur global) ; le detail par point d'eau vient de PaiementForfaitaire.
    forfait_lines = _forfait_receipt_lines_by_ouvrage(current_year).get(str(ouvrage.id), [])
    forfait_total = sum((line[2] for line in forfait_lines), Decimal("0.00"))

    return JsonResponse({
        "success": True,
        "ouvrage": ouvrage.nom_ouvrage,
        "compte": COMPTE_INDEMNITES_RBF,
        "forfait": {
            "compte": COMPTE_PAIEMENT_FORFAITAIRE,
            "total": float(forfait_total),
            "count": len(forfait_lines),
        },
        "points": _rbf_groups_by_point(current_year, rows, year_lines),
        "year": current_year,
        "summary": {
            "total": float(total),
            "count": len(rows),
            "par_type": [{"type": item["type"], "amount": float(item["amount"])} for item in by_type],
        },
        "plafond": {
            "per_point": float(status["per_point"]),
            "public_points": status["public_points"],
            "cap": float(status["cap"]),
            "over": status["over"],
            "excess": float(status["excess"]),
            "explained": status["explained"],
            "needs_explanation": status["needs_explanation"],
        },
        "explications": [_serialize_explanation(item) for item in
                         ExplicationDepassementIndemnite.objects.filter(ouvrage=ouvrage, annee=current_year)
                         .select_related("created_by")[:10]],
        "rows": rows,
    })


@login_required
@require_GET
def details_montant_echu_ouvrage(request, ouvrage_id):
    """Detail AJAX du solde echu affiche dans les cartes ouvrage."""
    include_other_bases = request.GET.get("all_bases", "").lower() in {
        "1", "true", "on", "yes",
    }
    ouvrage = get_object_or_404(
        _accessible_ouvrages(
            request.user,
            include_other_bases=include_other_bases,
        ),
        id=ouvrage_id,
    )
    today = timezone.localdate()
    items = _overdue_invoice_items_by_ouvrage([ouvrage.id], today=today).get(
        str(ouvrage.id), []
    )
    total_due = sum((item["amount"] for item in items), Decimal("0.00"))
    total_collected = _annual_diamex_totals_by_ouvrage(today.year).get(
        str(ouvrage.id), Decimal("0.00")
    )
    remaining_collected = total_collected
    outstanding_rows = []
    for item in items:
        allocated = min(item["amount"], remaining_collected)
        remaining_collected -= allocated
        remaining = item["amount"] - allocated
        if remaining <= 0:
            continue
        outstanding_rows.append({
            "date": item["date"].isoformat(),
            "source": item["source"],
            "point": item["point"],
            "point_type": item["point_type"],
            "point_sort": item["point_sort"],
            "amount": float(item["amount"]),
            "collected": float(allocated),
            "remaining": float(remaining),
        })

    # Le tableau du modal est classe par IDXLS converti en nombre (2 avant 10),
    # puis par nom d'abonne, sans modifier l'imputation chronologique ci-dessus.
    outstanding_rows.sort(
        key=lambda row: (row["point_sort"], row["date"], row["source"])
    )
    for row in outstanding_rows:
        row.pop("point_sort", None)

    outstanding = max(total_due - total_collected, Decimal("0.00"))
    return JsonResponse({
        "success": True,
        "ouvrage": ouvrage.nom_ouvrage or "Ouvrage sans nom",
        "year": today.year,
        "summary": {
            "due": float(total_due),
            "collected": float(total_collected),
            "outstanding": float(outstanding),
        },
        "rows": outstanding_rows,
        "allocation_note": (
            "Le montant DiameX collecté est imputé aux factures les plus "
            "anciennes pour présenter le détail du solde restant."
        ),
    })


def _is_repair_or_rehabilitation_activity(planning):
    """Classe d'abord selon le type, avec repli pour les anciennes donnees."""
    fiche = getattr(planning, "fiche_poste", None)
    type_name = (
        getattr(getattr(fiche, "type_activites", None), "nomtype", "")
        or getattr(getattr(planning, "type_activite", None), "nomtype", "")
    )
    activity_text = normalize_repair_text(type_name)
    if not activity_text:
        activity_text = normalize_repair_text(getattr(fiche, "tache", ""))
    return (
        ("reparation" in activity_text and "preparation" not in activity_text)
        or ("rehabilitation" in activity_text and "preparation" not in activity_text)
    )


def _planning_type_text(planning):
    fiche = getattr(planning, "fiche_poste", None)
    type_name = (
        getattr(getattr(fiche, "type_activites", None), "nomtype", "")
        or getattr(getattr(planning, "type_activite", None), "nomtype", "")
    )
    return normalize_repair_text(type_name) or normalize_repair_text(getattr(fiche, "tache", ""))


def _is_installation_activity(planning):
    return "installation" in _planning_type_text(planning)


def _planning_family(planning):
    """Famille detaillee : reparation, rehabilitation, installation ou '' (autre)."""
    if _is_installation_activity(planning):
        return "installation"
    if not _is_repair_or_rehabilitation_activity(planning):
        return ""
    return "rehabilitation" if "rehabilitation" in _planning_type_text(planning) else "reparation"


def _planning_deadline(planning, today):
    planning_date = getattr(planning, "date", None)
    if not planning_date:
        return None
    if isinstance(planning_date, datetime):
        if timezone.is_aware(planning_date):
            planning_date = timezone.localtime(planning_date)
        planning_date = planning_date.date()
    return "overdue" if planning_date < today else "upcoming"


def _activity_deadline_bucket(planning, today):
    deadline = _planning_deadline(planning, today)
    if not deadline:
        return None
    family = "repair" if _is_repair_or_rehabilitation_activity(planning) else "other"
    return f"{family}_{deadline}"


FAMILY_BUCKET_NAMES = tuple(
    f"{family}_{deadline}"
    for family in ("reparation", "rehabilitation", "installation")
    for deadline in ("overdue", "upcoming")
)


def _activity_deadline_summary_by_ouvrage(ouvrage_ids, *, today=None, include_installation=False):
    """Compte les activites non terminees par famille et par echeance.

    Les buckets historiques (repair/other) sont inchanges. Les cles supplementaires
    `family_planning_ids` / `family_activity_counts` separent reparation, rehabilitation
    et installation ; les installations n'y figurent que si include_installation=True.
    """
    ouvrage_ids = set(ouvrage_ids)
    bucket_names = (
        "repair_overdue",
        "repair_upcoming",
        "other_overdue",
        "other_upcoming",
    )
    empty_summary = {
        "counts": {},
        "repair_ouvrage_ids": set(),
        "maintenance_only_ouvrage_ids": set(),
        "activity_counts": {name: {} for name in bucket_names},
        "planning_ids": {name: set() for name in bucket_names},
        "totals": {name: 0 for name in bucket_names},
        "family_activity_counts": {name: {} for name in FAMILY_BUCKET_NAMES},
        "family_planning_ids": {name: set() for name in FAMILY_BUCKET_NAMES},
    }
    if not ouvrage_ids:
        return empty_summary

    today = today or timezone.localdate()
    fiche_ids = list(
        _get_quick_repair_fiches_queryset().values_list("id", flat=True)
    )
    if include_installation:
        fiche_ids += list(
            FichePoste.objects.filter(type_activites__nomtype__icontains="installation")
            .values_list("id", flat=True)
        )
    old_activity_ids = list(Activite.objects.filter(
        Q(nom__icontains="réparation")
        | Q(nom__icontains="reparation")
        | Q(nom__icontains="réhabilitation")
        | Q(nom__icontains="rehabilitation")
        | Q(nom__icontains="panne")
        | Q(nom__icontains="entretien")
        | Q(nom__icontains="maintenance")
    ).values_list("id", flat=True))

    # `ouvrage_ids` peut arriver comme des UUID (querysets `.values_list('id', ...)`) ou des
    # chaines (ex. `classify_ouvrages`, qui travaille en identifiants texte). `planning.ouvrage_id`
    # est toujours un UUID cote ORM : comparer directement `planning.ouvrage_id in ouvrage_ids`
    # echoue silencieusement (UUID != str) des qu'on est appele avec des chaines. On normalise
    # donc une table de correspondance str -> valeur d'origine pour les tests d'appartenance,
    # tout en renvoyant les cles dans le type fourni par l'appelant (pas de regression ailleurs).
    ouvrage_id_by_str = {str(o): o for o in ouvrage_ids}

    plannings = (
        Planning.objects.filter(
            Q(ouvrage_id__in=ouvrage_ids)
            | Q(details__point_eau__ouvrage_id__in=ouvrage_ids)
            | Q(details__equipement_constitutif__ouvrage_id__in=ouvrage_ids),
            date__isnull=False,
        )
        .filter(
            Q(statut__isnull=True)
            | Q(statut="")
            | Q(statut__in=ACTIVE_INTERVENTION_STATUSES)
        )
        .filter(
            Q(fiche_poste_id__in=fiche_ids)
            | Q(fiche_poste__activites_postes__activite_id__in=old_activity_ids)
            | Q(remarque__startswith="[Saisie depuis la fiche ouvrage]")
        )
        .select_related("fiche_poste__type_activites", "type_activite")
        .prefetch_related(
            Prefetch(
                "details",
                queryset=PlanningDetail.objects.filter(
                    Q(point_eau__ouvrage_id__in=ouvrage_ids)
                    | Q(equipement_constitutif__ouvrage_id__in=ouvrage_ids)
                ).select_related("point_eau", "equipement_constitutif"),
                to_attr="deadline_ouvrage_details",
            )
        )
        .distinct()
    )

    planning_ids_by_bucket = {
        name: defaultdict(set) for name in bucket_names
    }
    family_ids_by_bucket = {
        name: defaultdict(set) for name in FAMILY_BUCKET_NAMES
    }

    for planning in plannings:
        target_ids = set()
        if is_excluded_repair_activity(planning.activite_display):
            continue
        matched = ouvrage_id_by_str.get(str(planning.ouvrage_id))
        if matched is not None:
            target_ids.add(matched)
        for detail in getattr(planning, "deadline_ouvrage_details", []):
            if detail.point_eau:
                matched = ouvrage_id_by_str.get(str(detail.point_eau.ouvrage_id))
                if matched is not None:
                    target_ids.add(matched)
            if detail.equipement_constitutif:
                matched = ouvrage_id_by_str.get(str(detail.equipement_constitutif.ouvrage_id))
                if matched is not None:
                    target_ids.add(matched)

        bucket = _activity_deadline_bucket(planning, today)
        if not bucket:
            continue
        family = _planning_family(planning)
        if family == "installation":
            # Les installations ont leur propre famille et ne gonflent pas les buckets historiques.
            if include_installation:
                family_bucket = f"installation_{_planning_deadline(planning, today)}"
                for ouvrage_id in target_ids:
                    family_ids_by_bucket[family_bucket][ouvrage_id].add(planning.id)
                continue
        elif family:
            family_bucket = f"{family}_{_planning_deadline(planning, today)}"
            for ouvrage_id in target_ids:
                family_ids_by_bucket[family_bucket][ouvrage_id].add(planning.id)
        for ouvrage_id in target_ids:
            planning_ids_by_bucket[bucket][ouvrage_id].add(planning.id)

    activity_counts = {
        bucket: {
            ouvrage_id: len(planning_ids)
            for ouvrage_id, planning_ids in planning_ids_by_ouvrage.items()
        }
        for bucket, planning_ids_by_ouvrage in planning_ids_by_bucket.items()
    }
    overdue_counts = {
        ouvrage_id: (
            activity_counts["repair_overdue"].get(ouvrage_id, 0)
            + activity_counts["other_overdue"].get(ouvrage_id, 0)
        )
        for ouvrage_id in ouvrage_ids
    }
    repair_overdue_ids = set(activity_counts["repair_overdue"])
    other_overdue_ids = set(activity_counts["other_overdue"])

    return {
        # Anciennes cles conservees pour les reponses AJAX existantes.
        "counts": {key: value for key, value in overdue_counts.items() if value},
        "repair_ouvrage_ids": repair_overdue_ids,
        "maintenance_only_ouvrage_ids": other_overdue_ids - repair_overdue_ids,
        "activity_counts": activity_counts,
        "planning_ids": {
            bucket: {
                planning_id
                for planning_ids in planning_ids_by_ouvrage.values()
                for planning_id in planning_ids
            }
            for bucket, planning_ids_by_ouvrage in planning_ids_by_bucket.items()
        },
        "totals": {
            bucket: sum(counts.values())
            for bucket, counts in activity_counts.items()
        },
        "family_activity_counts": {
            bucket: {o: len(ids) for o, ids in by_ouvrage.items()}
            for bucket, by_ouvrage in family_ids_by_bucket.items()
        },
        "family_planning_ids": {
            bucket: {pid for ids in by_ouvrage.values() for pid in ids}
            for bucket, by_ouvrage in family_ids_by_bucket.items()
        },
    }


def _overdue_activity_summary_by_ouvrage(ouvrage_ids, *, today=None):
    """Compatibilite avec les consommateurs de l'ancien resume des echues."""
    return _activity_deadline_summary_by_ouvrage(ouvrage_ids, today=today)


@login_required
def recherche_ouvrages_rapide(request):
    """Recherche légère limitée aux ouvrages accessibles à l'utilisateur."""
    query = (request.GET.get("q") or "").strip()
    region_filter = (request.GET.get("region") or "").strip()
    district_filter = (request.GET.get("district") or "").strip()
    commune_filter = (request.GET.get("commune") or "").strip()
    employee_filter = (request.GET.get("employee") or "").strip()
    today = timezone.localdate()
    accessible_ouvrages = _accessible_intervention_ouvrages(request.user)
    ouvrages = accessible_ouvrages.select_related("type_ouvrage")
    recent_cutoff = timezone.now() - timedelta(days=30)
    # Meme catalogue que le formulaire de saisie rapide avec photos.
    repair_fiche_ids = list(
        _get_quick_repair_fiches_queryset().values_list("id", flat=True)
    )
    statistics = _intervention_statistics(Planning.objects.filter(
        ouvrage__in=accessible_ouvrages,
        fiche_poste_id__in=repair_fiche_ids,
    ))

    active_responsibilities = EmployeOuvrages.objects.filter(
        ouvrage__in=accessible_ouvrages,
        date_debut__lte=today,
        employe__date_debauchage__isnull=True,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=today),
    )
    score_postes_filter = Q()
    for poste_name in OUVRAGE_SCORE_EMPLOYEE_POSTES:
        score_postes_filter |= Q(employe__poste__nom_poste__iexact=poste_name)
    active_responsibilities = active_responsibilities.filter(
        score_postes_filter
    ).select_related(
        "employe", "employe__base", "employe__poste",
    )

    employee_ouvrage_ids = defaultdict(set)
    score_employees_by_id = {}
    for responsibility in active_responsibilities:
        employee_id = str(responsibility.employe_id)
        employee_ouvrage_ids[employee_id].add(responsibility.ouvrage_id)
        score_employees_by_id[employee_id] = responsibility.employe
    score_employees = [
        {
            "id": employee_id,
            "label": employee.nom_affichage,
            "base_label": employee.base.nom_base if employee.base else "Base non définie",
            "poste_label": employee.poste.nom_poste if employee.poste else "Sans poste",
            "ouvrage_count": len(employee_ouvrage_ids[employee_id]),
        }
        for employee_id, employee in score_employees_by_id.items()
    ]
    score_employees.sort(key=lambda item: (
        item["base_label"].casefold(),
        item["poste_label"].casefold(),
        item["label"].casefold(),
    ))
    score_responsible_ouvrage_ids = {
        ouvrage_id
        for ouvrage_ids in employee_ouvrage_ids.values()
        for ouvrage_id in ouvrage_ids
    }
    if employee_filter:
        ouvrages = ouvrages.filter(
            id__in=employee_ouvrage_ids.get(employee_filter, set())
        )

    if query:
        ouvrages = ouvrages.filter(
            Q(nom_ouvrage__icontains=query)
            | Q(type_ouvrage__nom_type_ouvrage__icontains=query)
            | Q(observation__icontains=query)
            | Q(pointeau__code_point_eau__icontains=query)
            | Q(pointeau__parcelle__village__nom_village__icontains=query)
            | Q(pointeau__parcelle__village__fokontany__commune__nom_commune__icontains=query)
            | Q(pointeau__parcelle__village__fokontany__commune__district__nom_district__icontains=query)
            | Q(pointeau__parcelle__village__fokontany__commune__district__region__nom_region__icontains=query)
        ).distinct()

    first_point = PointEau.objects.filter(
        ouvrage_id=OuterRef("pk"),
        parcelle__village__fokontany__commune__district__region__isnull=False,
    ).exclude(
        parcelle__village__fokontany__commune__district__region__nom_region__icontains="inconnu",
    ).order_by("id")
    ouvrages = ouvrages.annotate(
        search_commune_id=Subquery(first_point.values("parcelle__village__fokontany__commune_id")[:1]),
        search_district_id=Subquery(first_point.values("parcelle__village__fokontany__commune__district_id")[:1]),
        search_region_id=Subquery(first_point.values("parcelle__village__fokontany__commune__district__region_id")[:1]),
        search_village=Subquery(first_point.values("parcelle__village__nom_village")[:1]),
        search_commune=Subquery(first_point.values("parcelle__village__fokontany__commune__nom_commune")[:1]),
        search_district=Subquery(first_point.values("parcelle__village__fokontany__commune__district__nom_district")[:1]),
        search_region=Subquery(first_point.values("parcelle__village__fokontany__commune__district__region__nom_region")[:1]),
        recent_interventions_count=Count(
            "plannings",
            filter=Q(
                plannings__fiche_poste_id__in=repair_fiche_ids,
                plannings__created_at__gte=recent_cutoff,
            ),
            distinct=True,
        ),
        unfinished_overdue_contributions_count=Count(
            "plannings",
            filter=(
                Q(plannings__fiche_poste_id__in=repair_fiche_ids)
                & Q(plannings__date__date__lt=today)
                & (
                    Q(plannings__statut__isnull=True)
                    | Q(plannings__statut="")
                    | Q(plannings__statut__in=ACTIVE_INTERVENTION_STATUSES)
                )
            ),
            distinct=True,
        ),
    ).filter(
        search_region__isnull=False,
    ).exclude(
        search_region="",
    ).exclude(
        search_region__icontains="inconnu",
    )

    if region_filter:
        ouvrages = ouvrages.filter(search_region_id=region_filter)
    if district_filter:
        ouvrages = ouvrages.filter(search_district_id=district_filter)
    if commune_filter:
        ouvrages = ouvrages.filter(search_commune_id=commune_filter)

    ouvrages = ouvrages.order_by(
        "search_region", "search_district", "search_commune", "nom_ouvrage"
    )

    # Alerte debit de source : perimetre du bandeau calcule avant le filtre.
    debit_scope_ids = list(ouvrages.order_by().values_list("id", flat=True))
    debit_filter = "critique" if request.GET.get("debit") == "critique" else ""
    if debit_filter:
        from apps.planning.services_debit_critique import ids_ouvrages_par_niveau
        ouvrages = ouvrages.filter(id__in=ids_ouvrages_par_niveau("critique"))

    contribution_filter = (
        Q(plannings__fiche_poste_id__in=repair_fiche_ids)
        & Q(plannings__created_at__year__lte=today.year)
    )
    unfinished_filter = (
        contribution_filter
        & (
            Q(plannings__statut__isnull=True)
            | Q(plannings__statut="")
            | Q(plannings__statut__in=ACTIVE_INTERVENTION_STATUSES)
        )
    )
    score_ouvrages = ouvrages.filter(id__in=score_responsible_ouvrage_ids)
    score_rows = list(
        score_ouvrages.order_by().values("id").annotate(
            contribution_count=Count(
                "plannings", filter=contribution_filter, distinct=True,
            ),
            unfinished_count=Count(
                "plannings", filter=unfinished_filter, distinct=True,
            ),
        )
    )
    score_values = _calculate_ouvrage_contribution_score(score_rows)
    filtered_ouvrage_ids = list(
        ouvrages.order_by().values_list("id", flat=True)
    )
    filtered_ouvrages_count = len(filtered_ouvrage_ids)
    can_see_indemnities = _can_see_indemnities(request.user)
    rbf_over_ouvrage_ids, rbf_unexplained_ouvrage_ids = set(), set()
    if can_see_indemnities:
        try:
            rbf_over_ouvrage_ids, rbf_unexplained_ouvrage_ids = _rbf_over_cap_ouvrage_ids(
                filtered_ouvrage_ids, _rbf_tracked_years())
        except Exception:  # noqa: BLE001 - statistique secondaire : ne jamais casser la page de recherche
            import logging
            logging.getLogger(__name__).exception("Statistique des depassements d'indemnites RBF impossible")
    indemnity_filter = "depasse" if (
        can_see_indemnities and request.GET.get("indemnite") == "depasse") else ""
    activity_deadline_summary = _activity_deadline_summary_by_ouvrage(
        filtered_ouvrage_ids,
        today=today,
    )
    overdue_unfinished_count = sum(activity_deadline_summary["counts"].values())
    overdue_repair_ouvrages_count = len(
        activity_deadline_summary["repair_ouvrage_ids"]
    )
    overdue_maintenance_only_ouvrages_count = len(
        activity_deadline_summary["maintenance_only_ouvrage_ids"]
    )
    overdue_repair_ouvrages_percentage = round(
        overdue_repair_ouvrages_count * 100 / filtered_ouvrages_count,
        1,
    ) if filtered_ouvrages_count else 0
    overdue_maintenance_only_ouvrages_percentage = round(
        overdue_maintenance_only_ouvrages_count * 100 / filtered_ouvrages_count,
        1,
    ) if filtered_ouvrages_count else 0

    selected_employee = score_employees_by_id.get(employee_filter)
    if selected_employee:
        score_scope_label = "Score employé"
        score_scope_name = selected_employee.nom_affichage
    elif commune_filter:
        score_scope_label = "Score commune"
        score_scope_name = Commune.objects.filter(
            id=commune_filter,
            id__in=PointEau.objects.filter(
                ouvrage__in=accessible_ouvrages,
            ).values("parcelle__village__fokontany__commune_id"),
        ).values_list("nom_commune", flat=True).first() or "Commune sélectionnée"
    elif district_filter:
        score_scope_label = "Score district"
        score_scope_name = District.objects.filter(
            id=district_filter,
            id__in=PointEau.objects.filter(
                ouvrage__in=accessible_ouvrages,
            ).values("parcelle__village__fokontany__commune__district_id"),
        ).values_list("nom_district", flat=True).first() or "District sélectionné"
    elif region_filter:
        score_scope_label = "Score région"
        score_scope_name = Region.objects.filter(
            id=region_filter,
            id__in=PointEau.objects.filter(
                ouvrage__in=accessible_ouvrages,
            ).values("parcelle__village__fokontany__commune__district__region_id"),
        ).values_list("nom_region", flat=True).first() or "Région sélectionnée"
    else:
        actor = getattr(request.user, "employe", None)
        organisation = getattr(getattr(actor, "base", None), "organisation", None)
        score_scope_label = "Score organisation"
        score_scope_name = getattr(organisation, "nom_organisation", None) or "Périmètre accessible"

    score_summary = {
        "scope_label": score_scope_label,
        "scope_name": score_scope_name,
        **score_values,
    }

    geo_point_scope = PointEau.objects.filter(
        ouvrage__in=accessible_ouvrages,
        parcelle__village__fokontany__commune__district__region__isnull=False,
    )
    regions = Region.objects.filter(
        id__in=geo_point_scope.values_list(
            "parcelle__village__fokontany__commune__district__region_id",
            flat=True,
        )
    ).only("id", "nom_region").distinct().order_by("nom_region")
    districts = District.objects.filter(
        id__in=geo_point_scope.values_list(
            "parcelle__village__fokontany__commune__district_id",
            flat=True,
        )
    ).only("id", "nom_district", "region_id").distinct().order_by("nom_district")
    if region_filter:
        districts = districts.filter(region_id=region_filter)
    communes = Commune.objects.filter(
        id__in=geo_point_scope.values_list(
            "parcelle__village__fokontany__commune_id",
            flat=True,
        )
    ).annotate(
        filter_region_id=F("district__region_id"),
    ).only("id", "nom_commune", "district_id").distinct().order_by("nom_commune")
    if district_filter:
        communes = communes.filter(district_id=district_filter)
    elif region_filter:
        communes = communes.filter(district__region_id=region_filter)

    if indemnity_filter:
        ouvrages = ouvrages.filter(id__in=[UUID(oid) for oid in rbf_over_ouvrage_ids])

    # Les badges de regroupement doivent compter tout le résultat filtré, pas
    # uniquement les 30 objets de la page courante.
    region_counts = defaultdict(int)
    district_counts = defaultdict(int)
    commune_counts = {}
    grouped_counts = (
        ouvrages.order_by()
        .values("search_region", "search_district", "search_commune")
        .annotate(total=Count("id", distinct=True))
    )
    for row in grouped_counts:
        total = int(row["total"] or 0)
        region_key = row["search_region"] or ""
        district_key = row["search_district"] or ""
        commune_key = row["search_commune"] or ""
        region_counts[region_key] += total
        district_counts[(region_key, district_key)] += total
        commune_counts[(region_key, district_key, commune_key)] = total

    page = Paginator(ouvrages, 30).get_page(request.GET.get("page"))
    _attach_ouvrage_card_metrics(page, include_indemnities=_can_see_indemnities(request.user))
    for ouvrage in page.object_list:
        ouvrage.unfinished_overdue_contributions_count = (
            activity_deadline_summary["counts"].get(ouvrage.id, 0)
        )
        ouvrage.overdue_activity_category = (
            "repair"
            if ouvrage.id in activity_deadline_summary["repair_ouvrage_ids"]
            else "maintenance"
            if ouvrage.id in activity_deadline_summary["maintenance_only_ouvrage_ids"]
            else "none"
        )
        ouvrage.repair_overdue_count = activity_deadline_summary["activity_counts"]["repair_overdue"].get(ouvrage.id, 0)
        ouvrage.repair_upcoming_count = activity_deadline_summary["activity_counts"]["repair_upcoming"].get(ouvrage.id, 0)
        ouvrage.other_overdue_count = activity_deadline_summary["activity_counts"]["other_overdue"].get(ouvrage.id, 0)
        ouvrage.other_upcoming_count = activity_deadline_summary["activity_counts"]["other_upcoming"].get(ouvrage.id, 0)
        region_key = ouvrage.search_region or ""
        district_key = ouvrage.search_district or ""
        commune_key = ouvrage.search_commune or ""
        ouvrage.card_region_total = region_counts.get(region_key, 0)
        ouvrage.card_district_total = district_counts.get(
            (region_key, district_key), 0
        )
        ouvrage.card_commune_total = commune_counts.get(
            (region_key, district_key, commune_key), 0
        )

    base_filter_pairs = [
        (key, value) for key, value in (
            ("q", query),
            ("region", region_filter),
            ("district", district_filter),
            ("commune", commune_filter),
            ("employee", employee_filter),
            ("debit", debit_filter),
        ) if value
    ]
    return render(
        request,
        "core/recherche_ouvrages_rapide.html",
        {
            "debit_scope_ids": debit_scope_ids,
            "debit_filter": debit_filter,
            "debit_filtre_url": "?" + urlencode(
                [pair for pair in base_filter_pairs if pair[0] != "debit"] + [("debit", "critique")]
            ),
            "debit_reset_url": "?" + urlencode(
                [pair for pair in base_filter_pairs if pair[0] != "debit"]
            ),
            "page_obj": page,
            "query": query,
            "title": "Recherche rapide des ouvrages",
            "can_add_intervention": not bool(getattr(request.user, "client", None)) or request.user.is_staff,
            "can_delete_interventions": is_directeur_poste(request.user),
            "intervention_stats": statistics,
            "region_filter": region_filter,
            "district_filter": district_filter,
            "commune_filter": commune_filter,
            "employee_filter": employee_filter,
            "regions": regions,
            "districts": districts,
            "communes": communes,
            "score_employees": score_employees,
            "score_summary": score_summary,
            "overdue_unfinished_count": overdue_unfinished_count,
            "overdue_repair_ouvrages_count": overdue_repair_ouvrages_count,
            "overdue_maintenance_only_ouvrages_count": overdue_maintenance_only_ouvrages_count,
            "overdue_repair_ouvrages_percentage": overdue_repair_ouvrages_percentage,
            "overdue_maintenance_only_ouvrages_percentage": overdue_maintenance_only_ouvrages_percentage,
            "activity_deadline_totals": activity_deadline_summary["totals"],
            "filtered_ouvrages_count": filtered_ouvrages_count,
            "can_see_indemnities": can_see_indemnities,
            "rbf_over_ouvrages_count": len(rbf_over_ouvrage_ids),
            "rbf_unexplained_ouvrages_count": len(rbf_unexplained_ouvrage_ids),
            "rbf_plafond_par_point": PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC,
            "rbf_annees_label": f"{min(_rbf_tracked_years())}-{max(_rbf_tracked_years())}",
            "indemnity_filter": indemnity_filter,
            "pagination_query": urlencode(base_filter_pairs + (
                [("indemnite", indemnity_filter)] if indemnity_filter else [])),
            "indemnity_link_query": urlencode(base_filter_pairs + [("indemnite", "depasse")]),
            "indemnity_reset_query": urlencode(base_filter_pairs),
        },
    )


@login_required
def interventions_recentes(request):
    """Fil chronologique global basé sur la date réelle de saisie."""
    include_other_bases = request.GET.get("all_bases", "").lower() in {
        "1", "true", "on", "yes",
    }
    # Meme catalogue que le formulaire de saisie rapide avec photos.
    fiche_ids = list(
        _get_quick_repair_fiches_queryset().values_list("id", flat=True)
    )
    detail_queryset = PlanningDetail.objects.select_related(
        "point_eau",
        "equipement_constitutif",
    ).order_by("created_at")
    accessible_ouvrages = _accessible_intervention_ouvrages(
        request.user,
        include_other_bases=include_other_bases,
    )
    base_plannings = Planning.objects.filter(
        ouvrage__in=accessible_ouvrages,
        fiche_poste_id__in=fiche_ids,
    )
    statistics = _intervention_statistics(base_plannings)

    # Les liens des statistiques ouvrent la liste exacte des contributions
    # photographiées ayant servi au calcul du classement.
    period_filter = (request.GET.get("period") or "").strip().lower()
    if period_filter not in {"month", "year"}:
        period_filter = ""

    def valid_uuid_filter(parameter_name):
        value = (request.GET.get(parameter_name) or "").strip()
        if not value:
            return ""
        try:
            return str(UUID(value))
        except (ValueError, AttributeError, TypeError):
            return ""

    employee_filter = valid_uuid_filter("employee")
    ouvrage_filter = valid_uuid_filter("ouvrage")
    region_filter = valid_uuid_filter("region")
    district_filter = valid_uuid_filter("district")
    commune_filter = valid_uuid_filter("commune")
    responsible_employee_filter = valid_uuid_filter("responsible_employee")
    has_statistics_filter = bool(period_filter or employee_filter or ouvrage_filter)
    filtered_plannings = base_plannings
    if has_statistics_filter:
        filtered_plannings = filtered_plannings.filter(
            Q(photo__iregex=r'"type"\s*:\s*"image/')
            | Q(photo__icontains="data:image/")
        )
        now_local = timezone.localtime(timezone.now())
        if period_filter == "month":
            filtered_plannings = filtered_plannings.filter(
                created_at__gte=now_local.replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0,
                )
            )
        elif period_filter == "year":
            filtered_plannings = filtered_plannings.filter(
                created_at__gte=now_local.replace(
                    month=1, day=1, hour=0, minute=0, second=0, microsecond=0,
                )
            )
        if employee_filter:
            filtered_plannings = filtered_plannings.filter(employe_id=employee_filter)
        if ouvrage_filter:
            filtered_plannings = filtered_plannings.filter(ouvrage_id=ouvrage_filter)

    # Les options geographiques et les responsables sont toujours construites
    # depuis les ouvrages deja accessibles. Un UUID forge ne peut donc ni
    # elargir le perimetre, ni reveler un libelle hors cloisonnement.
    geo_point_scope = PointEau.objects.filter(
        ouvrage__in=accessible_ouvrages,
        parcelle__village__fokontany__commune__district__region__isnull=False,
    )
    regions = Region.objects.filter(
        id__in=geo_point_scope.values_list(
            "parcelle__village__fokontany__commune__district__region_id",
            flat=True,
        )
    ).only("id", "nom_region").distinct().order_by("nom_region")
    districts = District.objects.filter(
        id__in=geo_point_scope.values_list(
            "parcelle__village__fokontany__commune__district_id",
            flat=True,
        )
    ).only("id", "nom_district", "region_id").distinct().order_by("nom_district")
    if region_filter:
        districts = districts.filter(region_id=region_filter)

    communes = Commune.objects.filter(
        id__in=geo_point_scope.values_list(
            "parcelle__village__fokontany__commune_id",
            flat=True,
        )
    ).annotate(
        filter_region_id=F("district__region_id"),
    ).only("id", "nom_commune", "district_id").distinct().order_by("nom_commune")
    if district_filter:
        communes = communes.filter(district_id=district_filter)
    elif region_filter:
        communes = communes.filter(district__region_id=region_filter)

    today = timezone.localdate()
    active_responsibilities = EmployeOuvrages.objects.filter(
        ouvrage__in=accessible_ouvrages,
        date_debut__lte=today,
        employe__date_debauchage__isnull=True,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=today),
    )
    responsible_postes_filter = Q()
    for poste_name in OUVRAGE_SCORE_EMPLOYEE_POSTES:
        responsible_postes_filter |= Q(employe__poste__nom_poste__iexact=poste_name)
    active_responsibilities = active_responsibilities.filter(
        responsible_postes_filter
    ).select_related("employe", "employe__base", "employe__poste")

    responsible_ouvrage_ids = defaultdict(set)
    responsible_employees_by_id = {}
    for responsibility in active_responsibilities:
        employee_id = str(responsibility.employe_id)
        responsible_ouvrage_ids[employee_id].add(responsibility.ouvrage_id)
        responsible_employees_by_id[employee_id] = responsibility.employe
    responsible_employees = [
        {
            "id": employee_id,
            "label": employee.nom_affichage,
            "base_label": employee.base.nom_base if employee.base else "Base non definie",
            "poste_label": employee.poste.nom_poste if employee.poste else "Sans poste",
            "ouvrage_count": len(responsible_ouvrage_ids[employee_id]),
        }
        for employee_id, employee in responsible_employees_by_id.items()
    ]
    responsible_employees.sort(key=lambda item: (
        item["base_label"].casefold(),
        item["poste_label"].casefold(),
        item["label"].casefold(),
    ))

    if region_filter:
        filtered_plannings = filtered_plannings.filter(
            ouvrage_id__in=geo_point_scope.filter(
                parcelle__village__fokontany__commune__district__region_id=region_filter,
            ).values("ouvrage_id")
        )
    if district_filter:
        filtered_plannings = filtered_plannings.filter(
            ouvrage_id__in=geo_point_scope.filter(
                parcelle__village__fokontany__commune__district_id=district_filter,
            ).values("ouvrage_id")
        )
    if commune_filter:
        filtered_plannings = filtered_plannings.filter(
            ouvrage_id__in=geo_point_scope.filter(
                parcelle__village__fokontany__commune_id=commune_filter,
            ).values("ouvrage_id")
        )
    if responsible_employee_filter:
        filtered_plannings = filtered_plannings.filter(
            ouvrage_id__in=responsible_ouvrage_ids.get(
                responsible_employee_filter, set(),
            )
        )

    valid_statuses = dict(Planning.STATUS_CHOICES)
    status_filter_active = request.GET.get("status_filter") == "1"
    selected_statuses = [
        status for status in request.GET.getlist("status")
        if status in valid_statuses
    ]
    if status_filter_active:
        if selected_statuses:
            filtered_plannings = filtered_plannings.filter(statut__in=selected_statuses)
        else:
            filtered_plannings = filtered_plannings.none()

    sort_mode = (request.GET.get("sort") or "created_at").strip().lower()
    if sort_mode not in {"created_at", "intervention_date"}:
        sort_mode = "created_at"

    filter_labels = {}
    if employee_filter:
        accessible_employee_ids = base_plannings.filter(
            employe_id=employee_filter,
        ).values("employe_id")
        employee = Employe.objects.filter(
            id__in=accessible_employee_ids,
        ).first()
        filter_labels["employee"] = employee.nom_affichage if employee else "Employé"
    if ouvrage_filter:
        ouvrage = accessible_ouvrages.filter(id=ouvrage_filter).first()
        filter_labels["ouvrage"] = (
            ouvrage.nom_ouvrage if ouvrage else "Ouvrage"
        )
    if period_filter:
        filter_labels["period"] = (
            "Mois en cours" if period_filter == "month"
            else f"Année {timezone.localtime(timezone.now()).year}"
        )

    selected_region = regions.filter(id=region_filter).first() if region_filter else None
    selected_district = districts.filter(id=district_filter).first() if district_filter else None
    selected_commune = communes.filter(id=commune_filter).first() if commune_filter else None
    selected_responsible = responsible_employees_by_id.get(responsible_employee_filter)

    ordering = (
        (
            F("date").desc(nulls_last=True),
            F("created_at").desc(nulls_last=True),
            "-id",
        )
        if sort_mode == "intervention_date"
        else (
            F("created_at").desc(nulls_last=True),
            F("updated_at").desc(nulls_last=True),
            "-id",
        )
    )
    plannings = filtered_plannings.select_related(
        "ouvrage",
        "ouvrage__type_ouvrage",
        "fiche_poste",
        "type_activite",
        "employe",
        "employe__base",
    ).prefetch_related(
        Prefetch("details", queryset=detail_queryset, to_attr="recent_details"),
    ).order_by(*ordering).distinct()

    page = Paginator(plannings, 20).get_page(request.GET.get("page", 1))
    card_ouvrages = _attach_ouvrage_card_metrics({
        str(planning.ouvrage_id): planning.ouvrage
        for planning in page.object_list
        if planning.ouvrage_id and planning.ouvrage
    }.values(), include_indemnities=_can_see_indemnities(request.user))
    card_ouvrages_by_id = {
        str(ouvrage.id): ouvrage for ouvrage in card_ouvrages
    }
    preserved_params = []
    if include_other_bases:
        preserved_params.append(("all_bases", "1"))
    if period_filter:
        preserved_params.append(("period", period_filter))
    if employee_filter:
        preserved_params.append(("employee", employee_filter))
    if ouvrage_filter:
        preserved_params.append(("ouvrage", ouvrage_filter))
    if region_filter:
        preserved_params.append(("region", region_filter))
    if district_filter:
        preserved_params.append(("district", district_filter))
    if commune_filter:
        preserved_params.append(("commune", commune_filter))
    if responsible_employee_filter:
        preserved_params.append(("responsible_employee", responsible_employee_filter))
    if status_filter_active:
        preserved_params.append(("status_filter", "1"))
        preserved_params.extend(("status", status) for status in selected_statuses)
    if sort_mode != "created_at":
        preserved_params.append(("sort", sort_mode))
    pagination_query = urlencode(preserved_params)
    can_edit_interventions = not bool(getattr(request.user, "client", None)) or request.user.is_staff
    editable_ouvrage_ids = set()
    if can_edit_interventions:
        editable_ouvrage_ids = {
            str(ouvrage_id)
            for ouvrage_id in _accessible_ouvrages(request.user).filter(
                id__in=[planning.ouvrage_id for planning in page.object_list if planning.ouvrage_id]
            ).values_list("id", flat=True)
        }
    now = timezone.now()
    today = timezone.localdate(now)
    doublons_par_planning = calculer_doublons_securise([p.id for p in page.object_list])
    for planning in page.object_list:
        planning.saisie_doublons = doublons_par_planning.get(str(planning.id))
        planning.card_ouvrage = card_ouvrages_by_id.get(str(planning.ouvrage_id or ""))
        planning.saisie_can_edit = str(planning.ouvrage_id or "") in editable_ouvrage_ids
        planning.saisie_can_delete = (
            planning.saisie_can_edit and is_directeur_poste(request.user)
        )
        planning.saisie_created_relative = _format_relative_day_duration(
            planning.created_at,
            reference_date=today,
        )
        planning.saisie_date_iso = ""
        planning.saisie_date_relative = ""
        planning.saisie_requires_action = False
        planning.saisie_is_upcoming = False
        planning.saisie_is_today = False
        if planning.date:
            planning_date = timezone.localtime(planning.date) if timezone.is_aware(planning.date) else planning.date
            planning.saisie_date_iso = planning_date.strftime("%Y-%m-%d")
            day_delta = (planning_date.date() - today).days
            planning.saisie_requires_action = (
                day_delta < 0 and planning.statut != "termine"
            )
            planning.saisie_is_upcoming = (
                day_delta > 0 and planning.statut != "termine"
            )
            planning.saisie_is_today = (
                day_delta == 0 and planning.statut != "termine"
            )
            planning.saisie_date_relative = _format_relative_day_duration(
                planning_date,
                reference_date=today,
            )
        planning.saisie_update_url = reverse(
            "core:modifier_intervention_ouvrage",
            kwargs={"ouvrage_id": planning.ouvrage_id, "planning_id": planning.id},
        )
        planning.saisie_delete_url = reverse(
            "core:supprimer_intervention_ouvrage",
            kwargs={"ouvrage_id": planning.ouvrage_id, "planning_id": planning.id},
        )
        planning.saisie_options_url = reverse(
            "core:options_intervention_ouvrage",
            kwargs={"ouvrage_id": planning.ouvrage_id},
        )
        if not planning.created_at:
            planning.saisie_badge_class = "badge-neutral"
        elif planning.created_at >= now - timedelta(days=7):
            planning.saisie_badge_class = "badge-info"
        elif planning.created_at >= now - timedelta(days=30):
            planning.saisie_badge_class = "badge-success"
        else:
            planning.saisie_badge_class = "bg-orange-500 text-white border-orange-500"
        planning.saisie_photos = [
            {
                "name": photo["name"],
                "type": photo["type"],
                "is_video": photo["is_video"],
                "url": reverse(
                    "core:photo_intervention_ouvrage",
                    kwargs={
                        "ouvrage_id": planning.ouvrage_id,
                        "planning_id": planning.id,
                        "photo_index": index,
                    },
                ),
            }
            for index, photo in enumerate(_planning_attachments(planning.photo))
        ]
        planning.saisie_cibles = []
        planning.saisie_target_type = ""
        planning.saisie_target_id = ""
        for detail in planning.recent_details:
            target = None
            if detail.point_eau:
                target = f"Point d'eau : {detail.point_eau.code_point_eau or detail.point_eau.nomabonne or detail.point_eau.id}"
                if not planning.saisie_target_id:
                    planning.saisie_target_type = "point_eau"
                    planning.saisie_target_id = str(detail.point_eau_id)
            elif detail.equipement_constitutif:
                target = f"Équipement : {detail.equipement_constitutif.nom or detail.equipement_constitutif.id}"
                if not planning.saisie_target_id:
                    planning.saisie_target_type = "equipement"
                    planning.saisie_target_id = str(detail.equipement_constitutif_id)
            if target and target not in planning.saisie_cibles:
                planning.saisie_cibles.append(target)

    return render(
        request,
        "core/interventions_recentes.html",
        {
            "debit_scope_ids": list(accessible_ouvrages.order_by().values_list("id", flat=True)),
            "title": "Dernières saisies de réparations",
            "page_obj": page,
            "include_other_bases": include_other_bases,
            "intervention_stats": statistics,
            "can_edit_interventions": can_edit_interventions,
            "can_delete_interventions": is_directeur_poste(request.user),
            "period_filter": period_filter,
            "employee_filter": employee_filter,
            "ouvrage_filter": ouvrage_filter,
            "region_filter": region_filter,
            "district_filter": district_filter,
            "commune_filter": commune_filter,
            "responsible_employee_filter": responsible_employee_filter,
            "regions": regions,
            "districts": districts,
            "communes": communes,
            "responsible_employees": responsible_employees,
            "selected_region_label": selected_region.nom_region if selected_region else "",
            "selected_district_label": selected_district.nom_district if selected_district else "",
            "selected_commune_label": selected_commune.nom_commune if selected_commune else "",
            "selected_responsible_label": selected_responsible.nom_affichage if selected_responsible else "",
            "has_statistics_filter": has_statistics_filter,
            "filter_labels": filter_labels,
            "pagination_query": pagination_query,
            "status_filter_active": status_filter_active,
            "selected_statuses": selected_statuses,
            "sort_mode": sort_mode,
            "status_choices": [
                {"code": "en_cours", "label": "En cours", "class": "checkbox-warning"},
                {"code": "termine", "label": "Terminé", "class": "checkbox-success"},
                {"code": "annule", "label": "Annulé", "class": "checkbox-error"},
                {"code": "reporte", "label": "Reporté", "class": "checkbox-info"},
            ],
        },
    )


@mobile_auth_required
@require_GET
def options_intervention_ouvrage(request, ouvrage_id):
    """Options du formulaire rapide, limitées à l'ouvrage accessible."""
    if getattr(request.user, "client", None) and not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Accès réservé aux utilisateurs internes."}, status=403)

    ouvrage = get_object_or_404(
        _accessible_ouvrages(request.user).select_related("type_ouvrage"),
        id=ouvrage_id,
    )
    ouvrage_type_name = getattr(ouvrage.type_ouvrage, "nom_type_ouvrage", "") or ""
    is_pmh_ouvrage = _is_pmh_ouvrage(ouvrage_type_name)
    equipment_types = list(
        TypeEquipement.objects.filter(is_active=True).values("id", "nom_type")
    )
    configured_activity_ids = {
        str(policy.type_equipement_id): {
            str(activity.id) for activity in policy.allowed_activities.all()
        }
        for policy in RepairActivityEquipmentPolicy.objects
        .filter(type_equipement_id__in=[item["id"] for item in equipment_types])
        .prefetch_related("allowed_activities")
    }
    point_types = list(TypePointEau.objects.filter(actif=True).values("id", "nom_type"))
    configured_point_activity_ids = {
        str(policy.type_point_eau_id): {
            str(activity.id) for activity in policy.allowed_activities.all()
        }
        for policy in RepairActivityPointTypePolicy.objects
        .filter(type_point_eau_id__in=[item["id"] for item in point_types])
        .prefetch_related("allowed_activities")
    }
    activities = []
    for fiche in _get_quick_repair_fiches_queryset().order_by("tache"):
        activity_label = fiche.tache or ""
        metadata = _activity_target_metadata(activity_label, equipment_types)
        allowed_equipment_type_ids = []
        for equipment_type in equipment_types:
            type_id = str(equipment_type["id"])
            if type_id in configured_activity_ids:
                is_allowed = str(fiche.id) in configured_activity_ids[type_id]
            else:
                is_allowed = _activity_allowed_for_target(
                    activity_label,
                    ouvrage_type_name,
                    "equipement",
                    equipment_type["nom_type"],
                    equipment_type["id"],
                    metadata,
                )
            if is_allowed:
                allowed_equipment_type_ids.append(type_id)
        allowed_point_type_ids = []
        normalized_activity = _policy_text(activity_label)
        for point_type in point_types:
            type_id = str(point_type["id"])
            if type_id in configured_point_activity_ids:
                is_allowed = str(fiche.id) in configured_point_activity_ids[type_id]
                if "pmh" in normalized_activity and not is_pmh_ouvrage:
                    is_allowed = False
                if is_pmh_ouvrage and "citerne" in normalized_activity:
                    is_allowed = False
            else:
                is_allowed = _activity_allowed_for_target(
                    activity_label,
                    ouvrage_type_name,
                    "point_eau",
                    fallback_metadata=metadata,
                )
            if is_allowed:
                allowed_point_type_ids.append(type_id)
        activities.append({
            "id": str(fiche.id),
            "label": activity_label,
            "type_label": fiche.type_activites.nomtype if fiche.type_activites else "Sans type",
            "requires_signalement_date": _requires_signalement_date(activity_label),
            "composants_regles": regles_fiche(fiche),
            "allowed_point_eau": _activity_allowed_for_target(
                activity_label,
                ouvrage_type_name,
                "point_eau",
                fallback_metadata=metadata,
            ),
            "allowed_point_type_ids": allowed_point_type_ids,
            "allowed_equipment_type_ids": allowed_equipment_type_ids,
        })
    ouvrage_points = sorted(
        PointEau.objects.filter(ouvrage=ouvrage).select_related(
            "type_point_eau",
            "parcelle__village",
        ),
        key=_quick_point_eau_sort_key,
    )
    village_reference = next(
        (
            point.parcelle.village
            for point in ouvrage_points
            if point.parcelle_id
            and point.parcelle.village_id
            and point.parcelle.village.latitude is not None
            and point.parcelle.village.longitude is not None
        ),
        None,
    )
    points = [
        {
            "id": str(point.id),
            "label": _quick_point_eau_label(point),
            "type_id": str(point.type_point_eau_id or ""),
            "has_photos": _has_photos(point.photos),
            "photos_count": len(point.photos) if isinstance(point.photos, list) else int(_has_photos(point.photos)),
            "has_coordinates": point.latitude is not None and point.longitude is not None,
            "latitude": point.latitude,
            "longitude": point.longitude,
            "map_latitude": (
                float(point.parcelle.village.latitude)
                if point.parcelle_id and point.parcelle.village_id and point.parcelle.village.latitude is not None
                else float(village_reference.latitude) if village_reference else None
            ),
            "map_longitude": (
                float(point.parcelle.village.longitude)
                if point.parcelle_id and point.parcelle.village_id and point.parcelle.village.longitude is not None
                else float(village_reference.longitude) if village_reference else None
            ),
            "village_name": (
                point.parcelle.village.nom_village
                if point.parcelle_id and point.parcelle.village_id
                else village_reference.nom_village if village_reference else ""
            ),
        }
        for point in ouvrage_points
    ]
    equipements = [
        {
            "id": str(equipement.id),
            "label": (
                f"{equipement.nom} — {equipement.type_equipement.nom_type}"
                if equipement.type_equipement else equipement.nom
            ),
            "type_id": str(equipement.type_equipement_id or ""),
            "type_label": equipement.type_equipement.nom_type if equipement.type_equipement else "",
            "is_captage": "captage" in normalize_repair_text(
                equipement.type_equipement.nom_type if equipement.type_equipement else ""
            ),
            "has_photos": _has_photos(equipement.photos),
            "photos_count": len(equipement.photos) if isinstance(equipement.photos, list) else int(_has_photos(equipement.photos)),
            "has_coordinates": equipement.latitude is not None and equipement.longitude is not None,
            "latitude": float(equipement.latitude) if equipement.latitude is not None else None,
            "longitude": float(equipement.longitude) if equipement.longitude is not None else None,
            "map_latitude": float(village_reference.latitude) if village_reference else None,
            "map_longitude": float(village_reference.longitude) if village_reference else None,
            "village_name": village_reference.nom_village if village_reference else "",
        }
        for equipement in EquipementConstitutif.objects.filter(ouvrage=ouvrage)
        .select_related("type_equipement")
        .order_by("nom")
    ]
    debit_history = []
    previous_debit = None
    for measure in reversed(list(
        DebitSourceMesure.objects.filter(ouvrage=ouvrage)
        .select_related("employe")
        .order_by("-date_visite", "-created_at")[:10]
    )):
        debit_value = float(measure.debit_l_s)
        debit_history.append({
            "date": measure.date_visite.strftime("%d/%m/%Y"),
            "debit": debit_value,
            "employee": measure.employe.nom_affichage if measure.employe else "Non affecte",
            "delta": round(debit_value - previous_debit, 3) if previous_debit is not None else None,
        })
        previous_debit = debit_value
    debit_history.reverse()
    actor = getattr(request.user, "employe", None)
    active_employees = _active_intervention_employees(request.user)
    employees = [
        {
            "id": str(employee.id),
            "label": employee.nom_affichage,
            "base_label": employee.base.nom_base or "Base non definie",
            "poste_label": employee.poste.nom_poste if employee.poste else "Sans poste",
        }
        for employee in sorted(
            active_employees,
            key=lambda employee: (
                (employee.base.nom_base or "").casefold(),
                (employee.poste.nom_poste if employee.poste else "Sans poste").casefold(),
                (employee.nom_affichage or "").casefold(),
            ),
        )
    ]
    return JsonResponse({
        "success": True,
        "ouvrage": {
            "id": str(ouvrage.id),
            "nom": ouvrage.nom_ouvrage,
            "type": ouvrage_type_name,
            "is_pmh": is_pmh_ouvrage,
        },
        "activities": activities,
        "points": points,
        "equipements": equipements,
        "debit_history": debit_history,
        "debit_source_url": f"{reverse('planning:debit_source')}?ouvrage={ouvrage.id}",
        "employees": employees,
        "default_employee_id": (
            str(actor.id)
            if actor and any(employee["id"] == str(actor.id) for employee in employees)
            else ""
        ),
    })


def _historique_interventions(ouvrage):
    # Utiliser exactement le meme catalogue que la saisie avec photos et la
    # page des interventions recentes. Une intervention visible dans ce fil
    # ne doit pas disparaitre de l'historique de son ouvrage.
    fiche_ids = list(
        _get_quick_repair_fiches_queryset().values_list("id", flat=True)
    )
    old_activity_ids = list(Activite.objects.filter(
        Q(nom__icontains="réparation")
        | Q(nom__icontains="reparation")
        | Q(nom__icontains="réhabilitation")
        | Q(nom__icontains="rehabilitation")
        | Q(nom__icontains="panne")
        | Q(nom__icontains="entretien")
        | Q(nom__icontains="maintenance")
    ).values_list("id", flat=True))

    # CRITICAL: la liste doit couvrir exactement les mêmes plannings que le
    # badge "X échue(s)" des cartes ouvrage (unfinished_overdue_contributions_count),
    # sinon l'historique affiche moins d'interventions que ce que le compteur annonce.
    # On part donc de Planning (comme le compteur), rattaché à l'ouvrage soit
    # directement, soit via un de ses PlanningDetail (point d'eau / équipement).
    plannings = Planning.objects.filter(
        Q(ouvrage=ouvrage)
        | Q(details__point_eau__ouvrage=ouvrage)
        | Q(details__equipement_constitutif__ouvrage=ouvrage),
    ).filter(
        Q(fiche_poste_id__in=fiche_ids)
        | Q(fiche_poste__activites_postes__activite_id__in=old_activity_ids)
        | Q(remarque__startswith="[Saisie depuis la fiche ouvrage]")
    ).select_related(
        "fiche_poste",
        "type_activite",
        "employe",
    ).prefetch_related(
        Prefetch(
            "details",
            queryset=PlanningDetail.objects.filter(
                Q(point_eau__ouvrage=ouvrage) | Q(equipement_constitutif__ouvrage=ouvrage)
            ).select_related("point_eau", "equipement_constitutif"),
            to_attr="ouvrage_details",
        )
    ).order_by("-date").distinct()

    records = {}
    for planning in plannings:
        if is_excluded_repair_activity(planning.activite_display):
            continue
        key = str(planning.id)
        if key in records:
            continue
        classification = get_planning_repair_classification(planning)
        family_labels = {
            "reparation": "Réparation / entretien",
            "rehabilitation": "Réhabilitation",
            "panne": "Panne",
        }
        photos = _planning_attachments(planning.photo)
        planning_date = planning.date
        if planning_date and timezone.is_aware(planning_date):
            planning_date = timezone.localtime(planning_date)
        requires_action = bool(
            planning_date
            and planning_date.date() < timezone.localdate()
            and (planning.statut or "") in ("", *ACTIVE_INTERVENTION_STATUSES)
        )
        cibles = []
        for detail in getattr(planning, "ouvrage_details", []):
            target = None
            if detail.point_eau:
                target = f"Point d'eau : {detail.point_eau.code_point_eau or detail.point_eau.nomabonne or detail.point_eau.id}"
            elif detail.equipement_constitutif:
                target = f"Équipement : {detail.equipement_constitutif.nom or detail.equipement_constitutif.id}"
            if target and target not in cibles:
                cibles.append(target)
        records[key] = {
            "id": key,
            "date": planning_date.strftime("%d/%m/%Y") if planning_date else "-",
            "date_iso": planning_date.strftime("%Y-%m-%d") if planning_date else "",
            "activite": planning.activite_display,
            "famille": family_labels.get(classification["family"], "Intervention"),
            "employe": planning.employe.nom_affichage if planning.employe else "Non affecté",
            "employe_id": str(planning.employe_id or ""),
            "remarque": planning.remarque or "",
            "statut": planning.get_statut_display() if planning.statut else "Non défini",
            "statut_code": planning.statut or "",
            "update_url": reverse(
                "core:modifier_intervention_ouvrage",
                kwargs={"ouvrage_id": ouvrage.id, "planning_id": planning.id},
            ),
            "delete_url": reverse(
                "core:supprimer_intervention_ouvrage",
                kwargs={"ouvrage_id": ouvrage.id, "planning_id": planning.id},
            ),
            "requires_action": requires_action,
            "photos": [
                {
                    "name": photo["name"],
                    "type": photo["type"],
                    "is_video": photo["is_video"],
                    "url": reverse(
                        "core:photo_intervention_ouvrage",
                        kwargs={
                            "ouvrage_id": ouvrage.id,
                            "planning_id": planning.id,
                            "photo_index": index,
                        },
                    ),
                }
                for index, photo in enumerate(photos)
            ],
            "cibles": cibles,
        }
    doublons = calculer_doublons_securise(list(records.keys()))
    for key, record in records.items():
        record["doublons"] = doublons.get(key)
    return list(records.values())


@login_required
@require_GET
def historique_interventions_ouvrage(request, ouvrage_id):
    """Historique paginé chargé à la demande depuis la recherche rapide."""
    ouvrage = get_object_or_404(
        _accessible_ouvrages(request.user).select_related("type_ouvrage"),
        id=ouvrage_id,
    )
    show_completed = request.GET.get("show_completed", "").lower() in {
        "1", "true", "on", "yes",
    }
    history = _historique_interventions(ouvrage)
    completed_count = sum(item["statut_code"] == "termine" for item in history)
    if not show_completed:
        history = [item for item in history if item["statut_code"] != "termine"]
    page = Paginator(history, 5).get_page(request.GET.get("page", 1))
    return JsonResponse({
        "success": True,
        "ouvrage": {"id": str(ouvrage.id), "nom": ouvrage.nom_ouvrage},
        "can_edit": not bool(getattr(request.user, "client", None)) or request.user.is_staff,
        "can_delete": is_directeur_poste(request.user),
        "items": list(page.object_list),
        "pagination": {
            "page": page.number,
            "pages": page.paginator.num_pages,
            "count": page.paginator.count,
            "completed_count": completed_count,
            "show_completed": show_completed,
            "has_previous": page.has_previous(),
            "has_next": page.has_next(),
        },
    })


@csrf_exempt
@mobile_auth_required
@require_POST
@transaction.atomic
def modifier_intervention_ouvrage(request, ouvrage_id, planning_id):
    """Met a jour les champs rapides d'une intervention depuis son historique."""
    if getattr(request.user, "client", None) and not request.user.is_staff:
        return JsonResponse(
            {"success": False, "error": "Cette modification est reservee aux utilisateurs internes."},
            status=403,
        )

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Donnees JSON invalides."}, status=400)

    ouvrage = _accessible_ouvrages(request.user).filter(id=ouvrage_id).first()
    if not ouvrage:
        return JsonResponse(
            {"success": False, "error": "Ouvrage introuvable ou hors de votre perimetre."},
            status=404,
        )
    planning = (
        Planning.objects.filter(
            Q(ouvrage=ouvrage)
            | Q(details__point_eau__ouvrage=ouvrage)
            | Q(details__equipement_constitutif__ouvrage=ouvrage)
        ).filter(id=planning_id).distinct().first()
    )
    if not planning:
        return JsonResponse(
            {"success": False, "error": "Intervention introuvable pour cet ouvrage."},
            status=404,
        )

    target_detail = (
        planning.details.filter(
            Q(point_eau__ouvrage=ouvrage)
            | Q(equipement_constitutif__ouvrage=ouvrage)
        )
        .select_related(
            "point_eau__type_point_eau",
            "equipement_constitutif__type_equipement",
        )
        .order_by("created_at", "id")
        .first()
    )
    current_target_type = ""
    current_target_id = ""
    if target_detail and target_detail.point_eau_id:
        current_target_type = "point_eau"
        current_target_id = str(target_detail.point_eau_id)
    elif target_detail and target_detail.equipement_constitutif_id:
        current_target_type = "equipement"
        current_target_id = str(target_detail.equipement_constitutif_id)
    classification_fields_supplied = any(
        field in data for field in ("activity_id", "target_type", "target_id")
    )
    preserve_unclassified_intervention = bool(
        not current_target_type and not classification_fields_supplied
    )
    new_target_designation = None
    if not target_detail and not preserve_unclassified_intervention:
        new_target_designation = Designation.objects.filter(actif=True).order_by("nom").first()
        if not new_target_designation:
            return JsonResponse(
                {"success": False, "error": "Aucune designation active n'est configuree."},
                status=400,
            )

    target_type = str(data.get("target_type") or current_target_type).strip()
    target_id = str(data.get("target_id") or current_target_id).strip()
    point_eau = None
    equipement = None
    if preserve_unclassified_intervention:
        pass
    elif target_type == "point_eau":
        try:
            point_eau = (
                PointEau.objects.filter(id=target_id, ouvrage=ouvrage)
                .select_related("type_point_eau")
                .first()
            )
        except (ValidationError, ValueError):
            point_eau = None
    elif target_type == "equipement":
        try:
            equipement = (
                EquipementConstitutif.objects.filter(id=target_id, ouvrage=ouvrage)
                .select_related("type_equipement")
                .first()
            )
        except (ValidationError, ValueError):
            equipement = None
    else:
        return JsonResponse({"success": False, "error": "Choisissez le type de cible."}, status=400)
    if not preserve_unclassified_intervention and not point_eau and not equipement:
        return JsonResponse(
            {"success": False, "error": "La cible choisie n'appartient pas a cet ouvrage."},
            status=400,
        )

    activity_id = str(data.get("activity_id") or planning.fiche_poste_id or "").strip()
    activity_changed = activity_id != str(planning.fiche_poste_id or "")
    target_changed = target_type != current_target_type or target_id != current_target_id
    if not activity_changed and planning.fiche_poste_id:
        fiche = planning.fiche_poste
    else:
        try:
            fiche = _get_quick_repair_fiches_queryset().filter(id=activity_id).first()
        except (ValidationError, ValueError):
            fiche = None
    if not fiche:
        return JsonResponse(
            {"success": False, "error": "Selectionnez une activite de reparation ou d'entretien valide."},
            status=400,
        )

    # Une ancienne combinaison reste modifiable telle quelle. En revanche,
    # tout changement d'activite ou de cible respecte les regles du formulaire
    # de creation afin d'eviter une association incoherente.
    if activity_changed or target_changed:
        equipment_types = list(
            TypeEquipement.objects.filter(is_active=True).values("id", "nom_type")
        )
        target_policy = None
        if equipement:
            target_policy = RepairActivityEquipmentPolicy.objects.filter(
                type_equipement_id=equipement.type_equipement_id,
            ).first()
        elif point_eau and point_eau.type_point_eau_id:
            target_policy = RepairActivityPointTypePolicy.objects.filter(
                type_point_eau_id=point_eau.type_point_eau_id,
            ).first()
        if target_policy is not None:
            is_activity_allowed = target_policy.allowed_activities.filter(id=fiche.id).exists()
            normalized_activity = _policy_text(fiche.tache or "")
            is_pmh_ouvrage = _is_pmh_ouvrage(
                getattr(ouvrage.type_ouvrage, "nom_type_ouvrage", "") or ""
            )
            if "pmh" in normalized_activity and not is_pmh_ouvrage:
                is_activity_allowed = False
            if is_pmh_ouvrage and "citerne" in normalized_activity:
                is_activity_allowed = False
        else:
            is_activity_allowed = _activity_allowed_for_target(
                fiche.tache or "",
                getattr(ouvrage.type_ouvrage, "nom_type_ouvrage", "") or "",
                target_type,
                getattr(getattr(equipement, "type_equipement", None), "nom_type", "") or "",
                getattr(equipement, "type_equipement_id", None),
                _activity_target_metadata(fiche.tache or "", equipment_types),
            )
        if not is_activity_allowed:
            return JsonResponse(
                {"success": False, "error": "Cette activite ne correspond pas a la cible choisie."},
                status=400,
            )

    date_intervention = parse_date(str(data.get("date") or ""))
    if not date_intervention:
        return JsonResponse({"success": False, "error": "La date est obligatoire."}, status=400)

    planning_status = str(data.get("status") or "").strip()
    if planning_status not in dict(Planning.STATUS_CHOICES):
        return JsonResponse({"success": False, "error": "Le statut choisi est invalide."}, status=400)

    employee_id = str(data.get("employee_id") or "").strip()
    selected_employee = None
    if employee_id:
        if employee_id == str(planning.employe_id or ""):
            selected_employee = planning.employe
        else:
            try:
                selected_employee = _active_intervention_employees(request.user).filter(
                    id=employee_id,
                ).first()
            except (ValidationError, ValueError):
                selected_employee = None
            if not selected_employee:
                return JsonResponse(
                    {"success": False, "error": "Choisissez un employe actif autorise pour votre compte."},
                    status=400,
                )

    existing_attachments = _planning_attachments(planning.photo)
    raw_indexes = data.get("existing_attachment_indexes", [])
    if not isinstance(raw_indexes, list):
        return JsonResponse({"success": False, "error": "Liste des pieces existantes invalide."}, status=400)
    try:
        kept_indexes = {int(index) for index in raw_indexes}
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "Indice de piece jointe invalide."}, status=400)
    if any(index < 0 or index >= len(existing_attachments) for index in kept_indexes):
        return JsonResponse({"success": False, "error": "Une piece jointe existante est introuvable."}, status=400)

    try:
        new_attachments = _normalize_attachments(data.get("attachments") or [])
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    attachments = [
        {
            "data": attachment["data"],
            "name": attachment["name"],
            "type": attachment["type"],
        }
        for index, attachment in enumerate(existing_attachments)
        if index in kept_indexes
    ] + new_attachments
    if len(attachments) > MAX_ATTACHMENTS:
        return JsonResponse(
            {"success": False, "error": f"Vous pouvez conserver ou ajouter au maximum {MAX_ATTACHMENTS} pieces jointes."},
            status=400,
        )
    if sum(len(attachment["data"]) for attachment in attachments) > MAX_ATTACHMENT_PAYLOAD:
        return JsonResponse(
            {"success": False, "error": "Les pieces jointes sont trop volumineuses (45 Mo maximum au total)."},
            status=400,
        )

    local_time = time(hour=8)
    if planning.date:
        current_date = timezone.localtime(planning.date) if timezone.is_aware(planning.date) else planning.date
        local_time = current_date.time().replace(tzinfo=None)
    planning.date = timezone.make_aware(datetime.combine(date_intervention, local_time))
    planning.employe = selected_employee
    planning.statut = planning_status
    planning.fiche_poste = fiche
    planning.type_activite = fiche.type_activites
    planning.suiteadonner = "Termine" if planning_status == "termine" else "A suivre"
    planning.photo = json.dumps(attachments, ensure_ascii=False) if attachments else None
    if target_changed and planning.remarque:
        remark_lines = planning.remarque.splitlines()
        if remark_lines and remark_lines[0].startswith("[Saisie depuis la fiche ouvrage]"):
            target_kind = "Point d'eau" if point_eau else "Equipement"
            target_label = (
                point_eau.code_point_eau or point_eau.nomabonne or str(point_eau.id)
                if point_eau
                else equipement.nom or str(equipement.id)
            )
            remark_lines[0] = f"[Saisie depuis la fiche ouvrage] {target_kind}: {target_label}"
            planning.remarque = "\n".join(remark_lines)
    planning.save(update_fields=[
        "date", "employe", "statut", "fiche_poste", "type_activite",
        "suiteadonner", "photo", "remarque", "updated_at",
    ])

    if target_detail:
        target_detail.point_eau = point_eau
        target_detail.equipement_constitutif = equipement
        target_detail.save(update_fields=["point_eau", "equipement_constitutif", "updated_at"])
    elif not preserve_unclassified_intervention:
        PlanningDetail.objects.create(
            planning=planning,
            designation=new_target_designation,
            quantity=1,
            pu=Decimal("0.00"),
            montant=Decimal("0.00"),
            point_eau=point_eau,
            equipement_constitutif=equipement,
        )

    from apps.messaging.repair_sync import ensure_repair_conversation

    try:
        ensure_repair_conversation(planning, actor=getattr(request.user, "employe", None), notify=False)
    except Exception:
        # La synchronisation de messagerie est secondaire et ne doit pas annuler
        # une modification de l'intervention deja enregistree.
        import logging

        logging.getLogger(__name__).exception(
            "Echec de synchronisation de la conversation pour le planning %s",
            planning.id,
        )
    overdue_summary = _overdue_activity_summary_by_ouvrage([ouvrage.id])
    overdue_count = overdue_summary["counts"].get(ouvrage.id, 0)
    overdue_category = (
        "repair"
        if ouvrage.id in overdue_summary["repair_ouvrage_ids"]
        else "maintenance"
        if ouvrage.id in overdue_summary["maintenance_only_ouvrage_ids"]
        else "none"
    )
    activity_deadline_counts = {
        bucket: counts.get(ouvrage.id, 0)
        for bucket, counts in overdue_summary["activity_counts"].items()
    }
    return JsonResponse({
        "success": True,
        "message": "L'intervention a ete mise a jour.",
        "overdue_count": overdue_count,
        "overdue_category": overdue_category,
        "activity_deadline_counts": activity_deadline_counts,
    })


@login_required
@require_POST
@transaction.atomic
def supprimer_intervention_ouvrage(request, ouvrage_id, planning_id):
    """Supprime une intervention accessible apres confirmation dans l'interface."""
    if not is_directeur_poste(request.user):
        return JsonResponse(
            {"success": False, "error": "Cette suppression est réservée aux directeurs."},
            status=403,
        )

    ouvrage = _accessible_ouvrages(request.user).filter(id=ouvrage_id).first()
    if not ouvrage:
        return JsonResponse(
            {"success": False, "error": "Ouvrage introuvable ou hors de votre perimetre."},
            status=404,
        )
    planning = (
        Planning.objects.filter(
            Q(ouvrage=ouvrage)
            | Q(details__point_eau__ouvrage=ouvrage)
            | Q(details__equipement_constitutif__ouvrage=ouvrage)
        ).filter(id=planning_id).distinct().first()
    )
    if not planning:
        return JsonResponse(
            {"success": False, "error": "Intervention introuvable pour cet ouvrage."},
            status=404,
        )

    # La conversation de suivi utilise une cle textuelle et n'a pas de FK vers
    # le planning : elle doit donc etre supprimee explicitement avec celui-ci.
    from apps.messaging.models import Conversation

    Conversation.objects.filter(
        type="group",
        description__startswith=f"repair_planning:{planning.id}",
    ).delete()
    planning.delete()
    return JsonResponse({"success": True, "message": "L'intervention a ete supprimee."})


def _normalize_attachments(raw_attachments):
    if not isinstance(raw_attachments, list):
        raise ValueError("Le format des pieces jointes est invalide.")
    if len(raw_attachments) > MAX_ATTACHMENTS:
        raise ValueError(f"Vous pouvez ajouter au maximum {MAX_ATTACHMENTS} pieces jointes.")

    attachments = []
    total_size = 0
    for index, attachment in enumerate(raw_attachments, start=1):
        if not isinstance(attachment, dict):
            raise ValueError("Le format d'une piece jointe est invalide.")
        data = attachment.get("data") or ""
        content_type = str(attachment.get("type") or "").lower()
        if isinstance(data, str) and data.startswith("data:"):
            content_type = data[5:].split(";", 1)[0].lower()
        if not isinstance(data, str) or not data.startswith("data:") or content_type not in ALLOWED_ATTACHMENT_TYPES:
            raise ValueError(f"La piece jointe {index} n'est pas une image ou video valide.")
        total_size += len(data)
        if total_size > MAX_ATTACHMENT_PAYLOAD:
            raise ValueError("Les pieces jointes sont trop volumineuses (45 Mo maximum au total).")
        attachments.append(
            {
                "data": data,
                "name": str(attachment.get("name") or f"piece-jointe-{index}")[:180],
                "type": content_type,
            }
        )
    return attachments


@login_required
@require_GET
def photo_intervention_ouvrage(request, ouvrage_id, planning_id, photo_index):
    """Sert une photo à la demande afin de garder la fiche ouvrage légère."""
    ouvrage = get_object_or_404(_accessible_ouvrages(request.user), id=ouvrage_id)
    planning = get_object_or_404(
        Planning.objects.filter(
            Q(ouvrage=ouvrage)
            | Q(details__point_eau__ouvrage=ouvrage)
            | Q(details__equipement_constitutif__ouvrage=ouvrage)
        ).distinct(),
        id=planning_id,
    )

    photos = _planning_attachments(planning.photo)
    if photo_index < 0 or photo_index >= len(photos):
        return HttpResponseBadRequest("Photo introuvable.")

    source = photos[photo_index]["data"]
    if source.startswith(("http://", "https://", "/media/")):
        from django.shortcuts import redirect

        return redirect(source)

    try:
        header, encoded = source.split(",", 1)
        content_type = header[5:].split(";", 1)[0]
        if content_type not in ALLOWED_ATTACHMENT_TYPES:
            raise ValueError
        attachment_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return HttpResponseBadRequest("Photo invalide.")

    response = HttpResponse(attachment_bytes, content_type=content_type)
    response["Content-Disposition"] = 'inline; filename="piece-jointe-intervention"'
    response["Cache-Control"] = "private, max-age=3600"
    return response


@login_required
@require_POST
def ajouter_intervention_ouvrage(request, ouvrage_id):
    """Ajoute une réparation/maintenance à un équipement ou point d'eau."""
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Données JSON invalides."}, status=400)

    if getattr(request.user, "client", None) and not request.user.is_staff:
        return JsonResponse(
            {"success": False, "error": "Cette saisie est réservée aux utilisateurs internes."},
            status=403,
        )

    ouvrage = get_object_or_404(
        _accessible_ouvrages(request.user).select_related("type_ouvrage"),
        id=ouvrage_id,
    )
    date_intervention = parse_date(str(data.get("date") or ""))
    if not date_intervention:
        return JsonResponse({"success": False, "error": "La date est obligatoire."}, status=400)

    target_type = data.get("target_type")
    target_id = data.get("target_id")
    point_eau = None
    equipement = None
    if target_type == "point_eau":
        point_eau = (
            PointEau.objects
            .filter(id=target_id, ouvrage=ouvrage)
            .select_related("type_point_eau")
            .first()
        )
        target_label = getattr(point_eau, "code_point_eau", "")
    elif target_type == "equipement":
        equipement = (
            EquipementConstitutif.objects
            .filter(id=target_id, ouvrage=ouvrage)
            .select_related("type_equipement")
            .first()
        )
        target_label = getattr(equipement, "nom", "")
    else:
        return JsonResponse({"success": False, "error": "Choisissez le type de cible."}, status=400)

    if not point_eau and not equipement:
        return JsonResponse(
            {"success": False, "error": "La cible choisie n'appartient pas à cet ouvrage."},
            status=400,
        )

    is_captage = bool(
        equipement
        and equipement.type_equipement
        and "captage" in normalize_repair_text(equipement.type_equipement.nom_type or "")
    )
    debit_l_s = None
    if is_captage:
        raw_debit = data.get("debit_l_s")
        if raw_debit not in (None, ""):
            try:
                debit_l_s = Decimal(str(raw_debit)).quantize(Decimal("0.001"))
            except (TypeError, ValueError, ArithmeticError):
                return JsonResponse({"success": False, "error": "Le debit saisi est invalide."}, status=400)
            if not debit_l_s.is_finite() or debit_l_s < 0 or debit_l_s > Decimal("99999.999"):
                return JsonResponse(
                    {"success": False, "error": "Le debit doit etre compris entre 0 et 99 999,999 L/s."},
                    status=400,
                )

    activity_id = data.get("activity_id")
    fiche = _get_quick_repair_fiches_queryset().filter(id=activity_id).first()
    if not fiche:
        return JsonResponse(
            {"success": False, "error": "Sélectionnez une activité de réparation ou d'entretien valide."},
            status=400,
        )

    if _requires_signalement_date(fiche.tache or ""):
        date_signalement = parse_date(str(data.get("date_signalement") or ""))
        if not date_signalement:
            return JsonResponse(
                {
                    "success": False,
                    "error": "La date de signalement est obligatoire pour l'activité Réparation panne.",
                },
                status=400,
            )
        aware_date_signalement = timezone.make_aware(
            datetime.combine(date_signalement, time(hour=8))
        )
    else:
        aware_date_signalement = timezone.now()

    equipment_types = list(
        TypeEquipement.objects.filter(is_active=True).values("id", "nom_type")
    )
    activity_target = _activity_target_metadata(fiche.tache or "", equipment_types)
    target_policy = None
    if equipement:
        target_policy = RepairActivityEquipmentPolicy.objects.filter(
            type_equipement_id=equipement.type_equipement_id,
        ).first()
    elif point_eau and point_eau.type_point_eau_id:
        target_policy = RepairActivityPointTypePolicy.objects.filter(
            type_point_eau_id=point_eau.type_point_eau_id,
        ).first()
    if target_policy is not None:
        is_activity_allowed = target_policy.allowed_activities.filter(id=fiche.id).exists()
        normalized_activity = _policy_text(fiche.tache or "")
        is_pmh_ouvrage = _is_pmh_ouvrage(
            getattr(ouvrage.type_ouvrage, "nom_type_ouvrage", "") or ""
        )
        if "pmh" in normalized_activity and not is_pmh_ouvrage:
            is_activity_allowed = False
        if is_pmh_ouvrage and "citerne" in normalized_activity:
            is_activity_allowed = False
    else:
        is_activity_allowed = _activity_allowed_for_target(
            fiche.tache or "",
            getattr(ouvrage.type_ouvrage, "nom_type_ouvrage", "") or "",
            target_type,
            getattr(getattr(equipement, "type_equipement", None), "nom_type", "") or "",
            getattr(equipement, "type_equipement_id", None),
            activity_target,
        )
    if not is_activity_allowed:
        return JsonResponse(
            {"success": False, "error": "Cette activité ne correspond pas à la cible choisie."},
            status=400,
        )

    composant_ids = parse_composants_ids(data) or []
    try:
        verifier_regles_fiche(fiche, equipement, point_eau, composant_ids)
    except ComposantsError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    try:
        attachments = _normalize_attachments(data.get("attachments", data.get("photos") or []))
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    target_coordinates = None
    raw_latitude = data.get("target_latitude")
    raw_longitude = data.get("target_longitude")
    if raw_latitude not in (None, "") or raw_longitude not in (None, ""):
        try:
            latitude = Decimal(str(raw_latitude))
            longitude = Decimal(str(raw_longitude))
        except (TypeError, ValueError, ArithmeticError):
            return JsonResponse({"success": False, "error": "Les coordonnees GPS sont invalides."}, status=400)
        if not Decimal("-90") <= latitude <= Decimal("90") or not Decimal("-180") <= longitude <= Decimal("180"):
            return JsonResponse({"success": False, "error": "Les coordonnees GPS sont hors limites."}, status=400)
        target_coordinates = (latitude, longitude)

    copy_photo_to_target = data.get("copy_photo_to_target") is True
    first_image = next(
        (attachment for attachment in attachments if attachment["type"].startswith("image/")),
        None,
    )
    if copy_photo_to_target and not first_image:
        return JsonResponse(
            {"success": False, "error": "Ajoutez au moins une photo pour completer la fiche de la cible."},
            status=400,
        )

    actor = getattr(request.user, "employe", None)
    selected_employee = None
    employee_id = str(data.get("employee_id") or "").strip()
    if employee_id:
        if not actor or not actor.base_id:
            return JsonResponse(
                {"success": False, "error": "Votre compte n'est rattache a aucune base."},
                status=400,
            )
        try:
            selected_employee = _active_intervention_employees(request.user).filter(
                id=employee_id,
            ).first()
        except (ValidationError, ValueError):
            selected_employee = None
        if not selected_employee:
            return JsonResponse(
                {"success": False, "error": "Choisissez un employe actif autorise pour votre compte."},
                status=400,
            )

    planning_status = str(data.get("status") or "termine").strip()
    if planning_status not in dict(Planning.STATUS_CHOICES):
        return JsonResponse({"success": False, "error": "Le statut choisi est invalide."}, status=400)

    description = str(data.get("description") or "").strip()[:3000]
    designation = Designation.objects.filter(actif=True).order_by("nom").first()
    if not designation:
        return JsonResponse(
            {"success": False, "error": "Aucune désignation active n'est configurée."},
            status=400,
        )

    aware_date = timezone.make_aware(datetime.combine(date_intervention, time(hour=8)))
    target_kind = "Point d'eau" if point_eau else "Équipement"
    remark_lines = [f"[Saisie depuis la fiche ouvrage] {target_kind}: {target_label or target_id}"]
    if description:
        remark_lines.append(description)

    with transaction.atomic():
        planning = Planning.objects.create(
            date=aware_date,
            datesignalementactivite=aware_date_signalement,
            estvalide=False,
            statut=planning_status,
            remarque="\n".join(remark_lines),
            suiteadonner="Terminé" if planning_status == "termine" else "À suivre",
            priorite_suivi="normale",
            debitmesure=float(debit_l_s) if debit_l_s is not None else None,
            photo=json.dumps(attachments, ensure_ascii=False) if attachments else None,
            employe=selected_employee,
            type_activite=fiche.type_activites,
            fiche_poste=fiche,
            ouvrage=ouvrage,
        )
        PlanningDetail.objects.create(
            planning=planning,
            designation=designation,
            quantity=1,
            pu=Decimal("0.00"),
            montant=Decimal("0.00"),
            point_eau=point_eau,
            equipement_constitutif=equipement,
        )
        try:
            apply_repair_target(planning, equipement, point_eau, composant_ids)
        except ComposantsError as exc:
            transaction.set_rollback(True)
            return JsonResponse({"success": False, "error": str(exc)}, status=400)

        if debit_l_s is not None:
            DebitSourceMesure.objects.update_or_create(
                ouvrage=ouvrage,
                date_visite=date_intervention,
                defaults={
                    "debit_l_s": debit_l_s,
                    "remarque": description,
                    "employe": selected_employee,
                    "created_by": actor,
                },
            )

        target = point_eau or equipement
        target_update_fields = []
        if target_coordinates and not (
            target.latitude is not None and target.longitude is not None
        ):
            target.latitude, target.longitude = target_coordinates
            target_update_fields.extend(["latitude", "longitude"])

        if copy_photo_to_target and first_image and not _has_photos(target.photos):
            _, encoded_image = first_image["data"].split(",", 1)
            target.photos = [{
                "filename": first_image["name"],
                "size": (len(encoded_image) * 3) // 4,
                "content_type": first_image["type"],
                "data": encoded_image,
                "uploaded_at": timezone.now().isoformat(),
            }]
            target_update_fields.append("photos")

        if target_update_fields:
            if point_eau:
                point_eau.updatedat = timezone.now()
                point_eau.updated_by = actor
                target_update_fields.extend(["updatedat", "updated_by"])
            else:
                equipement.updated_by = request.user
                target_update_fields.append("updated_by")
            target.save(update_fields=list(dict.fromkeys(target_update_fields)))

        from apps.messaging.repair_sync import ensure_repair_conversation

        ensure_repair_conversation(planning, actor=actor, notify=True)

    detail_url = reverse(
        "core:search_detail",
        kwargs={"entity_type": "ouvrage", "entity_id": str(ouvrage.id)},
    )
    return JsonResponse(
        {
            "success": True,
            "message": "L'intervention a été enregistrée.",
            "planning_id": str(planning.id),
            "redirect_url": f"{detail_url}#section-reparations-ouvrage",
        }
    )
