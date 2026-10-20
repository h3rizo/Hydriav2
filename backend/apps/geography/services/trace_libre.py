"""Tracé libre : relier au réseau routier un village éloigné de toute route.

L'utilisateur dessine sur le satellite un chemin depuis le village jusqu'au réseau ; il est
enregistré comme tronçon `source='manuel'`. L'arrivée est ramenée sur la route la plus proche
(en préférant le réseau principal) et le tronçon visé est découpé à cet endroit si besoin.
Les villages voisins du nouveau chemin sont rattachés à celui-ci s'il est plus proche que leur route.
"""
from collections import defaultdict

from django.db import transaction
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from apps.geography.models import Village
from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute

from . import index_spatial
from .coupures import _decouper, _graphe, _noeud
from .lieux import dans_madagascar
from .reseau_routier import haversine_m, longueur_geodesique_m

SEUIL_FIN_M = 300.0        # écart max entre le point d'arrivée posé et la route visée
SNAP_NOEUD_M = 3.0         # sous cette distance d'un nœud existant on s'y raccroche sans découper
RECHERCHE_DEG = 0.01       # ~1 km autour de l'arrivée pour chercher la route à viser
CATEGORIES = ('sentier', 'piste', 'route')


class TraceInvalide(Exception):
    pass


def villages_a_tracer(seuil_m=1000.0, recherche='', limite=600):
    """Villages dont la route la plus proche est à plus de `seuil_m` (les plus éloignés d'abord)."""
    q = (VillageAccesRoute.objects.filter(distance_m__gt=seuil_m)
         .select_related('village__fokontany__commune').order_by('-distance_m'))
    if recherche:
        q = q.filter(village__nom_village__icontains=recherche)
    total = q.count()
    villages = []
    for a in q[:limite]:
        v = a.village
        villages.append({
            'id': str(v.id), 'nom': v.nom_village,
            'commune': v.fokontany.commune.nom_commune if v.fokontany_id and v.fokontany.commune_id else '',
            'distance_m': round(a.distance_m),
            'lon': float(v.longitude), 'lat': float(v.latitude),
            'route': [float(a.longitude), float(a.latitude)],
            'reseau_principal': a.reseau_principal,
        })
    return {'total': total, 'villages': villages}


def contexte(lon, lat, marge=0.03):
    """Tronçons et villages autour d'un point, pour voir le réseau pendant le tracé."""
    ix, positions = index_spatial.dans_boite(lon, lat, marge)
    villages = (VillageAccesRoute.objects.filter(
        village__longitude__range=(lon - marge, lon + marge), village__latitude__range=(lat - marge, lat + marge))
        .select_related('village'))
    return {
        'troncons': {'type': 'FeatureCollection', 'features': [index_spatial.feature(ix, i) for i in positions]},
        'villages': [{'id': str(a.village_id), 'nom': a.village.nom_village, 'lon': float(a.village.longitude),
                      'lat': float(a.village.latitude), 'distance_m': round(a.distance_m)} for a in villages],
    }


def _choisir_cible(fin_lon, fin_lat, principale):
    """Tronçon à viser près du point d'arrivée : réseau principal d'abord, sinon n'importe quel tronçon.

    Retourne ((distance, tronçon, ligne, point le plus proche), fait_partie_du_réseau_principal).
    """
    p = Point(fin_lon, fin_lat)
    ix, positions = index_spatial.dans_boite(fin_lon, fin_lat, RECHERCHE_DEG)
    meilleur = {True: None, False: None}   # clé : fait partie du réseau principal ?
    for i in positions:
        q = nearest_points(ix.lignes[i], p)[0]
        d = haversine_m(p.x, p.y, q.x, q.y)
        cle = ix.debuts[i] in principale
        if meilleur[cle] is None or d < meilleur[cle][0]:
            meilleur[cle] = (d, i, q)
    for cle in (True, False):
        if meilleur[cle] and meilleur[cle][0] <= SEUIL_FIN_M:
            d, i, q = meilleur[cle]
            tronc = TronconRoute.objects.select_related('noeud_debut', 'noeud_fin').get(pk=ix.ids[i])
            return (d, tronc, ix.lignes[i], q), cle
    raise TraceInvalide("L'arrivée est à plus de 300 m du réseau : rapproche-la d'une route existante.")


