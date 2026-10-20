"""Page et API de réparation des coupures du réseau routier."""
import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .services import coupures as svc
from .services.reseau_routier import haversine_m

_staff = user_passes_test(lambda u: u.is_active and (u.is_staff or u.is_superuser))


def _json_staff(view):
    def wrapper(request, *args, **kwargs):
        u = request.user
        if not u.is_authenticated:
            return JsonResponse({'success': False, 'error': 'Authentification requise.'}, status=401)
        if not (u.is_staff or u.is_superuser):
            return JsonResponse({'success': False, 'error': 'Accès réservé aux administrateurs.'}, status=403)
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


@login_required
@_staff
def page_coupures(request):
    return render(request, 'geography/coupures_routes.html')


@require_GET
@_json_staff
def api_coupures_liste(request):
    return JsonResponse({'success': True, 'coupures': svc.lister_coupures()})


@require_GET
@_json_staff
def api_coupure_detail(request, cid):
    data = svc.detail_coupure(cid)
    if data is None:
        return JsonResponse({'success': False, 'error': 'Coupure introuvable (déjà raccordée ?).'}, status=404)
    return JsonResponse({'success': True, **data})


@require_POST
@_json_staff
def api_coupure_raccorder(request):
    try:
        d = json.loads(request.body or '{}')
        fin = d['fin']
        waypoints = [(float(x), float(y)) for x, y in d.get('waypoints', [])]
        t = svc.raccorder(d['from_noeud_id'], waypoints, float(fin[0]), float(fin[1]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide.'}, status=400)
    except svc.RaccordInvalide as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    return JsonResponse({'success': True, 'troncon_id': str(t.id), 'longueur_m': round(t.longueur_m)})


@require_GET
def api_itineraire(request):
    """Itinéraire routier entre deux villages : ?depart=<uuid>&arrivee=<uuid>&critere=temps|distance&profil=moto|voiture|pied"""
    from .services import itineraire as it

    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentification requise.'}, status=401)
    depart, arrivee = request.GET.get('depart'), request.GET.get('arrivee')
    critere = request.GET.get('critere', 'temps')
    profil = request.GET.get('profil', it.PROFIL_DEFAUT)
    if not depart or not arrivee or critere not in it.CRITERES or profil not in it.PROFILS_VALIDES:
        return JsonResponse({'success': False, 'error': 'Paramètres depart, arrivee (et critere) requis.'}, status=400)
    try:
        r = it.itineraire_villages(depart, arrivee, critere, profil)
    except ValidationError:
        return JsonResponse({'success': False, 'error': 'Identifiant de village invalide.'}, status=400)
    except it.ItineraireIntrouvable as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=404)

    g = r['geometrie']
    vol_m = haversine_m(g[0][0], g[0][1], g[-1][0], g[-1][1])
    return JsonResponse({
        'success': True,
        'depart': r['depart'], 'arrivee': r['arrivee'], 'critere': critere, 'profil': profil,
        'distance_km': round(r['distance_m'] / 1000, 2),
        'duree_minutes': round(r['duree_s'] / 60),
        'distance_vol_oiseau_km': round(vol_m / 1000, 2),
        'detour': round(r['distance_m'] / vol_m, 2) if vol_m else None,
        'marche_m': round(r['marche_m']),
        'repartition_km': {k: round(v / 1000, 2) for k, v in r['repartition_m'].items()},
        'geometrie': {'type': 'LineString', 'coordinates': g},
    })


# --- Jonctions manquantes -------------------------------------------------------------------

@login_required
@_staff
def page_jonctions(request):
    return render(request, 'geography/jonctions_routes.html')


@require_GET
@_json_staff
def api_jonctions_liste(request):
    """Candidats de jonction (1 par zone de ~200 m), du plus proche au plus éloigné."""
    from .services import jonctions as jn
    try:
        rayon = min(max(float(request.GET.get('rayon_m', 250)), 5), 500)
        ecart = min(max(float(request.GET.get('ecart_m', 3000)), 500), 20000)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Paramètres invalides.'}, status=400)
    data = jn.charger()
    vus, sortie = set(), []
    for c in jn.chercher(data, rayon, ecart):
        cellule = (round((c['from'][0] + c['to'][0]) / 2 * 500), round((c['from'][1] + c['to'][1]) / 2 * 500))
        if cellule in vus:
            continue
        vus.add(cellule)
        sortie.append({'noeud_id': str(c['noeud_id']), 'troncon_id': str(c['troncon_id']),
                       'fraction': c['fraction'], 'distance_m': round(c['distance_m']),
                       'from': c['from'], 'to': c['to']})
    return JsonResponse({'success': True, 'total': len(sortie), 'jonctions': sortie[:400]})


@require_GET
@_json_staff
def api_jonctions_contexte(request):
    """Tronçons autour d'un point (~600 m), pour voir le réseau pendant le contrôle."""
    try:
        lon, lat = float(request.GET['lon']), float(request.GET['lat'])
    except (KeyError, ValueError):
        return JsonResponse({'success': False, 'error': 'lon et lat requis.'}, status=400)
    from .services import index_spatial
    ix, positions = index_spatial.dans_boite(lon, lat, 0.006)
    return JsonResponse({'success': True, 'troncons': {
        'type': 'FeatureCollection', 'features': [index_spatial.feature(ix, i) for i in positions]}})


@require_POST
@_json_staff
def api_jonction_relier(request):
    from .services import jonctions as jn
    try:
        d = json.loads(request.body or '{}')
        fraction = float(d['fraction'])
        t = jn.relier(d['noeud_id'], d['troncon_id'], fraction, snap_m=3.0)
    except (KeyError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide.'}, status=400)
    except Exception as exc:  # nœud ou tronçon introuvable (déjà modifié par une validation précédente)
        if exc.__class__.__name__ == 'DoesNotExist':
            return JsonResponse({'success': False, 'error': 'Nœud ou route introuvable : recharge la liste.'}, status=404)
        raise
    return JsonResponse({'success': True, 'longueur_m': round(t.longueur_m) if t else 0})
