"""
Vues pour la gestion des coupures/remises des paiements volumétriques
"""
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import json
import pytz
import unicodedata

from .models import PointEau, CoupureEau, ModaliteGestion
from apps.organization.models import Ouvrage, Organisation
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_user_accessible_gestionnaire_ids,
    get_default_gestionnaire_filter_value,
    get_user_organisation,
)
from apps.employees.permissions import filter_queryset_by_permissions
from apps.employees.models import EmployeOuvrages
from apps.accounting.dashboard_employee_filter import (
    build_employee_geo_filter_options,
    resolve_dashboard_employee_filter,
)

COUPURES_MODALITES_PAIEMENT = ('forfaitaire', 'au_volume', 'mixte')
FORFAIT_MODALITES_PAIEMENT = ('forfaitaire', 'mixte')


def _is_directeur_user(user):
    if not user or not user.is_authenticated:
        return False
    employe = getattr(user, 'employe', None)
    if employe and hasattr(employe, 'is_directeur') and employe.is_directeur:
        return True
    return user.groups.filter(name='Directeur').exists()


def _get_user_organisation_id(user):
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation_id', None)


def _get_allowed_ouvrage_ids(user):
    """
    Ouvrages autorisés pour coupures/remises:
    modalité active (date_fin IS NULL) et modalitepaiement compatible
    avec le workflow eau (forfaitaire, au volume, mixte).
    """
    modalites = _get_allowed_modalites_queryset(user)

    if not (getattr(user, 'is_superuser', False) or _is_directeur_user(user)):
        gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
        if gestionnaire_ids is None:
            pass
        elif not gestionnaire_ids:
            return modalites.none().values_list('ouvrage_id', flat=True)
        else:
            modalites = modalites.filter(gestionnaire_id__in=gestionnaire_ids)

    ouvrage_ids = set(
        modalites.exclude(ouvrage_id__isnull=True).values_list('ouvrage_id', flat=True).distinct()
    )
    return apply_user_responsable_ouvrage_scope(ouvrage_ids, user)


def _get_allowed_modalites_queryset(user):
    return ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=COUPURES_MODALITES_PAIEMENT
    )


def _get_allowed_modalite_paiement_map(user, ouvrage_ids=None):
    modalites = _get_allowed_modalites_queryset(user)
    if ouvrage_ids is not None:
        modalites = modalites.filter(ouvrage_id__in=ouvrage_ids)
    modalites = modalites.exclude(ouvrage_id__isnull=True).order_by('ouvrage_id', 'date_debut')

    modalite_labels = dict(ModaliteGestion.MODALITE_PAIEMENT_CHOICES)
    modalite_map = {}
    for modalite in modalites:
        modalite_map.setdefault(str(modalite.ouvrage_id), {
            'value': modalite.modalitepaiement or '',
            'label': modalite_labels.get(modalite.modalitepaiement, modalite.modalitepaiement or '')
        })
    return modalite_map


def _resolve_requested_ouvrage_ids(request, allowed_ouvrage_ids=None):
    if allowed_ouvrage_ids is None:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

    allowed_ids = [str(ouvrage_id) for ouvrage_id in allowed_ouvrage_ids]
    ouvrages_qs = Ouvrage.objects.filter(id__in=allowed_ids)

    region_id = (request.GET.get('region_id') or '').strip()
    district_id = (request.GET.get('district_id') or '').strip()
    commune_id = (request.GET.get('commune_id') or '').strip()
    modalite_paiement = (request.GET.get('modalite_paiement') or '').strip()
    ouvrage_search = (request.GET.get('ouvrage_search') or '').strip()

    if region_id:
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune__district__region_id=region_id
        )
    if district_id:
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune__district_id=district_id
        )
    if commune_id:
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune_id=commune_id
        )
    if ouvrage_search:
        ouvrages_qs = ouvrages_qs.filter(nom_ouvrage__icontains=ouvrage_search)
    if modalite_paiement:
        ouvrages_qs = ouvrages_qs.filter(
            modalites_gestion__modalitepaiement=modalite_paiement,
            modalites_gestion__date_fin__isnull=True,
        )

    allowed_ids = [str(ouvrage_id) for ouvrage_id in ouvrages_qs.values_list('id', flat=True).distinct()]
    allowed_set = set(allowed_ids)

    ouvrage_id = (request.GET.get('ouvrage_id') or '').strip()
    ouvrage_ids_raw = (request.GET.get('ouvrage_ids') or '').strip()

    requested_ids = []
    if ouvrage_id:
        requested_ids = [ouvrage_id]
    elif ouvrage_ids_raw:
        requested_ids = [value.strip() for value in ouvrage_ids_raw.split(',') if value.strip()]

    if requested_ids:
        return [value for value in requested_ids if value in allowed_set], requested_ids

    return allowed_ids, []


