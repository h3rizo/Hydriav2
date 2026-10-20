"""API JSON pour gerer les liaisons entre villages depuis les cartes (creation, edition, suppression)."""
import json
import math
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import LiaisonVillage, Village
from .services.liaisons_routes import calculer_une


def air_distance_km(lat1, lon1, lat2, lon2):
    """Distance a vol d'oiseau (haversine) en km, ou None si un point n'a pas de GPS."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


def liaison_properties(liaison):
    """Proprietes JSON d'une liaison (partagees par le GeoJSON et les reponses d'API)."""
    source, cible = liaison.village_source, liaison.village_cible
    return {
        'id': str(liaison.id),
        'type_liaison': liaison.type_liaison,
        'type_liaison_display': liaison.get_type_liaison_display(),
        'type_route': liaison.type_route,
        'type_route_display': liaison.get_type_route_display() if liaison.type_route else None,
        'moyen_acces': liaison.moyen_acces,
        'moyen_acces_display': liaison.get_moyen_acces_display() if liaison.moyen_acces else None,
        'distance_km': float(liaison.distance_km) if liaison.distance_km is not None else None,
        'distance_vol_oiseau_km': air_distance_km(source.latitude, source.longitude, cible.latitude, cible.longitude),
        'temps_acces_minutes': liaison.temps_acces_minutes,
        'distance_route_km': liaison.distance_route_km,
        'duree_route_min': liaison.duree_route_min,
        'route_statut': liaison.route_statut,
        'ordre': liaison.ordre,
        'source_id': str(liaison.village_source_id),
        'source_nom': source.nom_village,
        'source_commune': source.commune.nom_commune if source.fokontany_id else None,
        'cible_id': str(liaison.village_cible_id),
        'cible_nom': cible.nom_village,
        'cible_commune': cible.commune.nom_commune if cible.fokontany_id else None,
    }


def liaison_coordinates(liaison):
    """Courbe réelle (par la route) si elle est calculée, sinon ligne droite entre les deux villages."""
    if liaison.route_statut == 'ok' and liaison.trace_route:
        return liaison.trace_route
    source, cible = liaison.village_source, liaison.village_cible
    return [[float(source.longitude), float(source.latitude)], [float(cible.longitude), float(cible.latitude)]]


def liaison_feature(liaison):
    return {
        'type': 'Feature',
        'properties': liaison_properties(liaison),
        'geometry': {
            'type': 'LineString',
            'coordinates': liaison_coordinates(liaison),
        },
    }


def _json_auth(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'error': 'Authentification requise.'}, status=401)
        return view(request, *args, **kwargs)
    return wrapper


def _payload(request):
    if request.content_type == 'application/json':
        try:
            return json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return {}
    return request.POST


class _Invalid(Exception):
    pass


def _clean_fields(data, partial_from=None):
    """Valide les champs communs. `partial_from` : liaison existante dont on conserve les valeurs absentes."""
    def get(key, default):
        if key in data:
            return data.get(key)
        return default

    base = partial_from
    type_liaison = str(get('type_liaison', base.type_liaison if base else 'desserte') or 'desserte').strip().lower()
    if type_liaison not in {c[0] for c in LiaisonVillage.TYPE_LIAISON_CHOICES}:
        raise _Invalid('Type de liaison invalide.')

    type_route = str(get('type_route', base.type_route if base else '') or '').strip().lower() or None
    if type_route and type_route not in {c[0] for c in LiaisonVillage.TYPE_ROUTE_CHOICES}:
        raise _Invalid('Type de route invalide.')

    moyen = str(get('moyen_acces', base.moyen_acces if base else '') or '').strip().lower() or None
    if moyen and moyen not in {c[0] for c in LiaisonVillage.MOYEN_ACCES_CHOICES}:
        raise _Invalid("Moyen d'acces invalide.")

    raw_distance = get('distance_km', base.distance_km if base else None)
    distance = None
    if raw_distance not in (None, ''):
        try:
            distance = Decimal(str(raw_distance).replace(',', '.')).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            raise _Invalid('Distance invalide.')
        if distance < 0 or distance > Decimal('999999.99'):
            raise _Invalid('Distance hors limites.')

    raw_temps = get('temps_acces_minutes', base.temps_acces_minutes if base else None)
    temps = None
    if raw_temps not in (None, ''):
        try:
            temps = int(raw_temps)
        except (TypeError, ValueError):
            raise _Invalid("Temps d'acces invalide.")
        if temps < 0:
            raise _Invalid("Le temps d'acces ne peut pas etre negatif.")

    raw_ordre = get('ordre', base.ordre if base else 0)
    try:
        ordre = max(0, int(raw_ordre or 0))
    except (TypeError, ValueError):
        raise _Invalid('Ordre invalide.')

    return {
        'type_liaison': type_liaison,
        'type_route': type_route,
        'moyen_acces': moyen,
        'distance_km': distance,
        'temps_acces_minutes': temps,
        'ordre': ordre,
    }


def _error(message, status=400):
    return JsonResponse({'success': False, 'error': message}, status=status)


@_json_auth
@require_http_methods(['POST'])
def api_liaison_create(request):
    data = _payload(request)
    source = get_object_or_404(Village, pk=data.get('source_id'))
    cible = get_object_or_404(Village, pk=data.get('cible_id'))
    if source.pk == cible.pk:
        return _error('Un village ne peut pas etre relie a lui-meme.')
    try:
        fields = _clean_fields(data)
    except _Invalid as exc:
        return _error(str(exc))

    if LiaisonVillage.objects.filter(village_source=source, village_cible=cible, type_liaison=fields['type_liaison']).exists():
        return _error('Cette liaison existe deja avec ce type.', status=409)

    try:
        liaison = LiaisonVillage.objects.create(village_source=source, village_cible=cible, **fields)
    except IntegrityError:
        return _error('Cette liaison existe deja avec ce type.', status=409)

    calculer_une(liaison)
    return JsonResponse({'success': True, 'liaison': liaison_properties(liaison), 'trace_route': liaison_coordinates(liaison)}, status=201)


@_json_auth
@require_http_methods(['POST'])
def api_liaison_update(request, liaison_id):
    liaison = get_object_or_404(
        LiaisonVillage.objects.select_related('village_source__fokontany__commune', 'village_cible__fokontany__commune'),
        pk=liaison_id,
    )
    data = _payload(request)
    try:
        fields = _clean_fields(data, partial_from=liaison)
    except _Invalid as exc:
        return _error(str(exc))

    source, cible = liaison.village_source, liaison.village_cible
    if str(data.get('inverser')).lower() in {'1', 'true'}:
        source, cible = cible, source

    if LiaisonVillage.objects.filter(
        village_source=source, village_cible=cible, type_liaison=fields['type_liaison']
    ).exclude(pk=liaison.pk).exists():
        return _error('Une liaison identique existe deja avec ce type.', status=409)

    liaison.village_source, liaison.village_cible = source, cible
    for key, value in fields.items():
        setattr(liaison, key, value)
    liaison.save()
    calculer_une(liaison)
    return JsonResponse({'success': True, 'liaison': liaison_properties(liaison), 'trace_route': liaison_coordinates(liaison)})


@_json_auth
@require_http_methods(['POST'])
def api_liaison_delete(request, liaison_id):
    liaison = get_object_or_404(LiaisonVillage, pk=liaison_id)
    liaison.delete()
    return JsonResponse({'success': True, 'id': str(liaison_id)})
