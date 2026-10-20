"""API native Android pour le domaine Recherche.

Les routes Web historiques restent inchangées. Ce module pose un contrat mobile
stable, authentifié par le token ``mobile`` et applique le périmètre ouvrage
avant toute sérialisation.
"""
import json
from datetime import datetime
from uuid import UUID

from django.http import JsonResponse
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.views_search_evolved import search_api_evolved
from apps.core.views_mobile_auth import mobile_auth_required
from apps.core.search_mobile_formatting import has_coordinates, point_type_pictogram, without_zero_values
from apps.core import views_personnes
from apps.core.views_ouvrage_interventions import (
    _accessible_intervention_ouvrages,
    _accessible_ouvrages,
    _get_quick_repair_fiches_queryset,
    _historique_interventions,
    _planning_attachments,
)
from apps.billing.models import PointEau
from apps.billing.points_eau_statut import q_actif, q_coupe, q_sans_date
from apps.employees.models import Employe, EmployeOuvrages
from apps.employees.permissions import filter_queryset_by_permissions, is_directeur_poste
from apps.infrastructure.models import EquipementConstitutif
from apps.organization.models import Ouvrage
from apps.planning.models import Planning
from apps.geography.models import Commune, District, Region


SEARCH_TYPES = (
    "village", "ouvrage", "commune", "planning", "employe", "point_eau",
    "representant", "autorite", "tiers", "fournisseur", "equipement",
    "designation", "modalite", "carte_sociale",
)
DEFAULT_TYPES = tuple(value for value in SEARCH_TYPES if value != "planning")
MAX_PAGE_SIZE = 50


def _positive_int(value, default, maximum=None):
    try:
        parsed = max(1, int(value))
    except (TypeError, ValueError):
        parsed = default
    return min(parsed, maximum) if maximum else parsed


def _requested_types(request):
    raw = (request.GET.get("types") or "").strip()
    if not raw:
        return set(DEFAULT_TYPES)
    return {item.strip() for item in raw.split(",") if item.strip() in SEARCH_TYPES}


@mobile_auth_required
@require_http_methods(["GET"])
def mobile_global_search(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({
            "success": True, "results": [], "total": 0,
            "counts_by_type": {}, "page": 1, "has_next": False,
            "message": "Saisissez au moins 2 caractères.",
        })

    selected_types = _requested_types(request)
    if not selected_types:
        return JsonResponse({
            "success": True, "results": [], "total": 0,
            "counts_by_type": {}, "page": 1, "has_next": False,
        })

    # La source Web évoluée filtre les types avant requête, applique le
    # périmètre puis pagine globalement. On force ici les types par défaut
    # Android (Planning désactivé), même si le paramètre était absent.
    original_get = request.GET
    mobile_get = original_get.copy()
    mobile_get["types"] = ",".join(sorted(selected_types))
    request.GET = mobile_get
    try:
        evolved_response = search_api_evolved(request)
    finally:
        request.GET = original_get
    payload = json.loads(evolved_response.content.decode("utf-8"))
    page_results = payload.get("results", [])
    for item in page_results:
        item["web_url"] = f"/recherche/details/{item['type']}/{item['id']}/"
        item["actions"] = {"view": True, "edit": False}

    return JsonResponse({
        "success": True,
        "query": query,
        "results": page_results,
        "total": payload.get("total", 0),
        "counts_by_type": payload.get("totals_by_type", {}),
        "page": payload.get("page", 1),
        "page_size": payload.get("page_size", 20),
        "has_next": payload.get("has_next", False),
        "available_types": SEARCH_TYPES,
        "default_types": DEFAULT_TYPES,
        "cache_version": timezone.now().isoformat(),
        "scope": "authorized",
    })


def _call_session_json(view, request, *args):
    response = view(request, *args)
    return response


@mobile_auth_required
@require_http_methods(["GET"])
def mobile_people(request):
    return _call_session_json(views_personnes.personnes_annuaire_json, request)


@mobile_auth_required
@require_http_methods(["GET"])
def mobile_person_detail(request, type_key, entity_id):
    return _call_session_json(
        views_personnes.personne_details_json, request, type_key, entity_id,
    )


@csrf_exempt
@mobile_auth_required
@require_http_methods(["POST"])
def mobile_person_update(request, type_key, entity_id):
    return _call_session_json(
        views_personnes.personne_update_champs, request, type_key, entity_id,
    )


def _geo_for_work(work):
    point = work.pointeau_set.select_related(
        "parcelle__village__fokontany__commune__district__region",
    ).first()
    village = getattr(getattr(point, "parcelle", None), "village", None)
    fokontany = getattr(village, "fokontany", None)
    commune = getattr(fokontany, "commune", None)
    district = getattr(commune, "district", None)
    region = getattr(district, "region", None)
    return {
        "village": getattr(village, "nom_village", "") or "",
        "commune_id": str(commune.id) if commune else "",
        "commune": getattr(commune, "nom_commune", "") or "",
        "district_id": str(district.id) if district else "",
        "district": getattr(district, "nom_district", "") or "",
        "region_id": str(region.id) if region else "",
        "region": getattr(region, "nom_region", "") or "",
    }


def _mobile_work_row(work):
    """Serialise un ouvrage avec les noms de relations Django declares."""
    points = work.pointeau_set.all()
    return {
        "id": str(work.id),
        "name": work.nom_ouvrage or "Ouvrage sans nom",
        "type": getattr(work.type_ouvrage, "nom_type_ouvrage", "") or "",
        "points_count": points.count(),
        "equipment_count": work.equipements_constitutifs.count(),
        "web_url": f"/recherche/details/ouvrage/{work.id}/",
        **_geo_for_work(work),
    }


@mobile_auth_required
@require_http_methods(["GET"])
def mobile_works(request):
    query = (request.GET.get("q") or "").strip()
    works = _accessible_intervention_ouvrages(request.user).select_related("type_ouvrage")
    if query:
        works = works.filter(
            Q(nom_ouvrage__icontains=query)
            | Q(type_ouvrage__nom_type_ouvrage__icontains=query)
            | Q(pointeau__code_point_eau__icontains=query)
            | Q(pointeau__parcelle__village__nom_village__icontains=query)
        ).distinct()
    filters = {
        "region": "pointeau__parcelle__village__fokontany__commune__district__region_id",
        "district": "pointeau__parcelle__village__fokontany__commune__district_id",
        "commune": "pointeau__parcelle__village__fokontany__commune_id",
    }
    for parameter, lookup in filters.items():
        value = (request.GET.get(parameter) or "").strip()
        if value:
            try:
                UUID(value)
            except ValueError:
                continue
            works = works.filter(**{lookup: value}).distinct()
    employee = (request.GET.get("employee") or "").strip()
    if employee:
        try:
            UUID(employee)
        except ValueError:
            employee = ""
    if employee:
        today = timezone.localdate()
        responsible_ids = EmployeOuvrages.objects.filter(
            employe_id=employee,
            date_debut__lte=today,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=today)).values_list("ouvrage_id", flat=True)
        works = works.filter(id__in=responsible_ids)
    total = works.count()
    page = _positive_int(request.GET.get("page"), 1)
    page_size = _positive_int(request.GET.get("page_size"), 20, MAX_PAGE_SIZE)
    rows = []
    for work in works.order_by("nom_ouvrage")[(page - 1) * page_size:page * page_size]:
        rows.append(_mobile_work_row(work))
    return JsonResponse({
        "success": True, "results": rows, "total": total, "page": page,
        "page_size": page_size, "has_next": page * page_size < total,
        "scope": "authorized",
    })


