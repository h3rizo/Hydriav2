"""Page et API du tracé libre (relier au réseau un village éloigné de toute route)."""
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .services import trace_libre as svc
from .services import edition_carte as edition
from .services import villages_carte as villages
from .views_coupures import _json_staff, _staff


@login_required
@_staff
def page_trace_libre(request):
    return render(request, 'geography/trace_libre.html')


def _nombre(request, cle, defaut, mini, maxi):
    try:
        return min(max(float(request.GET.get(cle, defaut)), mini), maxi)
    except ValueError:
        return None


@require_GET
@_json_staff
def api_trace_libre_liste(request):
    seuil = _nombre(request, 'seuil_m', 1000, 50, 20000)
    if seuil is None:
        return JsonResponse({'success': False, 'error': 'Paramètres invalides.'}, status=400)
    data = svc.villages_a_tracer(seuil, request.GET.get('q', '').strip()[:60])
    return JsonResponse({'success': True, **data})


@require_GET
@_json_staff
def api_trace_libre_contexte(request):
    lon, lat = _nombre(request, 'lon', 0, 40, 55), _nombre(request, 'lat', 0, -30, -10)
    marge = _nombre(request, 'marge', 0.03, 0.005, 0.08)
    if None in (lon, lat, marge) or 'lon' not in request.GET or 'lat' not in request.GET:
        return JsonResponse({'success': False, 'error': 'lon et lat requis.'}, status=400)
    return JsonResponse({'success': True, **svc.contexte(lon, lat, marge)})


@require_POST
@_json_staff
def api_trace_libre_creer(request):
    try:
        d = json.loads(request.body or '{}')
        fin = d['fin']
        waypoints = [(float(x), float(y)) for x, y in d.get('waypoints', [])]
        r = svc.tracer(d['village_id'], waypoints, float(fin[0]), float(fin[1]), d.get('categorie', 'sentier'))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide.'}, status=400)
    except svc.TraceInvalide as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    t = r['troncon']
    return JsonResponse({'success': True, 'longueur_m': round(t.longueur_m),
                         'reseau_principal': r['reseau_principal'], 'voisins_rattaches': r['voisins_rattaches']})


@require_POST
@_json_staff
def api_trace_libre_ligne(request):
    """Enregistre une route dessinée librement : {"points": [[lon, lat], ...], "categorie": "piste", "nom": ""}."""
    try:
        d = json.loads(request.body or '{}')
        points = d['points']
        if not isinstance(points, list):
            raise TypeError
        r = svc.tracer_ligne(points, d.get('categorie', 'piste'), str(d.get('nom', '')).strip())
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide.'}, status=400)
    except svc.TraceInvalide as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    return JsonResponse({'success': True, 'longueur_m': round(r['longueur_m']), 'nb_troncons': len(r['troncons']),
                         'jonctions': r['jonctions'], 'relie_reseau_principal': r['relie_reseau_principal'],
                         'voisins_rattaches': r['voisins_rattaches']})


# --- Création d'un village en cliquant sur la carte --------------------------------------------------------------------

@require_GET
@_json_staff
def api_village_lieu(request):
    """Hiérarchie administrative (région > district > commune > fokontany) d'un point : ?lon=&lat="""
    lon, lat = _nombre(request, 'lon', 0, 40, 55), _nombre(request, 'lat', 0, -30, -10)
    if None in (lon, lat) or 'lon' not in request.GET or 'lat' not in request.GET:
        return JsonResponse({'success': False, 'error': 'lon et lat requis.'}, status=400)
    return JsonResponse({'success': True, 'lieu': villages.lieu_du_point(lon, lat)})


@require_GET
@_json_staff
def api_village_liste(request):
    """Listes en cascade : ?niveau=region|district|commune|fokontany&parent=<id du niveau supérieur>"""
    niveau = request.GET.get('niveau', '')
    try:
        items = villages.lister(niveau, request.GET.get('parent') or None)
    except (villages.VillageInvalide, ValidationError, ValueError):
        return JsonResponse({'success': False, 'error': 'Paramètres invalides.'}, status=400)
    return JsonResponse({'success': True, 'items': items})


