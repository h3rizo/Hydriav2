import json
import math
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.billing.models import PointEau
from apps.employees.permissions import employe_required, filter_queryset_by_permissions
from apps.geography.models import Parcelle, Village
from apps.infrastructure.models import EquipementConstitutif

from .models import GPSDataQualityReview, Ouvrage


def _threshold(request):
    """Retourne uniquement un seuil GPS pris en charge par l'interface."""
    try:
        value = float(request.GET.get('threshold', '3'))
    except (TypeError, ValueError):
        value = 3.0
    return value if value in {2.0, 3.0} else 3.0


def _village_location_label(village):
    """Libellé non ambigu pour les villages portant le même nom."""
    if not village:
        return ''
    fokontany = getattr(village, 'fokontany', None)
    commune = getattr(fokontany, 'commune', None) if fokontany else None
    district = getattr(commune, 'district', None) if commune else None
    parts = [
        village.nom_village,
        getattr(fokontany, 'nom_fokontany', None),
        getattr(commune, 'nom_commune', None),
        getattr(district, 'nom_district', None),
    ]
    return ' · '.join(str(part) for part in parts if part)


def _parcelle_location_label(parcelle):
    if not parcelle:
        return 'Aucune parcelle'
    return f'{parcelle.reference_parcelle} — {_village_location_label(parcelle.village)}'


def _valid_coordinates(latitude, longitude):
    if latitude is None or longitude is None:
        return False
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(latitude) and math.isfinite(longitude)
        and -90 <= latitude <= 90 and -180 <= longitude <= 180
        and not (abs(latitude) < 1e-9 and abs(longitude) < 1e-9)
    )


def _haversine_km(latitude_1, longitude_1, latitude_2, longitude_2):
    radius = 6371.0088
    lat_1, lat_2 = math.radians(float(latitude_1)), math.radians(float(latitude_2))
    delta_lat = lat_2 - lat_1
    delta_lon = math.radians(float(longitude_2) - float(longitude_1))
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat_1) * math.cos(lat_2) * math.sin(delta_lon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _current_review(review, latitude, longitude):
    if not review or latitude is None or longitude is None:
        return None
    if review.latitude_snapshot is None or review.longitude_snapshot is None:
        return None
    if abs(float(review.latitude_snapshot) - float(latitude)) > 1e-7:
        return None
    if abs(float(review.longitude_snapshot) - float(longitude)) > 1e-7:
        return None
    return review


def _nearest_village(latitude, longitude, villages):
    candidates = [
        village for village in villages
        if _valid_coordinates(village.latitude, village.longitude)
    ]
    if not candidates:
        return None, None
    distances = [
        (_haversine_km(latitude, longitude, village.latitude, village.longitude), village)
        for village in candidates
    ]
    return min(distances, key=lambda item: item[0])


def _entry(entity_type, entity, villages, threshold, review):
    latitude, longitude = entity.latitude, entity.longitude
    ouvrage = entity.ouvrage
    label = (
        entity.nomabonne or entity.code_point_eau or "Point d'eau sans nom"
        if entity_type == 'point_eau'
        else entity.nom or entity.code_equipement or 'Équipement sans nom'
    )
    type_label = (
        getattr(entity.type_point_eau, 'nom_type', '') or "Point d'eau"
        if entity_type == 'point_eau'
        else getattr(entity.type_equipement, 'nom_type', '') or 'Équipement'
    )
    item = {
        'entity_type': entity_type,
        'entity_type_label': "Point d'eau" if entity_type == 'point_eau' else 'Équipement',
        'id': str(entity.id),
        'label': label,
        'type_label': type_label,
        'ouvrage': ouvrage.nom_ouvrage if ouvrage else 'Ouvrage non renseigné',
        'ouvrage_id': str(entity.ouvrage_id or ''),
        'latitude': float(latitude) if latitude is not None else None,
        'longitude': float(longitude) if longitude is not None else None,
        'village': None,
        'village_id': '',
        'distance_km': None,
        'review': None,
    }
    item['coordinate_update_url'] = reverse('organization:gps_quality_coordinate_update')
    item['map_data_url'] = (
        reverse('organization:gps_quality_map_data', kwargs={'ouvrage_id': entity.ouvrage_id})
        if entity.ouvrage_id else ''
    )

    if not _valid_coordinates(latitude, longitude):
        item.update(status='missing_gps', status_label='GPS manquant ou invalide', status_class='badge-error')
        return item

    distance, village = _nearest_village(latitude, longitude, villages)
    if not village:
        item.update(status='missing_reference', status_label='Village de référence sans GPS', status_class='badge-warning')
        return item

    item.update(
        village=village.nom_village,
        village_id=str(village.id),
        distance_km=round(distance, 3),
        map_url=f'https://www.google.com/maps/dir/{float(village.latitude)},{float(village.longitude)}/{float(latitude)},{float(longitude)}',
    )
    active_review = _current_review(review, latitude, longitude)
    if active_review:
        item['review'] = active_review

    if distance <= threshold:
        item.update(status='normal', status_label='Distance cohérente', status_class='badge-success')
    elif active_review and active_review.status == 'confirmed':
        item.update(status='confirmed', status_label='Écart expliqué', status_class='badge-info')
    elif active_review and active_review.status == 'to_correct':
        item.update(status='to_correct', status_label='Correction nécessaire', status_class='badge-error')
    else:
        item.update(status='anomaly', status_label='À contrôler', status_class='badge-warning')
    return item


def _quality_entries(user, threshold):
    ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), user)
    ouvrage_ids = list(ouvrages.values_list('id', flat=True))
    points = list(PointEau.objects.filter(ouvrage_id__in=ouvrage_ids).select_related(
        'ouvrage', 'type_point_eau', 'parcelle__village',
    ))
    equipements = list(EquipementConstitutif.objects.filter(ouvrage_id__in=ouvrage_ids).select_related(
        'ouvrage', 'type_equipement',
    ))
    reviews = {
        (review.entity_type, str(review.entity_id)): review
        for review in GPSDataQualityReview.objects.filter(
            Q(entity_type='point_eau', entity_id__in=[point.id for point in points])
            | Q(entity_type='equipement', entity_id__in=[equipment.id for equipment in equipements])
        ).select_related('reference_village', 'reviewed_by')
    }
    villages_by_ouvrage = {}
    for point in points:
        village = getattr(getattr(point, 'parcelle', None), 'village', None)
        if village and point.ouvrage_id:
            villages_by_ouvrage.setdefault(point.ouvrage_id, {})[village.id] = village

    entries = []
    for point in points:
        village = getattr(getattr(point, 'parcelle', None), 'village', None)
        entries.append(_entry(
            'point_eau', point, [village] if village else [], threshold,
            reviews.get(('point_eau', str(point.id))),
        ))
    for equipment in equipements:
        entries.append(_entry(
            'equipement', equipment,
            list(villages_by_ouvrage.get(equipment.ouvrage_id, {}).values()), threshold,
            reviews.get(('equipement', str(equipment.id))),
        ))
    order = {'to_correct': 0, 'anomaly': 1, 'missing_gps': 2, 'missing_reference': 3, 'confirmed': 4, 'normal': 5}
    return sorted(entries, key=lambda item: (order[item['status']], -(item['distance_km'] or 0), item['ouvrage'], item['label']))


