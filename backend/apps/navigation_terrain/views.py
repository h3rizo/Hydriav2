import base64
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation

from django.core import signing
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.billing.models import PointEau
from apps.core.views_mobile_auth import mobile_auth_required
from apps.geography.models import Village
from apps.infrastructure.models import EquipementConstitutif
from apps.organization.models import Organisation, Ouvrage
from apps.planning.views_reparations_apis import _get_scoped_ouvrage_ids_for_request

from .models import GeoPositionAudit, Repere, ReperePhoto, TypeRepere


def _payload(request):
    if request.content_type and 'application/json' in request.content_type:
        try:
            return json.loads(request.body.decode('utf-8') or '{}')
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    return request.POST.dict()


def _bool(value):
    return str(value).strip().lower() in {'1', 'true', 'yes', 'oui', 'on'}


def _decimal(payload, key, required=False):
    value = payload.get(key)
    if value in (None, ''):
        if required:
            raise ValueError(key)
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(key)


def _datetime(value):
    parsed = parse_datetime(str(value or ''))
    if parsed is None:
        raise ValueError('captured_at')
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def _scope(request):
    organisation_id, ouvrage_ids = _get_scoped_ouvrage_ids_for_request(request)

    # The repairs scope uses the sentinel ``all`` when an administrator can
    # access every organisation.  Navigation models use UUID foreign keys, so
    # passing that sentinel to an ``organisation_id`` lookup raises a
    # ValidationError and turns the entities endpoint into an HTTP 500.
    raw_organisation_id = str(organisation_id or '').strip()
    if not raw_organisation_id or raw_organisation_id.lower() == 'all':
        normalised_organisation_id = None
    else:
        try:
            normalised_organisation_id = str(uuid.UUID(raw_organisation_id))
        except (ValueError, TypeError, AttributeError):
            normalised_organisation_id = None

    normalised_ouvrage_ids = set()
    for value in ouvrage_ids or ():
        try:
            normalised_ouvrage_ids.add(str(uuid.UUID(str(value))))
        except (ValueError, TypeError, AttributeError):
            continue

    return normalised_organisation_id, normalised_ouvrage_ids


def _allowed_village_ids(ouvrage_ids):
    return PointEau.objects.filter(ouvrage_id__in=ouvrage_ids, parcelle_id__isnull=False).values_list(
        'parcelle__village_id', flat=True
    ).distinct()


def _repere_scope(user, organisation_id, ouvrage_ids):
    query = Q(createur=user) | Q(ouvrage_id__in=ouvrage_ids)
    if organisation_id:
        query |= Q(organisation_id=organisation_id)
    return Repere.objects.filter(query).distinct()


def _iso(value):
    return value.isoformat() if value else None


def _serialize_repair_type(value):
    return {'id': str(value.id), 'nom': value.nom, 'description': value.description, 'icone': value.icone,
            'couleur': value.couleur, 'ordre_affichage': value.ordre_affichage, 'actif': value.actif,
            'updated_at': _iso(value.updated_at)}


def _serialize_repere(value):
    return {'id': str(value.id), 'nom': value.nom, 'type_repere_id': str(value.type_repere_id),
            'type': value.type_repere.nom, 'code': value.type_repere.icone, 'latitude': float(value.latitude),
            'longitude': float(value.longitude), 'altitude': float(value.altitude) if value.altitude is not None else None,
            'accuracy_m': float(value.accuracy_m) if value.accuracy_m is not None else None,
            'marker_category': value.marker_category, 'is_field_marker': True,
            'ouvrage_id': str(value.ouvrage_id or ''), 'village_id': str(value.village_id or ''),
            'version': value.version, 'archived': bool(value.archived_at), 'updated_at': _iso(value.updated_at)}


@mobile_auth_required
@require_http_methods(['GET'])
def api_config(request):
    employe = getattr(request.user, 'employe', None)
    writable = bool(employe or request.user.is_staff)
    return JsonResponse({'success': True, 'config': {
        'arrival_radius_m': 25, 'accuracy_warning_m': 30, 'max_edge_indicators': 6,
        'permissions': {'modify_positions': writable, 'create_landmarks': writable, 'archive_landmarks': writable},
        'map': {'offline_neutral_style': True, 'style_url': None, 'offline_download_enabled': False},
    }})