def _rattacher_voisins(nouveau, principal):
    """Rattache au nouveau tracé les villages qui en sont plus proches que de leur route actuelle."""
    ligne = LineString(nouveau.geometrie)
    x0, y0, x1, y1 = ligne.bounds
    m = 0.01
    modifies = 0
    for a in (VillageAccesRoute.objects.select_related('village')
              .filter(village__longitude__range=(x0 - m, x1 + m), village__latitude__range=(y0 - m, y1 + m))):
        p = Point(float(a.village.longitude), float(a.village.latitude))
        q = nearest_points(ligne, p)[0]
        d = haversine_m(p.x, p.y, q.x, q.y)
        if d + 10 < a.distance_m:
            a.troncon, a.fraction, a.distance_m = nouveau, ligne.project(q, normalized=True), d
            a.longitude, a.latitude = round(q.x, 7), round(q.y, 7)
            a.reseau_principal = principal
            a.save()
            modifies += 1
    return modifies


@transaction.atomic
def tracer(village_id, waypoints, fin_lon, fin_lat, categorie='sentier'):
    """Crée le tronçon manuel village -> réseau. Retourne un dict de résultat."""
    if categorie not in CATEGORIES:
        raise TraceInvalide('Type de voie invalide.')
    village = Village.objects.filter(pk=village_id).first()
    if village is None or village.latitude is None or village.longitude is None:
        raise TraceInvalide("Village introuvable ou sans coordonnées GPS.")

    comps = _graphe()
    principale = comps[0] if comps else set()
    (_, cible, ligne, q), est_principal = _choisir_cible(fin_lon, fin_lat, principale)

    for n in (cible.noeud_debut, cible.noeud_fin):
        if haversine_m(float(n.longitude), float(n.latitude), q.x, q.y) <= SNAP_NOEUD_M:
            arrivee = n
            break
    else:
        arrivee = _decouper(cible, ligne.project(q, normalized=True))

    depart = _noeud(float(village.longitude), float(village.latitude))
    if depart.id == arrivee.id:
        raise TraceInvalide("Le village est déjà sur le réseau.")
    trace = [[float(depart.longitude), float(depart.latitude)]]
    trace += [[round(float(x), 7), round(float(y), 7)] for x, y in waypoints]
    trace.append([float(arrivee.longitude), float(arrivee.latitude)])

    t = TronconRoute.objects.create(
        nom=f"Tracé libre {village.nom_village}"[:255], type_voie='trace libre', categorie=categorie, source='manuel',
        noeud_debut=depart, noeud_fin=arrivee, geometrie=trace, longueur_m=longueur_geodesique_m(trace))

    VillageAccesRoute.objects.update_or_create(village=village, defaults={
        'troncon': t, 'fraction': 0.0, 'distance_m': 0.0, 'longitude': depart.longitude,
        'latitude': depart.latitude, 'reseau_principal': est_principal})
    voisins = _rattacher_voisins(t, est_principal)
    return {'troncon': t, 'reseau_principal': est_principal, 'voisins_rattaches': voisins}


# --- Tracé libre « SIG » : une route dessinée clic par clic, n'importe où -------------------------------------------------

CATEGORIES_LIGNE = ('nationale', 'provinciale', 'communale', 'route', 'piste', 'sentier')
SNAP_JONCTION_M = 5.0          # un sommet à moins de 5 m d'une route existante devient une jonction
BOITE_JONCTION_DEG = 0.0003    # ~33 m : zone de recherche des routes autour d'un sommet
LONGUEUR_MIN_M = 5.0
MAX_POINTS = 3000
MAX_JONCTIONS = 15


def _nettoyer_points(points):
    """Points [lon, lat] arrondis, sans doublons consécutifs (< 0,5 m) ; refuse l'invalide."""
    propres = []
    for p in points:
        try:
            lon, lat = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            raise TraceInvalide("Point invalide dans le tracé.")
        if not dans_madagascar(lon, lat):
            raise TraceInvalide("Un point du tracé est hors de Madagascar.")
        if propres and haversine_m(propres[-1][0], propres[-1][1], lon, lat) < 0.5:
            continue
        propres.append([round(lon, 7), round(lat, 7)])
    if len(propres) < 2:
        raise TraceInvalide("Il faut au moins deux points distincts.")
    if len(propres) > MAX_POINTS:
        raise TraceInvalide(f"Tracé trop détaillé (plus de {MAX_POINTS} points).")
    return propres


def _route_proche(ix, lon, lat):
    """(distance en m, position dans l'index, point le plus proche) de la route existante la plus proche, ou None."""
    _, positions = index_spatial.dans_boite(lon, lat, BOITE_JONCTION_DEG)
    p = Point(lon, lat)
    meilleur = None
    for pos in positions:
        q = nearest_points(ix.lignes[pos], p)[0]
        d = haversine_m(lon, lat, q.x, q.y)
        if d <= SNAP_JONCTION_M and (meilleur is None or d < meilleur[0]):
            meilleur = (d, pos, q)
    return meilleur