@employe_required
def gps_quality_dashboard(request):
    threshold = _threshold(request)
    entries = _quality_entries(request.user, threshold)
    stats = {
        'total': len(entries),
        'anomaly': sum(item['status'] in {'anomaly', 'to_correct'} for item in entries),
        'confirmed': sum(item['status'] == 'confirmed' for item in entries),
        'incomplete': sum(item['status'] in {'missing_gps', 'missing_reference'} for item in entries),
        'normal': sum(item['status'] == 'normal' for item in entries),
    }
    entity_filter = request.GET.get('entity', 'all')
    status_filter = request.GET.get('status', 'all')
    query = request.GET.get('q', '').strip().lower()
    filtered = entries
    if entity_filter in {'point_eau', 'equipement'}:
        filtered = [item for item in filtered if item['entity_type'] == entity_filter]
    if status_filter == 'attention':
        filtered = [item for item in filtered if item['status'] in {'anomaly', 'to_correct'}]
    elif status_filter == 'incomplete':
        filtered = [item for item in filtered if item['status'] in {'missing_gps', 'missing_reference'}]
    elif status_filter in {'confirmed', 'normal'}:
        filtered = [item for item in filtered if item['status'] == status_filter]
    if query:
        filtered = [item for item in filtered if query in ' '.join([
            item['label'], item['ouvrage'], item['type_label'], item['village'] or '',
        ]).lower()]
    page = Paginator(filtered, 50).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'organization/gps_quality_dashboard.html', {
        'page_obj': page, 'stats': stats, 'threshold': threshold,
        'entity_filter': entity_filter, 'status_filter': status_filter,
        'query': request.GET.get('q', ''), 'pagination_query': params.urlencode(),
    })