def _extract_date_only(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _get_stale_coupure_cutoff_date():
    return timezone.localdate() - timedelta(days=365)


def _is_point_eau_cut_since_more_than_one_year(point_eau, cutoff_date=None):
    date_arret = _extract_date_only(getattr(point_eau, 'datearretbranchement', None))
    if not date_arret:
        return False
    if cutoff_date is None:
        cutoff_date = _get_stale_coupure_cutoff_date()
    return date_arret <= cutoff_date


def _clear_stale_forfaitaire_points(ouvrage_ids=None, point_eau_ids=None):
    eligible_ouvrage_ids = set(
        ModaliteGestion.objects.filter(
            date_fin__isnull=True,
            modalitepaiement__in=FORFAIT_MODALITES_PAIEMENT
        ).exclude(
            ouvrage_id__isnull=True
        ).values_list('ouvrage_id', flat=True)
    )
    if not eligible_ouvrage_ids:
        return 0

    qs = PointEau.objects.filter(
        datearretbranchement__isnull=False,
        datearretbranchement__date__lte=_get_stale_coupure_cutoff_date(),
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=eligible_ouvrage_ids
    )
    if ouvrage_ids is not None:
        qs = qs.filter(ouvrage_id__in=ouvrage_ids)
    if point_eau_ids is not None:
        qs = qs.filter(id__in=point_eau_ids)
    return qs.update(tarifforfaitaire=None, pourcentage_tarif=None)


def _get_point_eau_village_nom(point_eau):
    if point_eau and point_eau.parcelle and point_eau.parcelle.village:
        return point_eau.parcelle.village.nom_village
    return 'N/A'


def _format_tarif_forfaitaire_display(value):
    if value in (None, ''):
        return 'Non defini'
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    if amount.is_integer():
        return f"{int(amount):,} Ar".replace(',', ' ')
    return f"{amount:,.2f} Ar".replace(',', ' ')


def _serialize_point_eau_tarif_context(point_eau, cutoff_date=None):
    date_arret = _extract_date_only(getattr(point_eau, 'datearretbranchement', None))
    est_coupe_plus_un_an = _is_point_eau_cut_since_more_than_one_year(point_eau, cutoff_date=cutoff_date)
    return {
        'point_eau_id': str(point_eau.id) if point_eau else '',
        'code': point_eau.code_point_eau if point_eau else '',
        'abonne': point_eau.nomabonne if point_eau else '',
        'ouvrage': point_eau.ouvrage.nom_ouvrage if (point_eau and point_eau.ouvrage) else 'N/A',
        'village': _get_point_eau_village_nom(point_eau),
        'tarifforfaitaire': point_eau.tarifforfaitaire if point_eau else None,
        'tarifforfaitaire_display': _format_tarif_forfaitaire_display(getattr(point_eau, 'tarifforfaitaire', None)),
        'date_arret': date_arret.strftime('%Y-%m-%d') if date_arret else None,
        'date_arret_display': date_arret.strftime('%d/%m/%Y') if date_arret else '',
        'est_coupe_plus_un_an': est_coupe_plus_un_an,
    }


@login_required
def gestion_coupures_eau(request):
    """Page de gestion des coupures et remises en eau."""
    base_ouvrages_qs = Ouvrage.objects.filter(
        pointeau__isnull=False
    ).distinct().order_by('nom_ouvrage')

    ouvrages = filter_queryset_by_permissions(base_ouvrages_qs, request.user)

    # Fallback pragmatique: en local certains comptes n'ont pas d'employe/base
    # et le filtrage retourne vide; on evite de bloquer totalement la page.
    if not ouvrages.exists():
        ouvrages = base_ouvrages_qs
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
    _clear_stale_forfaitaire_points(ouvrage_ids=allowed_ouvrage_ids)
    ouvrages = ouvrages.filter(id__in=allowed_ouvrage_ids)
    ouvrage_ids = list(ouvrages.values_list('id', flat=True))
    modalite_map = _get_allowed_modalite_paiement_map(request.user, ouvrage_ids=ouvrage_ids)

    points_geo = PointEau.objects.filter(
        ouvrage_id__in=ouvrage_ids
    ).select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district__region'
    )

    geo_by_ouvrage = {}
    for pe in points_geo:
        if not pe.ouvrage_id or pe.ouvrage_id in geo_by_ouvrage:
            continue

        region_id = ''
        region_nom = ''
        district_id = ''
        district_nom = ''
        commune_id = ''
        commune_nom = ''

        commune = None
        if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
            commune = pe.parcelle.village.fokontany.commune

        if commune:
            commune_id = str(commune.id)
            commune_nom = commune.nom_commune or ''
            if commune.district:
                district_id = str(commune.district.id)
                district_nom = commune.district.nom_district or ''
                if commune.district.region:
                    region_id = str(commune.district.region.id)
                    region_nom = commune.district.region.nom_region or ''

        geo_by_ouvrage[pe.ouvrage_id] = {
            'region_id': region_id,
            'region_nom': region_nom,
            'district_id': district_id,
            'district_nom': district_nom,
            'commune_id': commune_id,
            'commune_nom': commune_nom,
        }

    ouvrages_geo_data = []
    for ouvrage in ouvrages:
        geo = geo_by_ouvrage.get(ouvrage.id, {})
        modalite_info = modalite_map.get(str(ouvrage.id), {'value': '', 'label': ''})
        ouvrages_geo_data.append({
            'id': str(ouvrage.id),
            'nom': ouvrage.nom_ouvrage,
            'region_id': geo.get('region_id', ''),
            'region_nom': geo.get('region_nom', ''),
            'district_id': geo.get('district_id', ''),
            'district_nom': geo.get('district_nom', ''),
            'commune_id': geo.get('commune_id', ''),
            'commune_nom': geo.get('commune_nom', ''),
            'modalite_paiement': modalite_info.get('value', ''),
            'modalite_paiement_label': modalite_info.get('label', ''),
        })

    return render(request, 'billing/coupures_eau_management.html', {
        'ouvrages': ouvrages,
        'ouvrages_geo_data': ouvrages_geo_data,
        'modalites_paiement_options': [
            {'value': value, 'label': label}
            for value, label in ModaliteGestion.MODALITE_PAIEMENT_CHOICES
            if value in COUPURES_MODALITES_PAIEMENT
        ]
    })


def _history_organisation_scope(user, requested_organisation_id):
    """Resolve the organisation filter without allowing a forged scope."""
    accessible_ids = get_user_accessible_gestionnaire_ids(user)
    current_organisation = get_user_organisation(user)

    if accessible_ids is None:
        organisations = Organisation.objects.filter(
            type_organisation=Organisation.TYPE_GESTIONNAIRE
        ).order_by('nom_organisation')
        allowed_ids = None
        default_id = (
            str(current_organisation.id)
            if current_organisation and current_organisation.type_organisation == Organisation.TYPE_GESTIONNAIRE
            else ''
        )
    else:
        normalized_ids = [str(item) for item in accessible_ids if item]
        organisations = Organisation.objects.filter(
            id__in=normalized_ids,
            type_organisation=Organisation.TYPE_GESTIONNAIRE,
        ).order_by('nom_organisation')
        allowed_ids = set(normalized_ids)
        default_id = get_default_gestionnaire_filter_value(user, normalized_ids)

    selected_id = str(requested_organisation_id or '').strip()
    if not selected_id:
        selected_id = default_id
    if selected_id == 'all' and allowed_ids is not None:
        selected_id = default_id
    if selected_id and selected_id != 'all':
        if allowed_ids is not None and selected_id not in allowed_ids:
            selected_id = default_id
        elif not organisations.filter(id=selected_id).exists():
            selected_id = default_id

    return organisations, selected_id, accessible_ids


def _history_point_geo(point_eau):
    commune = None
    if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany:
        commune = point_eau.parcelle.village.fokontany.commune
    district = commune.district if commune else None
    region = district.region if district else None
    return {
        'village': _get_point_eau_village_nom(point_eau),
        'commune': commune.nom_commune if commune else 'N/A',
        'district': district.nom_district if district else 'N/A',
        'region': region.nom_region if region else 'N/A',
    }


def _is_bp_point_type(type_name):
    normalized = ''.join(
        character
        for character in unicodedata.normalize('NFKD', str(type_name or '').strip().lower())
        if not unicodedata.combining(character)
    )
    return (
        normalized == 'bp'
        or normalized.startswith('bp ')
        or 'branchement prive' in normalized
    )


def _detect_point_incoherences(events_chrono):
    """
    Marque en place (cle 'is_anomaly') les evenements incoherents : un evenement
    du meme type que le precedent (coupure -> coupure, ou remise -> remise) sans
    evenement du type oppose entre les deux, signe d'une coupure ou d'une remise
    non enregistree. `events_chrono` doit deja etre trie par ordre chronologique
    croissant. Retourne le nombre d'anomalies detectees.
    """
    nb_incoherences = 0
    previous_type = None
    for event in events_chrono:
        is_anomaly = bool(previous_type and event['type_evenement'] == previous_type)
        event['is_anomaly'] = is_anomaly
        if is_anomaly:
            nb_incoherences += 1
        previous_type = event['type_evenement']
    return nb_incoherences