@transaction.atomic
def tracer_ligne(points, categorie='piste', nom=''):
    """Enregistre une route dessinée librement (liste de [lon, lat]) comme tronçon(s) `source='manuel'`.

    Chaque sommet situé à moins de 5 m d'une route existante devient une **jonction** : la route visée est découpée à
    cet endroit (sauf si le point est déjà un de ses nœuds) et le tracé est coupé en un tronçon par jonction. Les deux
    extrémités libres deviennent des bouts de route (impasses). Les villages plus proches du nouveau tracé que de leur
    route actuelle y sont rattachés.
    """
    if categorie not in CATEGORIES_LIGNE:
        raise TraceInvalide('Type de voie invalide.')
    pts = _nettoyer_points(points)
    if longueur_geodesique_m(pts) < LONGUEUR_MIN_M:
        raise TraceInvalide(f"Tracé trop court (moins de {int(LONGUEUR_MIN_M)} m).")

    comps = _graphe()
    principale = comps[0] if comps else set()
    ix = index_spatial.index()

    # 1. Jonctions : sommets posés sur une route existante, regroupés par tronçon visé.
    par_troncon = defaultdict(list)           # id du tronçon -> [(fraction, indice du sommet, point projeté)]
    for i, (lon, lat) in enumerate(pts):
        proche = _route_proche(ix, lon, lat)
        if proche:
            _, pos, q = proche
            par_troncon[ix.ids[pos]].append((ix.lignes[pos].project(q, normalized=True), i, q))
    nb_jonctions = sum(len(v) for v in par_troncon.values())
    if nb_jonctions > MAX_JONCTIONS:
        raise TraceInvalide(f"Plus de {MAX_JONCTIONS} jonctions dans un même tracé : enregistre-le en plusieurs fois.")

    noeuds = {}                               # indice du sommet -> NoeudRoute
    relie_principal = False
    for tid, jonctions in par_troncon.items():
        troncon = TronconRoute.objects.select_related('noeud_debut', 'noeud_fin').get(pk=tid)
        relie_principal = relie_principal or troncon.noeud_debut_id in principale
        origine = LineString(troncon.geometrie)
        debut, fin = troncon.noeud_debut, troncon.noeud_fin
        crees = []                            # nœuds déjà posés sur ce tronçon pendant cet appel
        # On coupe de l'arrivée vers le départ : le tronçon d'origine devient sa première moitié, donc la
        # fraction suivante se ramène à la longueur restante.
        for fraction, i, q in sorted(jonctions, key=lambda j: j[0], reverse=True):
            voisin = next((n for n in (debut, fin, *crees)
                           if haversine_m(float(n.longitude), float(n.latitude), q.x, q.y) <= SNAP_NOEUD_M), None)
            if voisin is None:
                restante = LineString(troncon.geometrie).length
                voisin = _decouper(troncon, min(fraction * origine.length / restante, 0.999999))
                crees.append(voisin)
            noeuds[i] = voisin

    # 2. Extrémités libres : impasses.
    for i in (0, len(pts) - 1):
        if i not in noeuds:
            noeuds[i] = _noeud(pts[i][0], pts[i][1])

    # 3. Un tronçon par intervalle entre deux points d'arrêt (extrémités et jonctions).
    arrets = sorted(set(noeuds))
    crees_troncons = []
    for a, b in zip(arrets, arrets[1:]):
        na, nb = noeuds[a], noeuds[b]
        geometrie = [[float(na.longitude), float(na.latitude)]] + pts[a + 1:b] + [[float(nb.longitude), float(nb.latitude)]]
        longueur = longueur_geodesique_m(geometrie)
        if longueur < 1.0:                    # deux jonctions confondues : rien à dessiner
            continue
        crees_troncons.append(TronconRoute.objects.create(
            nom=(nom or 'Tracé libre')[:255], type_voie='trace libre', categorie=categorie, source='manuel',
            noeud_debut=na, noeud_fin=nb, geometrie=geometrie, longueur_m=longueur))
    if not crees_troncons:
        raise TraceInvalide("Le tracé se confond avec des routes existantes.")

    voisins = sum(_rattacher_voisins(t, relie_principal) for t in crees_troncons)
    return {'troncons': crees_troncons, 'longueur_m': sum(t.longueur_m for t in crees_troncons),
            'jonctions': nb_jonctions,
            'relie_reseau_principal': relie_principal, 'voisins_rattaches': voisins}