@mobile_auth_required
@require_http_methods(["GET"])
def mobile_work_filters(request):
    works = _accessible_intervention_ouvrages(request.user)
    points = PointEau.objects.filter(ouvrage__in=works)
    regions = Region.objects.filter(
        id__in=points.values_list(
            "parcelle__village__fokontany__commune__district__region_id", flat=True,
        )
    ).order_by("nom_region").distinct()
    districts = District.objects.filter(
        id__in=points.values_list(
            "parcelle__village__fokontany__commune__district_id", flat=True,
        )
    ).order_by("nom_district").distinct()
    communes = Commune.objects.filter(
        id__in=points.values_list(
            "parcelle__village__fokontany__commune_id", flat=True,
        )
    ).order_by("nom_commune").distinct()
    today = timezone.localdate()
    employee_ids = EmployeOuvrages.objects.filter(
        ouvrage__in=works,
        date_debut__lte=today,
    ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=today)).values_list("employe_id", flat=True)
    employees = Employe.objects.filter(
        id__in=employee_ids,
        date_debauchage__isnull=True,
    ).order_by("nom", "surnom").distinct()

    def rows(queryset, label_field):
        return [{"id": str(item.id), "label": getattr(item, label_field) or "-"} for item in queryset]

    return JsonResponse({
        "success": True,
        "regions": rows(regions, "nom_region"),
        "districts": rows(districts, "nom_district"),
        "communes": rows(communes, "nom_commune"),
        "employees": [{"id": str(item.id), "label": item.nom_affichage} for item in employees],
    })