@mobile_auth_required
@require_http_methods(['GET'])
def api_entities(request):
    try:
        limit = max(1, min(int(request.GET.get('limit', 500)), 500))
    except ValueError:
        limit = 500
    offset = 0
    cursor = request.GET.get('cursor', '')
    if cursor:
        try:
            cursor_data = signing.loads(cursor, salt='navigation-terrain-cursor', max_age=90 * 86400)
            offset = max(0, int(cursor_data.get('offset', 0)))
        except (signing.BadSignature, ValueError, TypeError):
            offset = 0

    # La carte terrain est un referentiel geographique transversal : une fois
    # authentifie, l'utilisateur doit pouvoir voir les villages et ouvrages
    # proches meme lorsqu'ils sont geres par une autre organisation.
    points = PointEau.objects.all().select_related('type_point_eau', 'parcelle__village')
    equipments = EquipementConstitutif.objects.all().select_related('type_equipement')
    villages = Village.objects.filter(latitude__isnull=False, longitude__isnull=False)
    reperes = Repere.objects.filter(archived_at__isnull=True).select_related('type_repere')

    rows = []
    rows += [('village', str(v.id), {'id': str(v.id), 'nom': v.nom_village, 'latitude': float(v.latitude),
              'longitude': float(v.longitude), 'altitude': float(v.altitude) if v.altitude is not None else None}) for v in villages]
    rows += [('water_point', str(v.id), {'id': str(v.id), 'nom': v.nomabonne, 'code': v.code_point_eau or '',
              'type': v.type_point_eau.nom_type if v.type_point_eau else '', 'ouvrage_id': str(v.ouvrage_id or ''),
              'latitude': v.latitude, 'longitude': v.longitude,
              'reference_latitude': getattr(getattr(getattr(v, 'parcelle', None), 'village', None), 'latitude', None),
              'reference_longitude': getattr(getattr(getattr(v, 'parcelle', None), 'village', None), 'longitude', None),
              'village': getattr(getattr(getattr(v, 'parcelle', None), 'village', None), 'nom_village', ''),
              'updated_at': _iso(v.updatedat)}) for v in points]
    rows += [('equipment', str(v.id), {'id': str(v.id), 'nom': v.nom, 'code': v.code_equipement or '',
              'type': str(v.type_equipement or ''), 'ouvrage_id': str(v.ouvrage_id or ''),
              'latitude': float(v.latitude) if v.latitude is not None else None,
              'longitude': float(v.longitude) if v.longitude is not None else None,
              'reference_latitude': v.latitude, 'reference_longitude': v.longitude,
              'updated_at': _iso(getattr(v, 'updated_at', None))}) for v in equipments]
    rows += [('landmark', str(v.id), _serialize_repere(v)) for v in reperes]
    rows.sort(key=lambda item: (item[0], item[1]))
    page = rows[offset:offset + limit]
    grouped = {'villages': [], 'points_eau': [], 'equipements': [], 'reperes': []}
    names = {'village': 'villages', 'water_point': 'points_eau', 'equipment': 'equipements', 'landmark': 'reperes'}
    for kind, _, value in page:
        grouped[names[kind]].append(value)
    if offset == 0:
        grouped['types_reperes'] = [_serialize_repair_type(v) for v in TypeRepere.objects.filter(actif=True)]
    has_more = offset + len(page) < len(rows)
    next_cursor = signing.dumps({'offset': offset + len(page)}, salt='navigation-terrain-cursor') if has_more else ''
    sync_cursor = signing.dumps({'completed_at': timezone.now().isoformat()}, salt='navigation-terrain-cursor')
    return JsonResponse({'success': True, 'data': {'entities': grouped, 'deletions': [],
        'next_cursor': next_cursor, 'cursor': sync_cursor, 'has_more': has_more, 'count': len(page)}})


def _entity_for_update(kind, entity_id, user, organisation_id, ouvrage_ids):
    if kind == 'water_point':
        return PointEau.objects.select_for_update().filter(id=entity_id).first()
    if kind == 'equipment':
        return EquipementConstitutif.objects.select_for_update().filter(id=entity_id).first()
    if kind == 'village':
        return Village.objects.select_for_update().filter(id=entity_id).first()
    if kind == 'landmark':
        return Repere.objects.select_for_update().filter(id=entity_id).first()
    return None