@employe_required
@require_http_methods(['POST'])
def gps_quality_review(request):
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données JSON invalides.'}, status=400)
    entity_type = payload.get('entity_type')
    entity_id = payload.get('entity_id')
    status = payload.get('status')
    explanation = str(payload.get('explanation') or '').strip()
    if entity_type not in {'point_eau', 'equipement'} or status not in {'confirmed', 'to_correct'}:
        return JsonResponse({'success': False, 'error': 'Décision invalide.'}, status=400)
    if status == 'confirmed' and len(explanation) < 10:
        return JsonResponse({'success': False, 'error': "Expliquez la raison de l'écart (10 caractères minimum)."}, status=400)
    ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    model = PointEau if entity_type == 'point_eau' else EquipementConstitutif
    entity_queryset = model.objects.filter(ouvrage__in=ouvrages)
    if entity_type == 'point_eau':
        entity_queryset = entity_queryset.select_related('parcelle__village')
    entity = get_object_or_404(entity_queryset, id=entity_id)
    if entity_type == 'point_eau':
        reference_villages = [entity.parcelle.village] if entity.parcelle and entity.parcelle.village else []
    else:
        reference_villages = list(Village.objects.filter(
            parcelles__pointeau__ouvrage_id=entity.ouvrage_id,
        ).distinct())
    distance, village = (None, None)
    if _valid_coordinates(entity.latitude, entity.longitude):
        distance, village = _nearest_village(entity.latitude, entity.longitude, reference_villages)
    review, _ = GPSDataQualityReview.objects.update_or_create(
        entity_type=entity_type, entity_id=entity.id,
        defaults={
            'status': status, 'explanation': explanation,
            'latitude_snapshot': Decimal(str(entity.latitude)) if entity.latitude is not None else None,
            'longitude_snapshot': Decimal(str(entity.longitude)) if entity.longitude is not None else None,
            'distance_km_snapshot': Decimal(str(round(distance, 3))) if distance is not None else None,
            'reference_village': village, 'reviewed_by': request.user,
        },
    )
    return JsonResponse({'success': True, 'message': review.get_status_display()})


@employe_required
def gps_quality_map_data(request, ouvrage_id):
    ouvrage = get_object_or_404(
        filter_queryset_by_permissions(Ouvrage.objects.all(), request.user), id=ouvrage_id,
    )
    points = list(PointEau.objects.filter(ouvrage=ouvrage).select_related(
        'type_point_eau',
        'parcelle__village__fokontany__commune__district',
    ))
    equipements = list(EquipementConstitutif.objects.filter(ouvrage=ouvrage).select_related('type_equipement'))
    villages = {}
    for point in points:
        village = getattr(getattr(point, 'parcelle', None), 'village', None)
        if village:
            villages[village.id] = village
    village_list = list(villages.values())
    village_name_counts = {}
    for village in village_list:
        normalized_name = (village.nom_village or '').strip().casefold()
        if normalized_name:
            village_name_counts[normalized_name] = village_name_counts.get(normalized_name, 0) + 1

    def marker(entity_type, entity, reference_village=None):
        type_object = entity.type_point_eau if entity_type == 'point_eau' else entity.type_equipement
        return {
            'entity_type': entity_type,
            'id': str(entity.id),
            'label': (
                entity.nomabonne or entity.code_point_eau or "Point d'eau"
                if entity_type == 'point_eau' else entity.nom or entity.code_equipement or 'Équipement'
            ),
            'type_label': getattr(type_object, 'nom_type', '') or '',
            'latitude': float(entity.latitude) if entity.latitude is not None else None,
            'longitude': float(entity.longitude) if entity.longitude is not None else None,
            'reference_village_id': str(reference_village.id) if reference_village else '',
            'reference_village_label': _village_location_label(reference_village),
            'reference_mode': 'assigned' if entity_type == 'point_eau' else 'nearest',
            'parcelle_id': str(entity.parcelle_id) if entity_type == 'point_eau' and entity.parcelle_id else '',
            'parcelle_label': _parcelle_location_label(entity.parcelle) if entity_type == 'point_eau' else '',
        }

    markers = []
    for point in points:
        reference = getattr(getattr(point, 'parcelle', None), 'village', None)
        markers.append(marker('point_eau', point, reference))
    for equipment in equipements:
        reference = None
        if _valid_coordinates(equipment.latitude, equipment.longitude):
            _, reference = _nearest_village(equipment.latitude, equipment.longitude, village_list)
        markers.append(marker('equipement', equipment, reference))
    parcel_assignments = []
    for point in points:
        parcel = point.parcelle
        village = parcel.village if parcel else None
        normalized_name = (village.nom_village or '').strip().casefold() if village else ''
        parcel_assignments.append({
            'point_id': str(point.id),
            'point_label': point.nomabonne or point.code_point_eau or "Point d'eau sans nom",
            'point_type': getattr(point.type_point_eau, 'nom_type', '') or "Point d'eau",
            'parcel_id': str(parcel.id) if parcel else '',
            'parcel_reference': parcel.reference_parcelle if parcel else '',
            'parcel_label': _parcelle_location_label(parcel),
            'village_id': str(village.id) if village else '',
            'village_name': village.nom_village if village else '',
            'village_label': _village_location_label(village),
            'homonym_warning': bool(normalized_name and village_name_counts.get(normalized_name, 0) > 1),
        })
    return JsonResponse({
        'success': True,
        'ouvrage': {'id': str(ouvrage.id), 'label': ouvrage.nom_ouvrage},
        'threshold_km': _threshold(request),
        'parcel_search_url': reverse('organization:gps_quality_parcel_search'),
        'parcel_update_url': reverse('organization:gps_quality_point_parcel_update'),
        'parcel_assignments': parcel_assignments,
        'homonymous_village_count': sum(count > 1 for count in village_name_counts.values()),
        'villages': [{
            'id': str(village.id), 'label': village.nom_village,
            'location_label': _village_location_label(village),
            'latitude': float(village.latitude) if village.latitude is not None else None,
            'longitude': float(village.longitude) if village.longitude is not None else None,
        } for village in village_list],
        'entities': markers,
    })