@mobile_auth_required
@require_http_methods(["GET"])
def mobile_interventions(request):
    include_other_bases = (request.GET.get("all_bases") or "").lower() in {"1", "true", "on"}
    works = _accessible_intervention_ouvrages(request.user, include_other_bases)
    fiche_ids = _get_quick_repair_fiches_queryset().values_list("id", flat=True)
    items = Planning.objects.filter(
        Q(ouvrage__in=works)
        | Q(details__point_eau__ouvrage__in=works)
        | Q(details__equipement_constitutif__ouvrage__in=works),
        fiche_poste_id__in=fiche_ids,
    ).select_related("ouvrage", "employe", "employe__base", "fiche_poste").prefetch_related(
        "details__point_eau__ouvrage",
        "details__equipement_constitutif__ouvrage",
    ).distinct()
    status = (request.GET.get("status") or "").strip()
    if status:
        items = items.filter(statut=status)
    geography_filters = {
        "region": "ouvrage__pointeau__parcelle__village__fokontany__commune__district__region_id",
        "district": "ouvrage__pointeau__parcelle__village__fokontany__commune__district_id",
        "commune": "ouvrage__pointeau__parcelle__village__fokontany__commune_id",
        "employee": "employe_id",
    }
    for parameter, lookup in geography_filters.items():
        value = (request.GET.get(parameter) or "").strip()
        if not value:
            continue
        try:
            UUID(value)
        except ValueError:
            continue
        items = items.filter(**{lookup: value}).distinct()
    sort = (request.GET.get("sort") or "created").strip()
    items = items.order_by("-date" if sort == "intervention" else "-created_at")
    total = items.count()
    page = _positive_int(request.GET.get("page"), 1)
    page_size = _positive_int(request.GET.get("page_size"), 20, MAX_PAGE_SIZE)
    rows = []
    editable_work_ids = {
        str(value) for value in _accessible_ouvrages(request.user)
        .values_list("id", flat=True)
    }
    internal_user = not bool(getattr(request.user, "client", None)) or request.user.is_staff
    can_delete = is_directeur_poste(request.user)
    for item in items[(page - 1) * page_size:page * page_size]:
        attachments = _planning_attachments(item.photo)
        target_detail = next((detail for detail in item.details.all() if detail.point_eau_id or detail.equipement_constitutif_id), None)
        target_type = "point_eau" if target_detail and target_detail.point_eau_id else "equipement" if target_detail and target_detail.equipement_constitutif_id else ""
        target_id = str(target_detail.point_eau_id or target_detail.equipement_constitutif_id or "") if target_detail else ""
        item_work = item.ouvrage
        if not item_work and target_detail and target_detail.point_eau_id:
            item_work = target_detail.point_eau.ouvrage
        if not item_work and target_detail and target_detail.equipement_constitutif_id:
            item_work = target_detail.equipement_constitutif.ouvrage
        item_work_id = str(item_work.id) if item_work else ""
        rows.append({
            "id": str(item.id),
            "date": item.date.isoformat() if item.date else "",
            "created_at": item.created_at.isoformat() if item.created_at else "",
            "status": item.statut or "",
            "activity": item.activite_display,
            "activity_id": str(item.fiche_poste_id or ""),
            "work_id": item_work_id,
            "work": item_work.nom_ouvrage if item_work else "",
            "employee": item.employe.nom_affichage if item.employe else "",
            "employee_id": str(item.employe_id or ""),
            "base": item.employe.base.nom_base if item.employe and item.employe.base else "",
            "description": item.remarque or "",
            "attachments": attachments,
            "target_type": target_type,
            "target_id": target_id,
            "actions": {
                "view": True,
                "edit": internal_user and item_work_id in editable_work_ids,
                "delete": can_delete and item_work_id in editable_work_ids,
                "complete": internal_user and item.statut not in {"termine", "annule"}
                and item_work_id in editable_work_ids,
                "postpone": internal_user and item.statut not in {"termine", "annule"}
                and item_work_id in editable_work_ids,
            },
        })
    return JsonResponse({
        "success": True, "results": rows, "total": total, "page": page,
        "page_size": page_size, "has_next": page * page_size < total,
    })


@csrf_exempt
@mobile_auth_required
@require_http_methods(["POST"])
def mobile_intervention_postpone(request, planning_id):
    """Reporte une intervention accessible sans modifier ses médias ni sa cible."""
    if getattr(request.user, "client", None) and not request.user.is_staff:
        return JsonResponse({
            "success": False,
            "error": "Cette modification est réservée aux utilisateurs internes.",
        }, status=403)
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Données JSON invalides."}, status=400)
    else:
        data = request.POST

    new_date = parse_date(str(data.get("date") or ""))
    if not new_date:
        return JsonResponse({"success": False, "error": "La nouvelle date est obligatoire."}, status=400)
    if new_date <= timezone.localdate():
        return JsonResponse({"success": False, "error": "Choisissez une date future."}, status=400)

    editable_works = _accessible_ouvrages(request.user)
    planning = Planning.objects.filter(
        Q(ouvrage__in=editable_works)
        | Q(details__point_eau__ouvrage__in=editable_works)
        | Q(details__equipement_constitutif__ouvrage__in=editable_works),
        id=planning_id,
    ).distinct().first()
    if not planning:
        return JsonResponse({
            "success": False,
            "error": "Intervention introuvable ou hors de votre périmètre.",
        }, status=404)
    if planning.statut in {"termine", "annule"}:
        return JsonResponse({"success": False, "error": "Cette intervention ne peut plus être reportée."}, status=400)

    current = timezone.localtime(planning.date) if planning.date and timezone.is_aware(planning.date) else planning.date
    intervention_time = current.time().replace(tzinfo=None) if current else datetime.min.time().replace(hour=8)
    planning.date = timezone.make_aware(datetime.combine(new_date, intervention_time))
    planning.statut = "reporte"
    planning.estvalide = False
    planning.suiteadonner = "A suivre"
    planning.save(update_fields=["date", "statut", "estvalide", "suiteadonner", "updated_at"])
    return JsonResponse({"success": True, "message": "L’intervention a été reportée."})