def _server_position(kind, entity):
    return {'entity_kind': kind, 'entity_id': str(entity.pk), 'latitude': float(entity.latitude),
            'longitude': float(entity.longitude), 'altitude': float(getattr(entity, 'altitude', 0) or 0),
            'server_updated_at': _iso(getattr(entity, 'updated_at', None) or getattr(entity, 'updatedat', None)),
            'version': getattr(entity, 'version', None)}


@csrf_exempt
@mobile_auth_required
@require_http_methods(['POST'])
def api_position_upsert(request):
    payload = _payload(request)
    if payload is None:
        return JsonResponse({'success': False, 'error': 'Corps invalide'}, status=400)
    try:
        local_uuid = uuid.UUID(str(payload.get('local_uuid')))
        latitude, longitude = _decimal(payload, 'latitude', True), _decimal(payload, 'longitude', True)
        altitude, accuracy = _decimal(payload, 'altitude'), _decimal(payload, 'accuracy_m')
        captured_at = _datetime(payload.get('captured_at'))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Coordonnées ou identifiant invalides'}, status=422)
    if not Decimal('-90') <= latitude <= Decimal('90') or not Decimal('-180') <= longitude <= Decimal('180'):
        return JsonResponse({'success': False, 'error': 'Coordonnées hors limites'}, status=422)
    existing_audit = GeoPositionAudit.objects.filter(local_uuid=local_uuid).first()
    if existing_audit:
        return JsonResponse({'success': True, 'duplicate_prevented': True, 'audit_id': str(existing_audit.id)})

    kind, entity_id = str(payload.get('entity_kind') or ''), payload.get('entity_id')
    organisation_id, ouvrage_ids = _scope(request)
    with transaction.atomic():
        entity = _entity_for_update(kind, entity_id, request.user, organisation_id, ouvrage_ids)
        if not entity:
            return JsonResponse({'success': False, 'error': 'Entité introuvable ou hors périmètre'}, status=404)
        server_updated = getattr(entity, 'updated_at', None) or getattr(entity, 'updatedat', None)
        base_updated = parse_datetime(str(payload.get('base_updated_at') or ''))
        if base_updated and timezone.is_naive(base_updated):
            base_updated = timezone.make_aware(base_updated)
        if server_updated and base_updated and server_updated > base_updated and not _bool(payload.get('force_sync')):
            return JsonResponse({'success': False, 'conflict': True, 'error': 'Coordonnées modifiées sur le serveur',
                                 'server_value': _server_position(kind, entity)}, status=409)
        old_lat, old_lon, old_alt = entity.latitude, entity.longitude, getattr(entity, 'altitude', None)
        entity.latitude, entity.longitude = latitude, longitude
        fields = ['latitude', 'longitude']
        if hasattr(entity, 'altitude'):
            entity.altitude = altitude
            fields.append('altitude')
        if kind == 'landmark':
            entity.accuracy_m = accuracy
            entity.version += 1
            fields += ['accuracy_m', 'version', 'updated_at']
        elif hasattr(entity, 'updatedat'):
            entity.updatedat = timezone.now()
            fields.append('updatedat')
        elif hasattr(entity, 'updated_at'):
            fields.append('updated_at')
        entity.save(update_fields=list(dict.fromkeys(fields)))
        audit = GeoPositionAudit.objects.create(local_uuid=local_uuid, entity_kind=kind, entity_uuid=entity.pk,
            old_latitude=old_lat, old_longitude=old_lon, old_altitude=old_alt, new_latitude=latitude,
            new_longitude=longitude, new_altitude=altitude, accuracy_m=accuracy,
            capture_method=str(payload.get('capture_method') or 'gps'), captured_at=captured_at,
            utilisateur=request.user, appareil=request.headers.get('User-Agent', '')[:160])
    return JsonResponse({'success': True, 'id': str(entity.pk), 'audit_id': str(audit.id),
                         'server_value': _server_position(kind, entity)})


def _resolve_type(value):
    try:
        return TypeRepere.objects.filter(id=uuid.UUID(str(value)), actif=True).first()
    except (ValueError, TypeError, AttributeError):
        return TypeRepere.objects.filter(icone=str(value), actif=True).first()