def _build_historique_coupures_dataset(request):
    """
    Construit le jeu de donnees complet (filtre, puis regroupe par point d'eau)
    utilise a la fois par la page historique et par l'export Excel. Chaque
    "groupe" correspond a un point d'eau avec son historique complet
    d'evenements (coupure/remise), tries chronologiquement, avec detection des
    incoherences (deux evenements du meme type a la suite).
    """
    filter_organisation_requested = request.GET.get('organisation', '')
    filter_employe = str(request.GET.get('employe', '') or '').strip()
    filter_region = str(request.GET.get('region', '') or '').strip()
    filter_district = str(request.GET.get('district', '') or '').strip()
    filter_commune = str(request.GET.get('commune', '') or '').strip()
    filter_ouvrage = str(request.GET.get('ouvrage', '') or '').strip()
    filter_categorie_point_eau = str(
        request.GET.get('categorie_point_eau', '') or ''
    ).strip().lower()
    if filter_categorie_point_eau not in {'bp', 'autres'}:
        filter_categorie_point_eau = ''
    filter_search = str(request.GET.get('search', '') or '').strip()
    filter_vue = str(request.GET.get('vue', 'tous') or 'tous').strip()
    filter_incoherences = str(request.GET.get('incoherences', '') or '').strip().lower() in {'1', 'true', 'on', 'yes'}
    filter_date_debut = str(request.GET.get('date_debut', '') or '').strip()
    filter_date_fin = str(request.GET.get('date_fin', '') or '').strip()
    try:
        date_debut_value = datetime.strptime(filter_date_debut, '%Y-%m-%d').date() if filter_date_debut else None
    except ValueError:
        filter_date_debut = ''
        date_debut_value = None
    try:
        date_fin_value = datetime.strptime(filter_date_fin, '%Y-%m-%d').date() if filter_date_fin else None
    except ValueError:
        filter_date_fin = ''
        date_fin_value = None
    if filter_vue not in {'tous', 'coupes_historique', 'encore_coupes', 'remis'}:
        filter_vue = 'tous'

    organisations, filter_organisation, accessible_ids = _history_organisation_scope(
        request.user,
        filter_organisation_requested,
    )

    modalites = _get_allowed_modalites_queryset(request.user).exclude(ouvrage_id__isnull=True)
    if accessible_ids is not None:
        modalites = modalites.filter(gestionnaire_id__in=accessible_ids)
    if filter_organisation and filter_organisation != 'all':
        modalites = modalites.filter(gestionnaire_id=filter_organisation)

    scope_ouvrage_ids = set(modalites.values_list('ouvrage_id', flat=True).distinct())
    scope_ouvrage_ids = apply_user_responsable_ouvrage_scope(scope_ouvrage_ids, request.user)
    employee_options, employee_ouvrage_ids = resolve_dashboard_employee_filter(
        scope_ouvrage_ids,
        filter_employe,
    )
    if filter_employe and not any(str(item['id']) == filter_employe for item in employee_options):
        filter_employe = ''
    else:
        scope_ouvrage_ids = set(employee_ouvrage_ids)

    regions, districts, communes, ouvrages = build_employee_geo_filter_options(
        scope_ouvrage_ids,
        employee_options=employee_options,
        require_forfait_tariff=False,
    )

    points = PointEau.objects.filter(ouvrage_id__in=scope_ouvrage_ids)
    if filter_region:
        points = points.filter(parcelle__village__fokontany__commune__district__region_id=filter_region)
    if filter_district:
        points = points.filter(parcelle__village__fokontany__commune__district_id=filter_district)
    if filter_commune:
        points = points.filter(parcelle__village__fokontany__commune_id=filter_commune)
    if filter_ouvrage:
        points = points.filter(ouvrage_id=filter_ouvrage)
    if filter_search:
        points = points.filter(
            Q(code_point_eau__icontains=filter_search)
            | Q(nomabonne__icontains=filter_search)
            | Q(ouvrage__nom_ouvrage__icontains=filter_search)
        )
    if filter_categorie_point_eau:
        candidate_type_rows = points.values_list('id', 'type_point_eau__nom_type')
        matching_point_ids = {
            point_id
            for point_id, type_name in candidate_type_rows
            if (
                _is_bp_point_type(type_name)
                if filter_categorie_point_eau == 'bp'
                else not _is_bp_point_type(type_name)
            )
        }
        points = points.filter(id__in=matching_point_ids)

    scoped_point_ids = set(points.values_list('id', flat=True))
    total_scoped_points = len(scoped_point_ids)
    cut_event_point_ids = set(CoupureEau.objects.filter(
        point_eau_id__in=scoped_point_ids,
        type_evenement='coupure',
    ).values_list('point_eau_id', flat=True).distinct())
    current_cut_ids = set(points.filter(
        datearretbranchement__isnull=False
    ).values_list('id', flat=True))
    ever_cut_ids = cut_event_point_ids | current_cut_ids
    restored_ids = ever_cut_ids - current_cut_ids

    def percentage_of_scoped_points(count):
        if not total_scoped_points:
            return 0
        return round((count / total_scoped_points) * 100, 1)

    all_scope_events = CoupureEau.objects.filter(point_eau_id__in=scoped_point_ids)
    legacy_current_count = points.filter(
        id__in=current_cut_ids,
    ).exclude(
        id__in=all_scope_events.values('point_eau_id')
    ).count()
    total_history_events = all_scope_events.count() + legacy_current_count

    bp_point_ids = {
        point_id
        for point_id, type_name in points.values_list('id', 'type_point_eau__nom_type')
        if _is_bp_point_type(type_name)
    }
    other_point_ids = scoped_point_ids - bp_point_ids

    def point_type_stats(group_point_ids):
        group_point_ids = set(group_point_ids)
        group_total = len(group_point_ids)
        group_current_cut_ids = current_cut_ids & group_point_ids
        group_ever_cut_ids = ever_cut_ids & group_point_ids
        group_restored_ids = restored_ids & group_point_ids
        group_events = all_scope_events.filter(point_eau_id__in=group_point_ids)
        group_legacy_count = points.filter(
            id__in=group_current_cut_ids,
        ).exclude(
            id__in=group_events.values('point_eau_id')
        ).count()

        def group_percentage(count):
            return round((count / group_total) * 100, 1) if group_total else 0

        return {
            'total_points': group_total,
            'total_evenements': group_events.count() + group_legacy_count,
            'points_coupes_historique': len(group_ever_cut_ids),
            'points_coupes_historique_pct': group_percentage(len(group_ever_cut_ids)),
            'encore_coupes': len(group_current_cut_ids),
            'encore_coupes_pct': group_percentage(len(group_current_cut_ids)),
            'remis': len(group_restored_ids),
            'remis_pct': group_percentage(len(group_restored_ids)),
        }

    stats_bp = point_type_stats(bp_point_ids)
    stats_autres = point_type_stats(other_point_ids)

    # Determiner l'ensemble des points a inclure selon la vue choisie. La plage
    # de dates ne filtre que la SELECTION des points : l'historique affiche pour
    # un point retenu reste complet, pour ne pas fausser la detection d'incoherences
    # (une remise hors de la plage resterait invisible et creerait un faux positif).
    if filter_vue == 'coupes_historique':
        vue_point_ids = set(ever_cut_ids)
    elif filter_vue == 'encore_coupes':
        vue_point_ids = set(current_cut_ids)
    elif filter_vue == 'remis':
        vue_point_ids = set(restored_ids)
    else:
        vue_point_ids = set(ever_cut_ids)

    if date_debut_value or date_fin_value:
        date_filtered_events = all_scope_events
        if date_debut_value:
            date_filtered_events = date_filtered_events.filter(date_evenement__gte=date_debut_value)
        if date_fin_value:
            date_filtered_events = date_filtered_events.filter(date_evenement__lte=date_fin_value)
        points_in_range = set(date_filtered_events.values_list('point_eau_id', flat=True).distinct())
        legacy_in_range_qs = points.filter(id__in=current_cut_ids).exclude(
            id__in=CoupureEau.objects.filter(point_eau_id__in=current_cut_ids).values('point_eau_id')
        )
        if date_debut_value:
            legacy_in_range_qs = legacy_in_range_qs.filter(datearretbranchement__date__gte=date_debut_value)
        if date_fin_value:
            legacy_in_range_qs = legacy_in_range_qs.filter(datearretbranchement__date__lte=date_fin_value)
        points_in_range |= set(legacy_in_range_qs.values_list('id', flat=True))
        vue_point_ids &= points_in_range

    today = timezone.localdate()
    active_responsibilities = EmployeOuvrages.objects.filter(
        ouvrage_id__in=scope_ouvrage_ids,
        date_debut__lte=today,
        employe__date_debauchage__isnull=True,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=today)
    ).select_related('employe')
    responsables_by_ouvrage = {}
    for relation in active_responsibilities:
        responsables_by_ouvrage.setdefault(relation.ouvrage_id, []).append(
            relation.employe.nom_affichage
        )

    # Historique complet (non borne par la plage de dates) des points retenus.
    events_by_point = {}
    events_qs = all_scope_events.filter(point_eau_id__in=vue_point_ids).select_related(
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune__district__region',
        'cree_par',
    ).order_by('point_eau_id', 'date_evenement', 'created_at')
    for event in events_qs:
        events_by_point.setdefault(event.point_eau_id, []).append({
            'id': event.id,
            'date_evenement': event.date_evenement,
            'type_evenement': event.type_evenement,
            'type_label': event.get_type_evenement_display(),
            'raison': event.get_raison_display() if event.raison else 'Non precisee',
            'raison_code': event.raison or '',
            'notes': event.notes or '',
            'cree_par': event.cree_par.get_full_name() or event.cree_par.username if event.cree_par else 'N/A',
            'legacy': False,
            '_point': event.point_eau,
        })

    # Points actuellement coupes sans aucun evenement detaille (historique ancien).
    legacy_points_qs = points.filter(
        id__in=(current_cut_ids & vue_point_ids),
    ).exclude(
        id__in=CoupureEau.objects.filter(point_eau_id__in=current_cut_ids).values('point_eau_id')
    ).select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district__region',
    )
    for point in legacy_points_qs:
        events_by_point.setdefault(point.id, []).append({
            'id': f'legacy-{point.id}',
            'date_evenement': _extract_date_only(point.datearretbranchement),
            'type_evenement': 'coupure',
            'type_label': "Coupure d'eau",
            'raison': 'Historique ancien',
            'raison_code': '',
            'notes': "Coupure en cours sans evenement detaille.",
            'cree_par': 'N/A',
            'legacy': True,
            '_point': point,
        })

    points_groups = []
    nb_points_incoherents = 0
    nb_incoherences_total = 0
    for point_id, events in events_by_point.items():
        events.sort(key=lambda e: (e['date_evenement'] or timezone.localdate()))
        nb_incoherences_point = _detect_point_incoherences(events)
        point = events[0]['_point']
        for event in events:
            event.pop('_point', None)
        geo = _history_point_geo(point)
        is_incoherent = nb_incoherences_point > 0
        if is_incoherent:
            nb_points_incoherents += 1
            nb_incoherences_total += nb_incoherences_point
        points_groups.append({
            'point': point,
            'ouvrage': point.ouvrage,
            'geo': geo,
            'responsables': responsables_by_ouvrage.get(point.ouvrage_id, []),
            'current_cut': point.id in current_cut_ids,
            'events': list(reversed(events)),  # affichage du plus recent au plus ancien
            'events_chrono': events,
            'nb_events': len(events),
            'nb_incoherences': nb_incoherences_point,
            'is_incoherent': is_incoherent,
        })

    if filter_incoherences:
        points_groups = [group for group in points_groups if group['is_incoherent']]

    points_groups.sort(key=lambda group: (
        group['geo']['region'] or '',
        group['geo']['district'] or '',
        group['geo']['commune'] or '',
        group['ouvrage'].nom_ouvrage if group['ouvrage'] else '',
        group['point'].code_point_eau or group['point'].nomabonne or '',
    ))

    stats_incoherences = {
        'nb_points_incoherents': nb_points_incoherents,
        'nb_points_incoherents_pct': percentage_of_scoped_points(nb_points_incoherents),
        'nb_incoherences': nb_incoherences_total,
    }

    selected_organisation = organisations.filter(id=filter_organisation).first() if filter_organisation and filter_organisation != 'all' else None

    return {
        'organisations': organisations,
        'selected_organisation': selected_organisation,
        'employee_options': employee_options,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'points_groups': points_groups,
        'stats': {
            'total_evenements': total_history_events,
            'points_coupes_historique': len(ever_cut_ids),
            'points_coupes_historique_pct': percentage_of_scoped_points(len(ever_cut_ids)),
            'encore_coupes': len(current_cut_ids),
            'encore_coupes_pct': percentage_of_scoped_points(len(current_cut_ids)),
            'remis': len(restored_ids),
            'remis_pct': percentage_of_scoped_points(len(restored_ids)),
            'total_points': total_scoped_points,
        },
        'stats_bp': stats_bp,
        'stats_autres': stats_autres,
        'stats_incoherences': stats_incoherences,
        'filters': {
            'organisation': filter_organisation,
            'employe': filter_employe,
            'region': filter_region,
            'district': filter_district,
            'commune': filter_commune,
            'ouvrage': filter_ouvrage,
            'categorie_point_eau': filter_categorie_point_eau,
            'search': filter_search,
            'vue': filter_vue,
            'incoherences': filter_incoherences,
            'date_debut': filter_date_debut,
            'date_fin': filter_date_fin,
        },
    }