@employe_required
def gps_quality_parcel_search(request):
    query = str(request.GET.get('q') or '').strip()
    if len(query) < 2:
        return JsonResponse({'success': True, 'parcels': []})
    parcels = Parcelle.objects.select_related(
        'village__fokontany__commune__district',
    ).filter(
        Q(reference_parcelle__icontains=query)
        | Q(village__nom_village__icontains=query)
        | Q(village__fokontany__nom_fokontany__icontains=query)
        | Q(village__fokontany__commune__nom_commune__icontains=query)
        | Q(village__fokontany__commune__district__nom_district__icontains=query)
    ).order_by(
        'village__nom_village', 'village__fokontany__commune__nom_commune', 'reference_parcelle',
    )[:50]
    return JsonResponse({
        'success': True,
        'parcels': [{
            'id': str(parcel.id),
            'reference': parcel.reference_parcelle,
            'village_id': str(parcel.village_id),
            'village': parcel.village.nom_village,
            'label': _parcelle_location_label(parcel),
        } for parcel in parcels],
    })


@employe_required
@require_http_methods(['POST'])
def gps_quality_point_parcel_update(request):
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données JSON invalides.'}, status=400)
    point_id = payload.get('point_id')
    parcel_id = payload.get('parcel_id')
    ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    point = get_object_or_404(
        PointEau.objects.filter(ouvrage__in=ouvrages).select_related('parcelle__village'), id=point_id,
    )
    parcel = None
    if parcel_id:
        parcel = get_object_or_404(
            Parcelle.objects.select_related('village__fokontany__commune__district'), id=parcel_id,
        )
    if point.parcelle_id != (parcel.id if parcel else None):
        point.parcelle = parcel
        point.save(update_fields=['parcelle'])
        GPSDataQualityReview.objects.filter(entity_type='point_eau', entity_id=point.id).delete()
    return JsonResponse({
        'success': True,
        'message': 'Parcelle du point d’eau mise à jour.',
        'parcel': {'id': str(parcel.id), 'label': _parcelle_location_label(parcel)} if parcel else None,
    })


@employe_required
@require_http_methods(['POST'])
def gps_quality_coordinate_update(request):
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données JSON invalides.'}, status=400)
    entity_type = str(payload.get('entity_type') or '')
    entity_id = payload.get('entity_id')
    action = str(payload.get('action') or 'set')
    if entity_type not in {'point_eau', 'equipement'} or action not in {'set', 'clear'}:
        return JsonResponse({'success': False, 'error': 'Action GPS invalide.'}, status=400)
    ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    model = PointEau if entity_type == 'point_eau' else EquipementConstitutif
    entity = get_object_or_404(model.objects.filter(ouvrage__in=ouvrages), id=entity_id)
    if action == 'clear':
        latitude = longitude = None
    else:
        try:
            latitude = float(str(payload.get('latitude')).replace(',', '.'))
            longitude = float(str(payload.get('longitude')).replace(',', '.'))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Latitude ou longitude invalide.'}, status=400)
        if not _valid_coordinates(latitude, longitude):
            return JsonResponse({'success': False, 'error': 'Coordonnées invalides ou égales à 0, 0.'}, status=400)
    entity.latitude = latitude
    entity.longitude = longitude
    entity.save(update_fields=['latitude', 'longitude'])
    return JsonResponse({
        'success': True,
        'message': 'Coordonnées effacées.' if action == 'clear' else 'Coordonnées enregistrées.',
        'entity': {
            'id': str(entity.id), 'entity_type': entity_type,
            'latitude': latitude, 'longitude': longitude,
        },
    })