@csrf_exempt
@mobile_auth_required
@require_http_methods(['POST'])
def api_repere_upsert(request):
    payload = _payload(request)
    if payload is None:
        return JsonResponse({'success': False, 'error': 'Corps invalide'}, status=400)
    try:
        repere_id = uuid.UUID(str(payload.get('id') or payload.get('local_uuid')))
        latitude, longitude = _decimal(payload, 'latitude', True), _decimal(payload, 'longitude', True)
        altitude, accuracy = _decimal(payload, 'altitude'), _decimal(payload, 'accuracy_m')
        captured_at = _datetime(payload.get('captured_at'))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Repère invalide'}, status=422)
    marker_category = str(payload.get('marker_category') or 'landmark').strip()
    if marker_category not in {'landmark', 'water_point', 'equipment'}:
        return JsonResponse({'success': False, 'error': 'Categorie de marquage invalide'}, status=422)
    type_repere = _resolve_type(payload.get('type_repere_id'))
    if not type_repere:
        return JsonResponse({'success': False, 'error': 'Type de repère invalide'}, status=422)
    organisation_id, ouvrage_ids = _scope(request)
    ouvrage_id = str(payload.get('ouvrage_id') or '')
    if ouvrage_id and ouvrage_id not in ouvrage_ids:
        return JsonResponse({'success': False, 'error': 'Ouvrage hors périmètre'}, status=403)
    with transaction.atomic():
        repere = Repere.objects.select_for_update().filter(id=repere_id).first()
        created = repere is None
        if repere and not _repere_scope(request.user, organisation_id, ouvrage_ids).filter(id=repere.id).exists():
            return JsonResponse({'success': False, 'error': 'Repère hors périmètre'}, status=404)
        try:
            base_version = int(payload['base_version']) if payload.get('base_version') not in (None, '') else None
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Version locale invalide'}, status=422)
        if repere and base_version is not None and base_version != repere.version and not _bool(payload.get('force_sync')):
            return JsonResponse({'success': False, 'conflict': True, 'error': 'Repère modifié sur le serveur',
                                 'server_value': _serialize_repere(repere)}, status=409)
        proposed_name = str(payload.get('nom') or 'Repère')[:255]
        if repere and all((
            repere.nom == proposed_name, repere.marker_category == marker_category,
            repere.type_repere_id == type_repere.id,
            repere.latitude == latitude, repere.longitude == longitude,
            repere.altitude == altitude, repere.accuracy_m == accuracy,
            repere.capture_method == str(payload.get('capture_method') or 'gps'),
            repere.captured_at == captured_at,
        )):
            return JsonResponse({'success': True, 'duplicate_prevented': True, 'id': str(repere.id),
                                 'server_value': _serialize_repere(repere)})
        if created:
            repere = Repere(id=repere_id, createur=request.user)
        repere.nom = proposed_name
        repere.marker_category = marker_category
        repere.type_repere, repere.latitude, repere.longitude = type_repere, latitude, longitude
        repere.altitude, repere.accuracy_m = altitude, accuracy
        repere.remarques = str(payload.get('remarques') or '')
        repere.capture_method = str(payload.get('capture_method') or 'gps')
        repere.captured_at, repere.ouvrage_id = captured_at, ouvrage_id or None
        repere.organisation_id = organisation_id if organisation_id and Organisation.objects.filter(id=organisation_id).exists() else None
        if not created:
            repere.version += 1
        repere.save()
    return JsonResponse({'success': True, 'created': created, 'id': str(repere.id), 'server_value': _serialize_repere(repere)}, status=201 if created else 200)


@csrf_exempt
@mobile_auth_required
@require_http_methods(['POST'])
def api_repere_archive(request, repere_id):
    organisation_id, ouvrage_ids = _scope(request)
    with transaction.atomic():
        repere = _repere_scope(request.user, organisation_id, ouvrage_ids).select_for_update().filter(id=repere_id).first()
        if not repere:
            return JsonResponse({'success': False, 'error': 'Repère introuvable ou hors périmètre'}, status=404)
        if not repere.archived_at:
            repere.archived_at, repere.version = timezone.now(), repere.version + 1
            repere.save(update_fields=['archived_at', 'version', 'updated_at'])
    return JsonResponse({'success': True, 'id': str(repere.id), 'archived': True, 'version': repere.version})