@login_required
def historique_coupures_eau(request):
    """Dashboard complet des coupures et remises en eau, regroupe par point d'eau
    (Region > District > Commune > Ouvrage > Point d'eau) avec detection des
    incoherences (coupures/remises consecutives du meme type)."""
    dataset = _build_historique_coupures_dataset(request)
    points_groups = dataset.pop('points_groups')

    paginator = Paginator(points_groups, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    prev_region = object()
    prev_district = object()
    prev_commune = object()
    prev_ouvrage = object()
    for group in page_obj.object_list:
        group['nouvelle_region'] = (group['geo']['region'] != prev_region)
        group['nouveau_district'] = group['nouvelle_region'] or (group['geo']['district'] != prev_district)
        group['nouvelle_commune'] = group['nouveau_district'] or (group['geo']['commune'] != prev_commune)
        group['nouveau_ouvrage'] = group['nouvelle_commune'] or (group['ouvrage'] != prev_ouvrage)
        prev_region = group['geo']['region']
        prev_district = group['geo']['district']
        prev_commune = group['geo']['commune']
        prev_ouvrage = group['ouvrage']

    query_params = request.GET.copy()
    query_params.pop('page', None)

    context = dict(dataset)
    context['page_obj'] = page_obj
    context['query_without_page'] = query_params.urlencode()
    context['raison_choices'] = CoupureEau.RAISON_CHOICES
    context['type_choices'] = CoupureEau.TYPE_COUPURE_CHOICES
    return render(request, 'billing/historique_coupures_eau.html', context)


@login_required
def export_historique_coupures_eau_excel(request):
    """Export Excel du tableau d'historique des coupures/remises, avec la
    meme hierarchie geographique et le meme signalement des incoherences que
    la page (respecte les filtres actifs)."""
    dataset = _build_historique_coupures_dataset(request)
    points_groups = dataset['points_groups']

    wb = Workbook()
    ws = wb.active
    ws.title = "Historique coupures d'eau"

    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    anomaly_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    headers = [
        'Région', 'District', 'Commune', 'Village', 'Ouvrage', 'Responsable(s)',
        "Point d'eau", 'Abonné', 'État actuel', 'Date événement', 'Type événement',
        'Raison', 'Notes', 'Saisi par', 'Incohérence', "Nb incohérences (point d'eau)",
    ]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border

    row_num = 2
    for group in points_groups:
        point = group['point']
        ouvrage = group['ouvrage']
        geo = group['geo']
        responsables = ', '.join(group['responsables']) if group['responsables'] else ''
        etat_actuel = 'Coupé' if group['current_cut'] else 'En service'
        for event in group['events_chrono']:
            values = [
                geo['region'], geo['district'], geo['commune'], geo['village'],
                ouvrage.nom_ouvrage if ouvrage else 'N/A',
                responsables,
                point.code_point_eau or 'Sans code',
                point.nomabonne or 'Sans abonné',
                etat_actuel,
                event['date_evenement'].strftime('%d/%m/%Y') if event['date_evenement'] else '',
                event['type_label'],
                event['raison'],
                event['notes'],
                event['cree_par'],
                'Oui' if event['is_anomaly'] else 'Non',
                group['nb_incoherences'],
            ]
            for col_num, value in enumerate(values, 1):
                cell = ws.cell(row=row_num, column=col_num, value=value)
                cell.border = border
                if event['is_anomaly']:
                    cell.fill = anomaly_fill
            row_num += 1

    column_widths = [16, 16, 18, 16, 26, 22, 16, 20, 12, 14, 16, 16, 30, 18, 12, 14]
    for idx, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = 'A2'

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"historique_coupures_eau_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@require_http_methods(["GET"])
def api_points_eau_actifs(request):
    try:
        allowed_ouvrage_ids = list(_get_allowed_ouvrage_ids(request.user))
        resolved_ouvrage_ids, requested_ouvrage_ids = _resolve_requested_ouvrage_ids(request, allowed_ouvrage_ids)
        cutoff_date = _get_stale_coupure_cutoff_date()
        _clear_stale_forfaitaire_points(ouvrage_ids=resolved_ouvrage_ids)

        if request.GET.get('ouvrage_id') and requested_ouvrage_ids and not resolved_ouvrage_ids:
            return JsonResponse({'success': False, 'error': 'Ouvrage non autorisé'}, status=403)

        if requested_ouvrage_ids and not resolved_ouvrage_ids:
            return JsonResponse({
                'success': True,
                'points_eau': [],
                'total': 0
            })

        points_eau_qs = PointEau.objects.filter(
            datearretbranchement__isnull=True,
            ouvrage_id__in=resolved_ouvrage_ids
        ).select_related(
            'ouvrage',
            'type_point_eau',
            'parcelle__village'
        ).order_by('ouvrage__nom_ouvrage', 'code_point_eau', 'nomabonne')

        points_eau_data = []
        for pe in points_eau_qs:
            point_state = _serialize_point_eau_tarif_context(pe, cutoff_date=cutoff_date)

            points_eau_data.append({
                'id': str(pe.id),
                'code': pe.code_point_eau or '',
                'nom': pe.nomabonne or '',
                'village': point_state['village'],
                'type': pe.type_point_eau.nom_type if pe.type_point_eau else 'N/A',
                'ouvrage_id': str(pe.ouvrage_id) if pe.ouvrage_id else '',
                'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
                'tarifforfaitaire': point_state['tarifforfaitaire'],
                'tarifforfaitaire_display': point_state['tarifforfaitaire_display'],
                'est_coupe_plus_un_an': point_state['est_coupe_plus_un_an'],
            })

        return JsonResponse({
            'success': True,
            'points_eau': points_eau_data,
            'total': len(points_eau_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_couper_point_eau(request):
    """
    API pour couper un point d'eau (paiement volumétrique)
    Met à jour le champ datearretbranchement du PointEau
    """
    try:
        data = json.loads(request.body)
        point_eau_id = data.get('point_eau_id')
        date_coupure = data.get('date_coupure')  # Format: YYYY-MM-DD
        motif = data.get('motif', '')

        if not point_eau_id or not date_coupure:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau et date de coupure obligatoires'
            }, status=400)

        # Récupérer le point d'eau
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        point_eau = PointEau.objects.filter(
            id=point_eau_id,
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not point_eau:
            return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable ou non autorisé'}, status=404)

        # Vérifier qu'il n'est pas déjà coupé
        if point_eau.datearretbranchement:
            return JsonResponse({
                'success': False,
                'error': f'Point d\'eau déjà coupé depuis le {point_eau.datearretbranchement.strftime("%d/%m/%Y")}'
            }, status=400)

        # Parser la date et convertir en datetime aware (timezone Madagascar)
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        date_naive = datetime.strptime(date_coupure, '%Y-%m-%d')
        date_aware = tz_madagascar.localize(date_naive)

        # Créer l'événement d'historique (source de vérité)
        CoupureEau.objects.create(
            point_eau=point_eau,
            type_evenement='coupure',
            date_evenement=date_aware.date(),
            raison='autre',
            notes=motif or '',
            cree_par=request.user if request.user.is_authenticated else None
        )

        return JsonResponse({
            'success': True,
            'message': f'Point d\'eau coupé avec succès le {date_aware.strftime("%d/%m/%Y")}',
            'point_eau_id': str(point_eau.id),
            'date_arret': date_aware.strftime('%Y-%m-%d')
        })

    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Point d\'eau introuvable'
        }, status=404)
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_remettre_point_eau(request):
    """
    API pour remettre en service un point d'eau (paiement volumétrique)
    Supprime le champ datearretbranchement du PointEau
    """
    try:
        data = json.loads(request.body)
        point_eau_id = data.get('point_eau_id')
        date_remise = data.get('date_remise')  # Format: YYYY-MM-DD
        motif = data.get('motif', '')

        if not point_eau_id or not date_remise:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau et date de remise obligatoires'
            }, status=400)

        # Récupérer le point d'eau
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        point_eau = PointEau.objects.filter(
            id=point_eau_id,
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not point_eau:
            return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable ou non autorisé'}, status=404)

        # Vérifier qu'il est bien coupé
        if not point_eau.datearretbranchement:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau n\'est pas coupé'
            }, status=400)

        # Parser la date
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        date_naive = datetime.strptime(date_remise, '%Y-%m-%d')
        date_aware = tz_madagascar.localize(date_naive)

        # Vérifier que la date de remise est après la date de coupure
        # Convertir datearretbranchement en date pour comparaison
        date_arret = point_eau.datearretbranchement.date() if isinstance(point_eau.datearretbranchement, datetime) else point_eau.datearretbranchement
        if date_aware.date() < date_arret:
            return JsonResponse({
                'success': False,
                'error': f'La date de remise doit être après la date de coupure ({date_arret.strftime("%d/%m/%Y")})'
            }, status=400)

        # Créer l'événement de remise (mettra à jour le statut via sync)
        CoupureEau.objects.create(
            point_eau=point_eau,
            type_evenement='remise',
            date_evenement=date_aware.date(),
            raison='autre',
            notes=motif or '',
            cree_par=request.user if request.user.is_authenticated else None
        )

        return JsonResponse({
            'success': True,
            'message': f'Point d\'eau remis en service le {date_aware.strftime("%d/%m/%Y")}',
            'point_eau_id': str(point_eau.id),
            'date_remise': date_aware.strftime('%Y-%m-%d')
        })

    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Point d\'eau introuvable'
        }, status=404)
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_points_eau_coupes(request):
    """
    API pour récupérer la liste des points d'eau coupés (avec datearretbranchement renseignée)
    Filtrable par ouvrage
    """
    try:
        allowed_ouvrage_ids = list(_get_allowed_ouvrage_ids(request.user))
        resolved_ouvrage_ids, requested_ouvrage_ids = _resolve_requested_ouvrage_ids(request, allowed_ouvrage_ids)
        cutoff_date = _get_stale_coupure_cutoff_date()
        _clear_stale_forfaitaire_points(ouvrage_ids=resolved_ouvrage_ids)

        if request.GET.get('ouvrage_id') and requested_ouvrage_ids and not resolved_ouvrage_ids:
            return JsonResponse({'success': False, 'error': 'Ouvrage non autorisé'}, status=403)

        if requested_ouvrage_ids and not resolved_ouvrage_ids:
            return JsonResponse({
                'success': True,
                'points_eau_coupes': [],
                'total': 0
            })

        # Base queryset: points d'eau coupés (datearretbranchement renseignée)
        points_eau_qs = PointEau.objects.filter(
            datearretbranchement__isnull=False,
            ouvrage_id__in=resolved_ouvrage_ids
        ).select_related(
            'ouvrage',
            'type_point_eau',
            'parcelle__village__fokontany__commune'
        ).order_by('ouvrage__nom_ouvrage', 'code_point_eau', 'nomabonne')

        # Construire la liste
        points_eau_data = []
        for pe in points_eau_qs:
            point_state = _serialize_point_eau_tarif_context(pe, cutoff_date=cutoff_date)

            points_eau_data.append({
                'id': str(pe.id),
                'code': pe.code_point_eau or '',
                'abonne': pe.nomabonne or '',
                'village': point_state['village'],
                'type': pe.type_point_eau.nom_type if pe.type_point_eau else 'N/A',
                'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
                'date_arret': pe.datearretbranchement.strftime('%Y-%m-%d') if pe.datearretbranchement else None,
                'date_arret_display': pe.datearretbranchement.strftime('%d/%m/%Y') if pe.datearretbranchement else 'N/A',
                'tarifforfaitaire': point_state['tarifforfaitaire'],
                'tarifforfaitaire_display': point_state['tarifforfaitaire_display'],
                'est_coupe_plus_un_an': point_state['est_coupe_plus_un_an'],
            })

        return JsonResponse({
            'success': True,
            'points_eau_coupes': points_eau_data,
            'total': len(points_eau_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_historique_coupures(request):
    """
    API pour récupérer l'historique des coupures/remises en eau.
    Filtres optionnels:
    - point_eau_id
    - ouvrage_id
    """
    try:
        point_eau_id = request.GET.get('point_eau_id')
        allowed_ouvrage_ids = list(_get_allowed_ouvrage_ids(request.user))
        resolved_ouvrage_ids, requested_ouvrage_ids = _resolve_requested_ouvrage_ids(request, allowed_ouvrage_ids)
        cutoff_date = _get_stale_coupure_cutoff_date()
        raison_labels = dict(CoupureEau.RAISON_CHOICES)
        _clear_stale_forfaitaire_points(ouvrage_ids=resolved_ouvrage_ids)

        if request.GET.get('ouvrage_id') and requested_ouvrage_ids and not resolved_ouvrage_ids:
            return JsonResponse({'success': False, 'error': 'Ouvrage non autorisé'}, status=403)

        qs = CoupureEau.objects.select_related(
            'point_eau',
            'point_eau__ouvrage',
            'point_eau__parcelle__village',
            'cree_par'
        ).filter(
            point_eau__ouvrage_id__in=resolved_ouvrage_ids
        ).order_by(
            'point_eau__ouvrage__nom_ouvrage',
            'point_eau__code_point_eau',
            'point_eau__nomabonne',
            'date_evenement',
            'created_at'
        )

        if point_eau_id:
            qs = qs.filter(point_eau_id=point_eau_id)

        if point_eau_id:
            events = qs
        else:
            events = qs[:500]

        historique = []
        event_point_eau_ids = set()
        for event in events:
            point_state = _serialize_point_eau_tarif_context(event.point_eau, cutoff_date=cutoff_date) if event.point_eau else {}

            if event.point_eau_id:
                event_point_eau_ids.add(event.point_eau_id)

            historique.append({
                'id': str(event.id),
                'type_evenement': event.type_evenement,
                'type_label': dict(CoupureEau.TYPE_COUPURE_CHOICES).get(event.type_evenement, event.type_evenement),
                'date_evenement': event.date_evenement.strftime('%Y-%m-%d') if event.date_evenement else None,
                'date_evenement_display': event.date_evenement.strftime('%d/%m/%Y') if event.date_evenement else 'N/A',
                'raison': event.raison or '',
                'raison_label': raison_labels.get(event.raison, event.raison or ''),
                'notes': event.notes or '',
                'point_eau_id': str(event.point_eau.id) if event.point_eau else None,
                'code_point_eau': event.point_eau.code_point_eau if event.point_eau else '',
                'abonne': event.point_eau.nomabonne if event.point_eau else '',
                'ouvrage': event.point_eau.ouvrage.nom_ouvrage if (event.point_eau and event.point_eau.ouvrage) else 'N/A',
                'village': point_state.get('village', 'N/A'),
                'cree_par': event.cree_par.username if event.cree_par else 'N/A',
                'created_at': event.created_at.strftime('%d/%m/%Y %H:%M') if event.created_at else '',
                'created_at_iso': event.created_at.isoformat() if event.created_at else '',
                'editable': True,
                'source': 'coupure_eau',
                'tarifforfaitaire': point_state.get('tarifforfaitaire'),
                'tarifforfaitaire_display': point_state.get('tarifforfaitaire_display', 'Non defini'),
                'date_arret_display_current': point_state.get('date_arret_display', ''),
                'est_coupe_plus_un_an': point_state.get('est_coupe_plus_un_an', False),
            })

        if point_eau_id:
            # Fallback legacy: point d'eau coupe via datearretbranchement sans ligne CoupureEau (point ciblé).
            if not historique:
                pe = PointEau.objects.select_related(
                    'ouvrage',
                    'parcelle__village'
                ).filter(
                    id=point_eau_id,
                    ouvrage_id__in=allowed_ouvrage_ids
                ).first()

                if pe and pe.datearretbranchement:
                    date_arret = pe.datearretbranchement
                    if isinstance(date_arret, datetime):
                        date_arret = date_arret.date()

                    point_state = _serialize_point_eau_tarif_context(pe, cutoff_date=cutoff_date)

                    historique.append({
                        'id': f'legacy-{pe.id}',
                        'type_evenement': 'coupure',
                        'type_label': "Coupure d'eau",
                        'date_evenement': date_arret.strftime('%Y-%m-%d'),
                        'date_evenement_display': date_arret.strftime('%d/%m/%Y'),
                        'raison': 'autre',
                        'raison_label': raison_labels.get('autre', 'Autre'),
                        'notes': "Historique non trace (ancienne coupure).",
                        'point_eau_id': str(pe.id),
                        'code_point_eau': pe.code_point_eau or '',
                        'abonne': pe.nomabonne or '',
                        'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
                        'village': point_state['village'],
                        'cree_par': 'N/A',
                        'created_at': '',
                        'created_at_iso': '',
                        'editable': True,
                        'source': 'point_eau_datearret',
                        'tarifforfaitaire': point_state['tarifforfaitaire'],
                        'tarifforfaitaire_display': point_state['tarifforfaitaire_display'],
                        'date_arret_display_current': point_state['date_arret_display'],
                        'est_coupe_plus_un_an': point_state['est_coupe_plus_un_an'],
                    })
        elif resolved_ouvrage_ids:
            # Fallback legacy: inclure les points encore coupés sur les ouvrages filtrés non encore tracés en CoupureEau.
            legacy_points = PointEau.objects.select_related(
                'ouvrage',
                'parcelle__village'
            ).filter(
                datearretbranchement__isnull=False,
                ouvrage_id__in=resolved_ouvrage_ids
            ).exclude(
                id__in=event_point_eau_ids
            )

            for pe in legacy_points:
                date_arret = pe.datearretbranchement
                if isinstance(date_arret, datetime):
                    date_arret = date_arret.date()

                point_state = _serialize_point_eau_tarif_context(pe, cutoff_date=cutoff_date)

                historique.append({
                    'id': f'legacy-{pe.id}',
                    'type_evenement': 'coupure',
                    'type_label': "Coupure d'eau",
                    'date_evenement': date_arret.strftime('%Y-%m-%d'),
                    'date_evenement_display': date_arret.strftime('%d/%m/%Y'),
                    'raison': 'autre',
                    'raison_label': raison_labels.get('autre', 'Autre'),
                    'notes': "Historique non trace (ancienne coupure).",
                    'point_eau_id': str(pe.id),
                    'code_point_eau': pe.code_point_eau or '',
                    'abonne': pe.nomabonne or '',
                    'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
                    'village': point_state['village'],
                    'cree_par': 'N/A',
                    'created_at': '',
                    'created_at_iso': '',
                    'editable': True,
                    'source': 'point_eau_datearret',
                    'tarifforfaitaire': point_state['tarifforfaitaire'],
                    'tarifforfaitaire_display': point_state['tarifforfaitaire_display'],
                    'date_arret_display_current': point_state['date_arret_display'],
                    'est_coupe_plus_un_an': point_state['est_coupe_plus_un_an'],
                })

        historique.sort(key=lambda item: (
            (item.get('ouvrage') or '').lower(),
            (item.get('code_point_eau') or '').lower(),
            (item.get('abonne') or '').lower(),
            item.get('date_evenement') or '',
            item.get('created_at_iso') or '',
            item.get('type_evenement') or '',
        ))

        return JsonResponse({
            'success': True,
            'historique': historique,
            'total': len(historique)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_modifier_historique_coupure(request):
    """
    API pour modifier un événement de coupure/remise (date et notes).
    """
    try:
        data = json.loads(request.body or '{}')
        coupure_id = data.get('coupure_id')
        date_evenement = data.get('date_evenement')  # YYYY-MM-DD
        raison = data.get('raison')
        notes = data.get('notes')
        type_evenement = data.get('type_evenement')

        if not coupure_id:
            return JsonResponse({'success': False, 'error': 'coupure_id est obligatoire'}, status=400)

        if type_evenement:
            type_evenement = type_evenement.strip().lower()
            valid_types = {t[0] for t in CoupureEau.TYPE_COUPURE_CHOICES}
            if type_evenement not in valid_types:
                return JsonResponse({
                    'success': False,
                    'error': "type_evenement invalide (attendu 'coupure' ou 'remise')"
                }, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        if str(coupure_id).startswith('legacy-'):
            point_eau_id = str(coupure_id).replace('legacy-', '', 1)
            point_eau = PointEau.objects.filter(
                id=point_eau_id,
                ouvrage_id__in=allowed_ouvrage_ids
            ).first()

            if not point_eau:
                return JsonResponse({'success': False, 'error': "Point d'eau introuvable"}, status=404)

            if not point_eau.datearretbranchement:
                return JsonResponse({
                    'success': False,
                    'error': "Ce point d'eau n'est pas actuellement coupé"
                }, status=400)

            if not date_evenement:
                return JsonResponse({
                    'success': False,
                    'error': 'date_evenement est obligatoire pour cet historique legacy'
                }, status=400)

            try:
                date_evenement_value = datetime.strptime(date_evenement, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
                }, status=400)

            event = CoupureEau.objects.create(
                point_eau=point_eau,
                type_evenement=type_evenement or 'coupure',
                date_evenement=date_evenement_value,
                raison=raison if raison in {r[0] for r in CoupureEau.RAISON_CHOICES} else 'autre',
                notes=notes or '',
                cree_par=request.user if request.user.is_authenticated else None
            )

            return JsonResponse({
                'success': True,
                'message': 'Historique legacy converti avec succès',
                'event': {
                    'id': str(event.id),
                    'date_evenement': event.date_evenement.strftime('%Y-%m-%d') if event.date_evenement else None,
                    'date_evenement_display': event.date_evenement.strftime('%d/%m/%Y') if event.date_evenement else 'N/A',
                    'type_evenement': event.type_evenement
                }
            })

        try:
            event = CoupureEau.objects.select_related('point_eau').get(
                id=coupure_id,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids
            )
        except CoupureEau.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Événement introuvable'}, status=404)

        if date_evenement:
            try:
                event.date_evenement = datetime.strptime(date_evenement, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
                }, status=400)

        if type_evenement:
            event.type_evenement = type_evenement

        if raison is not None:
            # Conserver uniquement les raisons autorisées (sinon forcer "autre")
            raisons_valides = {r[0] for r in CoupureEau.RAISON_CHOICES}
            event.raison = raison if raison in raisons_valides else 'autre'

        if notes is not None:
            event.notes = notes

        event.save()  # déclenche sync du statut du point d'eau

        return JsonResponse({
            'success': True,
            'message': 'Événement modifié avec succès',
            'event': {
                'id': str(event.id),
                'date_evenement': event.date_evenement.strftime('%Y-%m-%d') if event.date_evenement else None,
                'date_evenement_display': event.date_evenement.strftime('%d/%m/%Y') if event.date_evenement else 'N/A',
                'type_evenement': event.type_evenement
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_historique_coupure(request):
    """
    API pour supprimer un événement de coupure/remise.
    """
    try:
        data = json.loads(request.body or '{}')
        coupure_id = data.get('coupure_id')

        if not coupure_id:
            return JsonResponse({'success': False, 'error': 'coupure_id est obligatoire'}, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        if str(coupure_id).startswith('legacy-'):
            point_eau_id = str(coupure_id).replace('legacy-', '', 1)
            point_eau = PointEau.objects.filter(
                id=point_eau_id,
                ouvrage_id__in=allowed_ouvrage_ids
            ).first()

            if not point_eau:
                return JsonResponse({'success': False, 'error': "Point d'eau introuvable"}, status=404)

            if not point_eau.datearretbranchement:
                return JsonResponse({
                    'success': False,
                    'error': 'Aucune coupe legacy Ã  supprimer'
                }, status=400)

            point_eau.datearretbranchement = None
            point_eau.save(update_fields=['datearretbranchement'])

            return JsonResponse({
                'success': True,
                'message': 'Événement legacy supprimé avec succès'
            })

        try:
            event = CoupureEau.objects.get(
                id=coupure_id,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids
            )
        except CoupureEau.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Événement introuvable'}, status=404)

        event.delete()  # resync du point d'eau géré dans le modèle

        return JsonResponse({
            'success': True,
            'message': 'Événement supprimé avec succès'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_historique_coupures_bulk(request):
    """
    API pour supprimer plusieurs événements de coupure/remise en un seul appel
    (sélection multiple depuis le tableau historique).
    """
    try:
        data = json.loads(request.body or '{}')
        coupure_ids = data.get('coupure_ids') or []

        if not isinstance(coupure_ids, list) or not coupure_ids:
            return JsonResponse({'success': False, 'error': 'coupure_ids est obligatoire (liste non vide)'}, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        legacy_point_ids = []
        real_event_ids = []
        for coupure_id in coupure_ids:
            coupure_id = str(coupure_id)
            if coupure_id.startswith('legacy-'):
                legacy_point_ids.append(coupure_id.replace('legacy-', '', 1))
            else:
                real_event_ids.append(coupure_id)

        nb_supprimes = 0
        erreurs = []

        if legacy_point_ids:
            legacy_points = list(PointEau.objects.filter(
                id__in=legacy_point_ids,
                ouvrage_id__in=allowed_ouvrage_ids,
                datearretbranchement__isnull=False,
            ))
            found_ids = {str(point.id) for point in legacy_points}
            for missing_id in set(legacy_point_ids) - found_ids:
                erreurs.append(f"legacy-{missing_id}: introuvable")
            for point in legacy_points:
                point.datearretbranchement = None
                point.save(update_fields=['datearretbranchement'])
                nb_supprimes += 1

        if real_event_ids:
            events = CoupureEau.objects.filter(
                id__in=real_event_ids,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids,
            )
            found_ids = {str(event.id) for event in events}
            for missing_id in set(real_event_ids) - found_ids:
                erreurs.append(f"{missing_id}: introuvable")
            for event in events:
                event.delete()  # resync du point d'eau géré dans le modèle
                nb_supprimes += 1

        return JsonResponse({
            'success': True,
            'message': f"{nb_supprimes} événement(s) supprimé(s)" + (f", {len(erreurs)} erreur(s)" if erreurs else ''),
            'nb_supprimes': nb_supprimes,
            'erreurs': erreurs,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_modifier_tarif_forfaitaire_point_eau(request):
    """
    Met à jour le tarif forfaitaire d'un point d'eau depuis l'écran de gestion
    des coupures/remises.
    """
    try:
        data = json.loads(request.body or '{}')
        point_eau_id = data.get('point_eau_id')
        tarif_raw = data.get('tarifforfaitaire')

        if not point_eau_id:
            return JsonResponse({
                'success': False,
                'error': "Point d'eau obligatoire"
            }, status=400)

        allowed_ouvrage_ids = list(_get_allowed_ouvrage_ids(request.user))
        point_eau = PointEau.objects.select_related(
            'ouvrage',
            'parcelle__village'
        ).filter(
            id=point_eau_id,
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()

        if not point_eau:
            return JsonResponse({
                'success': False,
                'error': "Point d'eau introuvable ou non autorise"
            }, status=404)

        _clear_stale_forfaitaire_points(point_eau_ids=[point_eau.id])
        point_eau.refresh_from_db()

        if tarif_raw in (None, ''):
            point_eau.tarifforfaitaire = None
            point_eau.save(update_fields=['tarifforfaitaire'])
            point_state = _serialize_point_eau_tarif_context(point_eau)
            return JsonResponse({
                'success': True,
                'message': 'Tarif forfaitaire vide avec succes',
                'point_eau': point_state
            })

        try:
            tarif_value = float(str(tarif_raw).replace(',', '.').strip())
        except (TypeError, ValueError):
            return JsonResponse({
                'success': False,
                'error': 'Tarif forfaitaire invalide'
            }, status=400)

        if tarif_value < 0:
            return JsonResponse({
                'success': False,
                'error': 'Le tarif forfaitaire doit etre positif'
            }, status=400)

        if _is_point_eau_cut_since_more_than_one_year(point_eau):
            point_state = _serialize_point_eau_tarif_context(point_eau)
            return JsonResponse({
                'success': False,
                'error': "Impossible de renseigner un tarif forfaitaire: ce point d'eau est coupe depuis plus d'un an sans remise en eau.",
                'point_eau': point_state
            }, status=400)

        point_eau.tarifforfaitaire = tarif_value
        point_eau.save(update_fields=['tarifforfaitaire'])
        point_state = _serialize_point_eau_tarif_context(point_eau)

        return JsonResponse({
            'success': True,
            'message': 'Tarif forfaitaire mis a jour avec succes',
            'point_eau': point_state
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