@csrf_exempt
@mobile_auth_required
@require_http_methods(["POST"])
@transaction.atomic
def mobile_intervention_delete(request, planning_id):
    """Supprime une intervention uniquement pour un directeur et dans son périmètre."""
    if not is_directeur_poste(request.user):
        return JsonResponse({
            "success": False,
            "error": "Cette suppression est réservée aux directeurs.",
        }, status=403)
    editable_works = _accessible_ouvrages(request.user)
    planning = Planning.objects.filter(
        Q(ouvrage__in=editable_works)
        | Q(details__point_eau__ouvrage__in=editable_works)
        | Q(details__equipement_constitutif__ouvrage__in=editable_works),
        id=planning_id,
    ).distinct().first()
    if not planning:
        return JsonResponse({
            "success": False,
            "error": "Intervention introuvable ou hors de votre périmètre.",
        }, status=404)

    from apps.messaging.models import Conversation

    Conversation.objects.filter(
        type="group",
        description__startswith=f"repair_planning:{planning.id}",
    ).delete()
    planning.delete()
    return JsonResponse({"success": True, "message": "L’intervention a été supprimée."})


DETAIL_MODELS = {
    "ouvrage": ("apps.organization.models", "Ouvrage"),
    "point_eau": ("apps.billing.models", "PointEau"),
    "equipement": ("apps.infrastructure.models", "EquipementConstitutif"),
    "planning": ("apps.planning.models", "Planning"),
    "village": ("apps.geography.models", "Village"),
    "commune": ("apps.geography.models", "Commune"),
    "employe": ("apps.employees.models", "Employe"),
    "representant": ("apps.usagers.models", "RepresentantUsager"),
    "autorite": ("apps.usagers.models", "Autorite"),
    "tiers": ("apps.usagers.models", "TiersParticipant"),
    "fournisseur": ("apps.billing.models", "Fournisseur"),
    "designation": ("apps.planning.models", "Designation"),
    "modalite": ("apps.billing.models", "ModaliteGestion"),
    "carte_sociale": ("apps.infrastructure.models", "CarteSociale"),
}


def _detail_queryset(entity_type, model, user):
    queryset = model.objects.all()
    if entity_type == "ouvrage":
        return filter_queryset_by_permissions(queryset, user)
    if entity_type == "point_eau":
        allowed = filter_queryset_by_permissions(Ouvrage.objects.all(), user)
        return queryset.filter(ouvrage__in=allowed)
    if entity_type == "equipement":
        allowed = filter_queryset_by_permissions(Ouvrage.objects.all(), user)
        return queryset.filter(ouvrage__in=allowed)
    if entity_type == "planning":
        allowed = _accessible_intervention_ouvrages(user)
        return queryset.filter(ouvrage__in=allowed)
    if entity_type in {"village", "commune"}:
        allowed = filter_queryset_by_permissions(Ouvrage.objects.all(), user)
        points = PointEau.objects.filter(ouvrage__in=allowed)
        lookup = (
            "id__in" if entity_type == "village"
            else "id__in"
        )
        ids = points.values_list(
            "parcelle__village_id" if entity_type == "village"
            else "parcelle__village__fokontany__commune_id",
            flat=True,
        )
        return queryset.filter(**{lookup: ids})
    if entity_type in {"modalite", "carte_sociale"}:
        allowed = filter_queryset_by_permissions(Ouvrage.objects.all(), user)
        return queryset.filter(ouvrage__in=allowed)
    if entity_type == "employe":
        connected_employee = getattr(user, "employe", None)
        organisation_id = getattr(getattr(getattr(connected_employee, "base", None), "organisation", None), "id", None)
        return queryset.filter(base__organisation_id=organisation_id) if organisation_id else queryset
    return queryset


LIBELLES_TYPE_ABONNE_MOBILE = {'particulier': 'Particuliers', 'boutique': 'Boutiques'}