@csrf_exempt
@mobile_auth_required
@require_http_methods(['POST'])
def api_repere_photo(request, repere_id):
    payload = _payload(request)
    organisation_id, ouvrage_ids = _scope(request)
    repere = _repere_scope(request.user, organisation_id, ouvrage_ids).filter(id=repere_id, archived_at__isnull=True).first()
    if not repere:
        return JsonResponse({'success': False, 'error': 'Repère introuvable ou hors périmètre'}, status=404)
    try:
        local_uuid = uuid.UUID(str(payload.get('local_uuid')))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'UUID photo invalide'}, status=422)
    existing = ReperePhoto.objects.filter(local_uuid=local_uuid).first()
    if existing:
        return JsonResponse({'success': True, 'duplicate_prevented': True, 'id': str(existing.id)})
    raw = str(payload.get('photo_data') or '')
    if raw.startswith('data:'):
        raw = raw.split(',', 1)[-1]
    try:
        content = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Photo invalide'}, status=422)
    if not content or len(content) > 5 * 1024 * 1024:
        return JsonResponse({'success': False, 'error': 'La photo doit faire moins de 5 Mo'}, status=422)
    name = str(payload.get('filename') or 'repere-terrain.jpg')[:180]
    photo = ReperePhoto(local_uuid=local_uuid, repere=repere, nom=name,
        mime_type=str(payload.get('content_type') or 'image/jpeg')[:80], taille=len(content),
        sha256=hashlib.sha256(content).hexdigest(), createur=request.user)
    photo.fichier.save(name, ContentFile(content), save=True)
    return JsonResponse({'success': True, 'created': True, 'id': str(photo.id)}, status=201)


@mobile_auth_required
@require_http_methods(['GET'])
def api_itineraire(request):
    """Itinéraire routier entre deux positions GPS (position de l'agent -> entité de la carte).

    ?from_lat=&from_lon=&to_lat=&to_lon=&profil=moto|voiture|pied&critere=temps|distance
    Chaque extrémité est ramenée à la route praticable la plus proche ; la marche jusqu'à la route est
    comptée (4 km/h) et signalée dans `acces_depart_m` / `acces_arrivee_m`.
    """
    from apps.geography.services import itineraire as it
    from apps.geography.services import lieux
    from apps.geography.services.reseau_routier import haversine_m

    try:
        lat1, lon1 = float(request.GET['from_lat']), float(request.GET['from_lon'])
        lat2, lon2 = float(request.GET['to_lat']), float(request.GET['to_lon'])
    except (KeyError, ValueError):
        return JsonResponse({'success': False, 'error': 'from_lat, from_lon, to_lat, to_lon requis.'}, status=400)
    critere = request.GET.get('critere', 'temps')
    profil = request.GET.get('profil', it.PROFIL_DEFAUT)
    if critere not in it.CRITERES or profil not in it.PROFILS_VALIDES:
        return JsonResponse({'success': False, 'error': 'critere ou profil invalide.'}, status=400)
    try:
        a = lieux.acces_point(lon1, lat1, nom='Départ')
        b = lieux.acces_point(lon2, lat2, nom='Arrivée')
        r = it.reseau().itineraire(a, b, critere, profil)
    except it.ItineraireIntrouvable as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=404)

    vol_m = haversine_m(lon1, lat1, lon2, lat2)
    return JsonResponse({
        'success': True, 'critere': critere, 'profil': profil,
        'distance_km': round(r['distance_m'] / 1000, 2),
        'duree_minutes': round(r['duree_s'] / 60),
        'distance_vol_oiseau_km': round(vol_m / 1000, 2),
        'detour': round(r['distance_m'] / vol_m, 2) if vol_m else None,
        'marche_m': round(r['marche_m']),
        'acces_depart_m': round(a['distance_m']), 'acces_arrivee_m': round(b['distance_m']),
        'repartition_km': {k: round(v / 1000, 2) for k, v in r['repartition_m'].items()},
        'geometrie': {'type': 'LineString', 'coordinates': r['geometrie']},
    })