@require_POST
@_json_staff
def api_village_creer(request):
    """Crée un village : {"nom", "fokontany_id", "lon", "lat", "confirmer_proches": false}"""
    try:
        d = json.loads(request.body or '{}')
        lon, lat = float(d['lon']), float(d['lat'])
        r = villages.creer_village(d.get('nom', ''), d.get('fokontany_id') or None, lon, lat, bool(d.get('confirmer_proches')))
    except (KeyError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide.'}, status=400)
    except villages.VillageProche as exc:
        return JsonResponse({'success': False, 'confirmation_requise': True, 'proches': exc.proches,
                             'error': 'Des villages existent déjà à moins de 100 m.'}, status=409)
    except villages.VillageInvalide as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    v = r['village']
    return JsonResponse({'success': True, 'id': str(v.id), 'nom': v.nom_village,
                         'url': reverse('geography:village_detail', args=[v.pk]),
                         'fokontany': v.fokontany.nom_fokontany, 'commune': v.fokontany.commune.nom_commune,
                         'distance_route_m': r['distance_route_m']})


# --- Recherche et édition (villages, tronçons) -------------------------------------------------------------------------

def _corps(request):
    d = json.loads(request.body or '{}')
    if not isinstance(d, dict):
        raise TypeError
    return d


@require_GET
@_json_staff
def api_village_recherche(request):
    """Recherche de village par nom : ?q="""
    return JsonResponse({'success': True, 'items': edition.rechercher_villages(request.GET.get('q', ''))})


@require_GET
@_json_staff
def api_villages_zone(request):
    """Villages d'une zone : ?bbox=ouest,sud,est,nord"""
    try:
        ouest, sud, est, nord = [float(x) for x in request.GET.get('bbox', '').split(',')]
    except ValueError:
        return JsonResponse({'success': False, 'error': 'bbox invalide.'}, status=400)
    if est - ouest > 2 or nord - sud > 2:
        return JsonResponse({'success': False, 'error': 'Zone trop grande : zoome.'}, status=400)
    items, tronque = edition.villages_zone(ouest, sud, est, nord)
    return JsonResponse({'success': True, 'items': items, 'tronque': tronque})


@require_GET
@_json_staff
def api_village_detail(request, village_id):
    try:
        return JsonResponse({'success': True, 'village': edition.detail_village(village_id)})
    except edition.EditionInvalide as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=404)


@require_POST
@_json_staff
def api_village_modifier(request, village_id):
    """{"nom", "fokontany_id", "lon", "lat", "confirmer_proches"}"""
    try:
        d = _corps(request)
        r = edition.modifier_village(village_id, d.get('nom', ''), d.get('fokontany_id') or None,
                                     float(d['lon']), float(d['lat']), bool(d.get('confirmer_proches')))
    except (KeyError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide.'}, status=400)
    except edition.EditionInvalide as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=404)
    except villages.VillageProche as exc:
        return JsonResponse({'success': False, 'confirmation_requise': True, 'proches': exc.proches,
                             'error': 'Des villages existent déjà à moins de 100 m.'}, status=409)
    except villages.VillageInvalide as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    v = r['village']
    return JsonResponse({'success': True, 'id': str(v.id), 'nom': v.nom_village, 'deplace': r['deplace'],
                         'distance_route_m': r['distance_route_m']})


@require_GET
@_json_staff
def api_troncon_detail(request, troncon_id):
    try:
        return JsonResponse({'success': True, 'troncon': edition.detail_troncon(troncon_id)})
    except (edition.EditionInvalide, ValidationError):
        return JsonResponse({'success': False, 'error': 'Tronçon introuvable.'}, status=404)


@require_POST
@_json_staff
def api_troncon_modifier(request, troncon_id):
    """{"points": [[lon, lat], ...], "categorie": "piste", "nom": ""}"""
    try:
        d = _corps(request)
        r = edition.modifier_troncon(troncon_id, d['points'], d.get('categorie'), d.get('nom'))
    except (KeyError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide.'}, status=400)
    except edition.EditionInvalide as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    t = r['troncon']
    return JsonResponse({'success': True, 'longueur_m': round(t.longueur_m), 'troncons_touches': r['troncons_touches']})