def _repartition_points_eau(points_queryset):
    """
    Répartition des points d'eau d'un ouvrage pour la tuile de l'app :
    - `actifs` : seuls points d'eau existants (branchés, non coupés), par type ; pour les kiosques, détail par
      type d'abonné (un kiosque sans type d'abonné est une anomalie à corriger) ;
    - `coupes` : branchés puis coupés (comptés à part) ;
    - `sans_date` : sans date de branchement = pas encore des points d'eau, par type.
    """
    def type_nom(row):
        return row['type_point_eau__nom_type'] or 'Type non renseigné'

    par_type = {}
    for row in points_queryset.filter(q_actif()).order_by().values(
        'type_point_eau__nom_type', 'typeabonne',
    ).annotate(n=Count('id')):
        nom = type_nom(row)
        entree = par_type.setdefault(nom, {'type': nom, 'count': 0, 'abonnes': {}})
        entree['count'] += row['n']
        if 'kiosque' in nom.lower():
            cle = (row['typeabonne'] or '').strip().lower()
            cle = cle if cle in LIBELLES_TYPE_ABONNE_MOBILE else 'manquant'
            entree['abonnes'][cle] = entree['abonnes'].get(cle, 0) + row['n']

    actifs = []
    for entree in sorted(par_type.values(), key=lambda e: (-e['count'], e['type'].lower())):
        abonnes = [
            {'libelle': LIBELLES_TYPE_ABONNE_MOBILE[cle], 'count': entree['abonnes'][cle], 'anomalie': False}
            for cle in ('particulier', 'boutique') if entree['abonnes'].get(cle)
        ]
        if entree['abonnes'].get('manquant'):
            abonnes.append({'libelle': "Type d'abonné manquant", 'count': entree['abonnes']['manquant'], 'anomalie': True})
        actifs.append({'type': entree['type'], 'count': entree['count'], 'abonnes': abonnes})

    sans_date = {}
    for row in points_queryset.filter(q_sans_date()).order_by().values(
        'type_point_eau__nom_type',
    ).annotate(n=Count('id')):
        sans_date[type_nom(row)] = sans_date.get(type_nom(row), 0) + row['n']
    sans_date_liste = [
        {'type': nom, 'count': n} for nom, n in sorted(sans_date.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    ]

    return {
        'actifs_total': sum(e['count'] for e in actifs),
        'actifs': actifs,
        'coupes': points_queryset.filter(q_coupe()).count(),
        'sans_date_total': sum(sans_date.values()),
        'sans_date': sans_date_liste,
    }


def _ouvrage_mobile_details(ouvrage):
    points_queryset = PointEau.objects.filter(ouvrage=ouvrage).select_related(
        "type_point_eau", "parcelle__village",
    ).order_by("code_point_eau", "nomabonne")
    equipments_queryset = EquipementConstitutif.objects.filter(ouvrage=ouvrage).select_related(
        "type_equipement",
    ).order_by("nom")
    points_total = points_queryset.count()
    equipments_total = equipments_queryset.count()
    points = list(points_queryset[:100])
    equipments = list(equipments_queryset[:100])
    history = _historique_interventions(ouvrage)

    point_rows = [{
        "IDXls": point.idxls or "Non renseigné",
        "abonné": point.nomabonne or "Non renseigné",
        "téléphone": point.numeroteleph or point.contactabonne or "Non renseigné",
        "type": f"{point_type_pictogram(point.type_point_eau.nom_type if point.type_point_eau else '')} "
                f"{point.type_point_eau.nom_type if point.type_point_eau else 'Non renseigné'}",
        "coordonnées": "Oui" if has_coordinates(point) else "Non",
        "photo": "Oui" if point.photos else "Non",
    } for point in points]
    equipment_rows = [{
        "nom": equipment.nom or "Équipement sans nom",
        "type": equipment.type_equipement.nom_type if equipment.type_equipement else "",
        "coordonnées": "Oui" if has_coordinates(equipment) else "Non",
        "photo": "Oui" if (equipment.photos or equipment.photo_reference_id) else "Non",
    } for equipment in equipments]
    intervention_rows = [{
        "id": row["id"],
        "date": row["date"],
        "activité": row["activite"],
        "statut": row["statut"],
        "employé": row["employe"],
        "action_requise": row["requires_action"],
        "médias": len(row["photos"]),
    } for row in history[:20]]
    repartition = _repartition_points_eau(points_queryset)
    indicators = {
            "points_eau": repartition["actifs_total"],
            "points_eau_coupés": repartition["coupes"],
            "points_sans_date_de_branchement": repartition["sans_date_total"],
            "équipements": equipments_total,
            "points_sans_coordonnées": points_queryset.filter(Q(latitude__isnull=True) | Q(longitude__isnull=True)).count(),
            "équipements_sans_coordonnées": equipments_queryset.filter(Q(latitude__isnull=True) | Q(longitude__isnull=True)).count(),
            "interventions": len(history),
            "interventions_échues": sum(1 for row in history if row["requires_action"]),
    }
    return {
        "indicateurs": without_zero_values(indicators),
        "repartition_points_eau": repartition,
        "points_eau": point_rows,
        "equipements": equipment_rows,
        "interventions_recentes": intervention_rows,
        "limites": without_zero_values({
            "points_affichés": min(points_total, 100),
            "équipements_affichés": min(equipments_total, 100),
            "interventions_affichées": min(len(history), 20),
        }),
    }


FLUX_COMMUNE_DEFAUT = ['taille', 'desserte', 'fonct', 'gestion', 'factures', 'reparation']


def _commune_mobile_details(commune, user):
    """
    Fiche commune de l'app : habitants (et desservis), ouvrages / points d'eau par type, listes de villages et
    d'ouvrages (cliquables vers leurs fiches) et données du diagramme de flux. Mêmes règles que le dashboard :
    point d'eau « en service » = branché et non coupé ; village desservi = au moins un point d'eau en service.
    """
    from apps.geography.models import Parcelle, Village
    from apps.organization.services_fonctionnalite import get_statuts_fonctionnel_bulk
    from hydria.views_structure import DIMENSIONS_META, DIMENSIONS_FLUX, calculer_structure

    # Comme les KPI par commune du dashboard : les ouvrages suspendus ou « potentiels » ne comptent pas
    allowed = filter_queryset_by_permissions(Ouvrage.objects.all(), user).exclude(
        Q(type_ouvrage__nom_type_ouvrage__icontains='suspend')
        | Q(type_ouvrage__nom_type_ouvrage__icontains='potentiel')
    )
    points = PointEau.objects.filter(
        ouvrage__in=allowed, parcelle__village__fokontany__commune=commune,
    ).select_related('type_point_eau')
    repartition = _repartition_points_eau(points)

    # Habitants : tous ceux de la commune, et ceux dont la parcelle a au moins un point d'eau en service
    parcelles = Parcelle.objects.filter(village__fokontany__commune=commune)
    habitants = int(parcelles.aggregate(n=Sum('nombre_habitants'))['n'] or 0)
    parcelles_desservies = parcelles.filter(id__in=points.filter(q_actif()).values('parcelle_id'))
    habitants_desservis = int(parcelles_desservies.aggregate(n=Sum('nombre_habitants'))['n'] or 0)

    # Villages : habitants, points d'eau en service, et fiche disponible (au moins un point d'eau dans le périmètre)
    habitants_par_village = {
        row['village_id']: int(row['n'] or 0)
        for row in parcelles.order_by().values('village_id').annotate(n=Sum('nombre_habitants'))
    }
    points_par_village = {
        row['parcelle__village_id']: row
        for row in points.order_by().values('parcelle__village_id').annotate(
            total=Count('id'), actifs=Count('id', filter=q_actif()),
        )
    }
    villages = []
    for village in Village.objects.filter(fokontany__commune=commune).order_by('nom_village'):
        comptes = points_par_village.get(village.id) or {}
        actifs = comptes.get('actifs') or 0
        villages.append({
            'id': str(village.id), 'nom': village.nom_village or 'Village sans nom',
            'habitants': habitants_par_village.get(village.id, 0),
            'points_eau': actifs, 'desservi': actifs > 0,
            'cliquable': (comptes.get('total') or 0) > 0,     # la fiche village n'existe que s'il y a un point d'eau
        })
    nb_villages_desservis = sum(1 for v in villages if v['desservi'])

    # Ouvrages : type, points d'eau en service, fonctionnement
    ouvrages_commune = list(
        allowed.filter(id__in=points.values('ouvrage_id')).select_related('type_ouvrage').order_by('nom_ouvrage')
    )
    statuts = get_statuts_fonctionnel_bulk([o.id for o in ouvrages_commune])
    actifs_par_ouvrage = {
        row['ouvrage_id']: row['n']
        for row in points.filter(q_actif()).order_by().values('ouvrage_id').annotate(n=Count('id'))
    }
    ouvrages = []
    par_type = {}
    for o in ouvrages_commune:
        type_nom = o.type_ouvrage.nom_type_ouvrage if o.type_ouvrage else 'Type non renseigné'
        fonctionnel = bool(statuts.get(o.id, {}).get('fonctionnel', True))
        ouvrages.append({
            'id': str(o.id), 'nom': o.nom_ouvrage or 'Ouvrage sans nom', 'type': type_nom,
            'points_eau': actifs_par_ouvrage.get(o.id, 0), 'fonctionnel': fonctionnel,
        })
        entree = par_type.setdefault(type_nom, {'type': type_nom, 'count': 0, 'fonctionnels': 0})
        entree['count'] += 1
        entree['fonctionnels'] += 1 if fonctionnel else 0
    ouvrages_par_type = sorted(par_type.values(), key=lambda e: (-e['count'], e['type'].lower()))

    # Diagramme de flux : même calcul que le dashboard, restreint à la commune. Ne doit jamais bloquer la fiche.
    try:
        structure = calculer_structure(user, {'commune_id': str(commune.id)})
        flux = {
            'total': structure['villages']['total'],
            'dimensions': {k: DIMENSIONS_META[k] for k in DIMENSIONS_FLUX},
            'defaut': FLUX_COMMUNE_DEFAUT,
            'rows': structure['flux'],
        }
    except Exception:
        flux = None

    return {
        'synthese': {
            'habitants': habitants,
            'habitants_desservis': habitants_desservis,
            'taux_desserte_pct': round(habitants_desservis / habitants * 100) if habitants else 0,
            'villages': len(villages),
            'villages_desservis': nb_villages_desservis,
            'ouvrages': len(ouvrages),
            'ouvrages_fonctionnels': sum(1 for o in ouvrages if o['fonctionnel']),
            'points_eau_en_service': repartition['actifs_total'],
        },
        'ouvrages_par_type': ouvrages_par_type,
        'repartition_points_eau': repartition,
        'villages': villages,
        'ouvrages': ouvrages,
        'flux': flux,
    }


PROFIL_VILLAGE_DIMENSIONS = [
    'taille', 'acces', 'desserte', 'fonct', 'continuite', 'gestion', 'paiement', 'factures', 'reparation', 'age',
]
LIBELLES_ACCESSIBILITE = {
    'pied': 'À pied', 'moto': 'Moto', 'voiture': 'Voiture', 'pirogue': 'Pirogue', 'goudron': 'Route goudronnée',
}


def _village_mobile_details(village, user):
    """
    Fiche village de l'app : population (et population desservie), accessibilité, ouvrages qui le desservent
    (cliquables), points d'eau par type, parcelles et profil du village (mêmes classements que le dashboard :
    taille, desserte, fonctionnement, gestion, recouvrement, réparations...).
    Règles du dashboard : point d'eau « en service » = branché et non coupé ; ouvrages suspendus / « potentiels »
    ignorés ; village desservi = au moins un point d'eau en service.
    """
    from apps.geography.models import Parcelle
    from apps.organization.services_fonctionnalite import get_statuts_fonctionnel_bulk
    from hydria.views_structure import DIMENSIONS_META, calculer_structure

    allowed = filter_queryset_by_permissions(Ouvrage.objects.all(), user).exclude(
        Q(type_ouvrage__nom_type_ouvrage__icontains='suspend')
        | Q(type_ouvrage__nom_type_ouvrage__icontains='potentiel')
    )
    points = PointEau.objects.filter(ouvrage__in=allowed, parcelle__village=village).select_related('type_point_eau')
    repartition = _repartition_points_eau(points)

    parcelles = list(Parcelle.objects.filter(village=village).order_by('reference_parcelle'))
    parcelles_desservies_ids = set(points.filter(q_actif()).values_list('parcelle_id', flat=True))
    points_par_parcelle = {
        row['parcelle_id']: row['n']
        for row in points.filter(q_actif()).order_by().values('parcelle_id').annotate(n=Count('id'))
    }
    habitants = sum(int(p.nombre_habitants or 0) for p in parcelles)
    habitants_desservis = sum(int(p.nombre_habitants or 0) for p in parcelles if p.id in parcelles_desservies_ids)
    menages = sum(int(p.nombre_menages or 0) for p in parcelles)
    menages_desservis = sum(int(p.nombre_menages or 0) for p in parcelles if p.id in parcelles_desservies_ids)

    # Ouvrages qui desservent le village
    ouvrages_village = list(
        allowed.filter(id__in=points.values('ouvrage_id')).select_related('type_ouvrage').order_by('nom_ouvrage')
    )
    statuts = get_statuts_fonctionnel_bulk([o.id for o in ouvrages_village])
    actifs_par_ouvrage = {
        row['ouvrage_id']: row['n']
        for row in points.filter(q_actif()).order_by().values('ouvrage_id').annotate(n=Count('id'))
    }
    ouvrages = [{
        'id': str(o.id), 'nom': o.nom_ouvrage or 'Ouvrage sans nom',
        'type': o.type_ouvrage.nom_type_ouvrage if o.type_ouvrage else 'Type non renseigné',
        'points_eau': actifs_par_ouvrage.get(o.id, 0),
        'fonctionnel': bool(statuts.get(o.id, {}).get('fonctionnel', True)),
    } for o in ouvrages_village]

    fokontany = village.fokontany
    commune = fokontany.commune if fokontany else None
    localisation = {
        'fokontany': fokontany.nom_fokontany if fokontany else '',
        'commune': {'id': str(commune.id), 'nom': commune.nom_commune} if commune else None,
        'district': commune.district.nom_district if commune and commune.district else '',
        'region': commune.district.region.nom_region if commune and commune.district and commune.district.region else '',
    }

    # Profil : le classement du village sur chaque dimension du diagramme de flux. Ne doit jamais bloquer la fiche.
    profil = None
    try:
        rows = calculer_structure(user, {'village_id': str(village.id)})['flux']
        if rows:
            row = rows[0]
            profil = []
            for key in PROFIL_VILLAGE_DIMENSIONS:
                meta = DIMENSIONS_META[key]
                cat = next((c for c in meta['cats'] if c['k'] == row.get(key)), None)
                if cat:
                    profil.append({'dimension': key, 'titre': meta['titre'], 'label': cat['court'], 'color': cat['color']})
    except Exception:
        profil = None

    actifs = repartition['actifs_total']
    return {
        'synthese': {
            'habitants': habitants,
            'habitants_desservis': habitants_desservis,
            'taux_desserte_pct': round(habitants_desservis / habitants * 100) if habitants else 0,
            'menages': menages,
            'menages_desservis': menages_desservis,
            'parcelles': len(parcelles),
            'parcelles_desservies': sum(1 for p in parcelles if p.id in parcelles_desservies_ids),
            'desservi': actifs > 0,
            'ouvrages': len(ouvrages),
            'ouvrages_fonctionnels': sum(1 for o in ouvrages if o['fonctionnel']),
            'points_eau_en_service': actifs,
            'accessibilite': LIBELLES_ACCESSIBILITE.get(village.accessibilite or '', ''),
            'distance_dernier_point_km': float(village.distance_dernier_point) if village.distance_dernier_point is not None else None,
        },
        'localisation': localisation,
        'profil': profil,
        'repartition_points_eau': repartition,
        'ouvrages': ouvrages,
        'parcelles': [{
            'reference': p.reference_parcelle or 'Parcelle sans référence',
            'habitants': int(p.nombre_habitants or 0), 'menages': int(p.nombre_menages or 0),
            'points_eau': points_par_parcelle.get(p.id, 0), 'desservie': p.id in parcelles_desservies_ids,
        } for p in parcelles],
    }


def _photo_preview(value):
    """Première photo exploitable : data-URI, URL /media/ ou http(s), sinon ''."""
    photos = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
    for photo in photos:
        if not isinstance(photo, dict):
            continue
        data = str(photo.get('data') or photo.get('url') or '').strip()
        if not data:
            continue
        if data.startswith(('data:', 'http://', 'https://', '/media/')):
            return data
        return f"data:{photo.get('content_type') or 'image/jpeg'};base64,{data}"
    return ''


def _mobile_terrain_block(entity_type, instance):
    """Informations terrain modifiables depuis la fiche Recherche de l'app
    (abonné, téléphone, GPS, photo) + version pour détecter les conflits."""
    latitude = getattr(instance, 'latitude', None)
    longitude = getattr(instance, 'longitude', None)
    block = {
        'kind': entity_type,
        'has_coordinates': has_coordinates(instance),
        'latitude': float(latitude) if latitude is not None else None,
        'longitude': float(longitude) if longitude is not None else None,
    }
    if entity_type == 'point_eau':
        preview = _photo_preview(instance.photos)
        block.update({
            'subscriber_name': instance.nomabonne or '',
            'telephone': instance.numeroteleph or instance.contactabonne or '',
            'idxls': instance.idxls or '',
            'code': instance.code_point_eau or '',
            'has_photo': bool(preview) or bool(instance.photos),
            'photo': preview,
            'updated_at': instance.updatedat.isoformat() if instance.updatedat else '',
        })
    else:
        # La photo de référence (FileUpload Supabase) compte comme photo présente, sans aperçu.
        preview = _photo_preview(instance.photos)
        block.update({
            'name': instance.nom or '',
            'has_photo': bool(preview) or bool(instance.photos) or bool(instance.photo_reference_id),
            'photo': preview,
            'updated_at': instance.updated_at.isoformat() if instance.updated_at else '',
        })
    return block


@mobile_auth_required
@require_http_methods(["GET"])
def mobile_detail(request, entity_type, entity_id):
    config = DETAIL_MODELS.get(entity_type)
    if not config:
        return JsonResponse({"success": False, "error": "Type inconnu."}, status=404)
    module_name, class_name = config
    module = __import__(module_name, fromlist=[class_name])
    model = getattr(module, class_name)
    try:
        instance = _detail_queryset(entity_type, model, request.user).get(pk=entity_id)
    except (model.DoesNotExist, ValueError):
        return JsonResponse({"success": False, "error": "Élément introuvable."}, status=404)

    hidden = {"password", "signature", "photo", "photos"}
    fields = []
    for field in instance._meta.fields:
        if field.name in hidden:
            continue
        value = getattr(instance, field.name, None)
        if field.is_relation:
            value = str(value) if value else ""
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        elif value is not None:
            value = str(value)
        fields.append({
            "key": field.name,
            "label": str(field.verbose_name).replace("_", " ").capitalize(),
            "value": value or "",
        })
    title = str(instance)
    last_update = getattr(instance, "updated_at", None) or getattr(instance, "created_at", None)
    payload = {
        "success": True, "id": str(instance.pk), "type": entity_type,
        "type_display": model._meta.verbose_name.capitalize(), "title": title,
        "fields": fields,
        "actions": {"view": True, "edit": False, "capture_gps": entity_type in {"point_eau", "equipement"}},
        "web_url": f"/recherche/details/{entity_type}/{instance.pk}/",
        "updated_at": last_update.isoformat() if last_update else None,
    }
    if entity_type == "ouvrage":
        payload["details"] = _ouvrage_mobile_details(instance)
    if entity_type == "commune":
        payload["details"] = _commune_mobile_details(instance, request.user)
    if entity_type == "village":
        payload["details"] = _village_mobile_details(instance, request.user)
    if entity_type in {"point_eau", "equipement"}:
        payload["terrain"] = _mobile_terrain_block(entity_type, instance)
    return JsonResponse(payload)
