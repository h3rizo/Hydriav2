"""Détection et réparation des coupures du réseau routier.

Une « coupure » est un morceau de réseau isolé du réseau principal (la plus grande
composante connexe) qui dessert au moins un village. Pour chacune on propose le raccord
le plus court vers le réseau principal ; l'utilisateur le valide ou l'ajuste sur la carte.
"""
from decimal import Decimal

import networkx as nx
from django.db import transaction
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, substring
from shapely.strtree import STRtree

from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute

from . import index_spatial
from .reseau_routier import haversine_m, longueur_geodesique_m

SEUIL_ECART_MAX_M = 300.0   # écart max entre le point posé par l'utilisateur et la route visée
BORNE_NOEUD_M = 1.5         # sous cette distance d'un nœud existant, on s'y raccroche sans découper


class RaccordInvalide(Exception):
    pass


def _graphe():
    lignes = list(TronconRoute.objects.values_list('id', 'noeud_debut_id', 'noeud_fin_id'))
    g = nx.Graph()
    g.add_edges_from((a, b) for _, a, b in lignes)
    comps = sorted(nx.connected_components(g), key=len, reverse=True)
    return comps


def _cid(noeuds):
    return str(min(noeuds))


def _villages_par_noeud():
    """{noeud_debut_id du tronçon d'accès: [noms de villages]}"""
    out = {}
    q = VillageAccesRoute.objects.values_list('troncon__noeud_debut_id', 'village__nom_village')
    for noeud_id, nom in q:
        out.setdefault(noeud_id, []).append(nom)
    return out


def lister_coupures():
    comps = _graphe()
    if not comps:
        return []
    principale, autres = comps[0], comps[1:]
    par_noeud = _villages_par_noeud()

    coupures = []
    for c in autres:
        noms = [n for noeud in c for n in par_noeud.get(noeud, [])]
        if noms:
            coupures.append((c, noms))
    if not coupures:
        return []

    troncons_princ = list(TronconRoute.objects.filter(noeud_debut_id__in=principale)
                          .values_list('id', 'geometrie'))
    lignes = [LineString(g) for _, g in troncons_princ]
    arbre = STRtree(lignes)
    coords = {n.id: (float(n.longitude), float(n.latitude))
              for n in NoeudRoute.objects.filter(id__in=[i for c, _ in coupures for i in c])}

    resultat = []
    for c, noms in coupures:
        meilleur = None
        for noeud_id in c:
            p = Point(coords[noeud_id])
            idx = int(arbre.nearest(p))
            d = lignes[idx].distance(p)
            if meilleur is None or d < meilleur[0]:
                meilleur = (d, noeud_id, idx, p)
        _, noeud_id, idx, p = meilleur
        q = nearest_points(lignes[idx], p)[0]
        centre = [sum(coords[i][0] for i in c) / len(c), sum(coords[i][1] for i in c) / len(c)]
        resultat.append({
            'id': _cid(c),
            'nb_villages': len(noms),
            'villages': sorted(noms)[:6],
            'nb_noeuds': len(c),
            'ecart_m': round(haversine_m(p.x, p.y, q.x, q.y)),
            'from_noeud_id': str(noeud_id),
            'from': list(coords[noeud_id]),
            'to': [q.x, q.y],
            'to_troncon_id': str(troncons_princ[idx][0]),
            'centre': centre,
        })
    resultat.sort(key=lambda r: (-r['nb_villages'], r['ecart_m']))
    return resultat


def detail_coupure(cid, marge_deg=0.02):
    """GeoJSON de la coupure, du réseau principal alentour et des villages concernés."""
    comps = _graphe()
    comp = next((c for c in comps[1:] if _cid(c) == cid), None)
    if comp is None:
        return None
    troncons = list(TronconRoute.objects.filter(noeud_debut_id__in=comp))
    xs = [x for t in troncons for x, _ in t.geometrie]
    ys = [y for t in troncons for _, y in t.geometrie]
    x0, x1, y0, y1 = min(xs) - marge_deg, max(xs) + marge_deg, min(ys) - marge_deg, max(ys) + marge_deg

    # Réseau principal alentour : on cherche par rectangle englobant (une longue route peut traverser la zone
    # sans qu'aucune de ses extrémités n'y soit).
    ix, positions = index_spatial.dans_boite((x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) / 2)
    voisins = [index_spatial.feature(ix, i) for i in positions if ix.debuts[i] in comps[0]]

    def feat(t):
        return {'type': 'Feature',
                'properties': {'id': str(t.id), 'categorie': t.categorie, 'nom': t.nom, 'source': t.source},
                'geometry': {'type': 'LineString', 'coordinates': t.geometrie}}

    villages = (VillageAccesRoute.objects.filter(troncon__noeud_debut_id__in=comp)
                .select_related('village'))
    return {
        'coupure': {'type': 'FeatureCollection', 'features': [feat(t) for t in troncons]},
        'reseau': {'type': 'FeatureCollection', 'features': voisins},
        'villages': [{'nom': a.village.nom_village, 'lon': float(a.village.longitude),
                      'lat': float(a.village.latitude), 'distance_m': round(a.distance_m)}
                     for a in villages],
        'bbox': [x0, y0, x1, y1],
    }


def _noeud(lon, lat):
    d = (Decimal(f"{lon:.7f}"), Decimal(f"{lat:.7f}"))
    n, _ = NoeudRoute.objects.get_or_create(longitude=d[0], latitude=d[1])
    return n


def _arrondi(coords):
    return [[round(x, 7), round(y, 7)] for x, y in coords]


def _decouper(troncon, fraction):
    """Coupe `troncon` en deux à `fraction` (0-1) ; retourne le NoeudRoute créé.

    Le tronçon d'origine devient la première moitié ; les accès de villages sont réaffectés
    pour rester cohérents.
    """
    ligne = LineString(troncon.geometrie)
    d = fraction * ligne.length
    p = ligne.interpolate(d)
    noeud = _noeud(round(p.x, 7), round(p.y, 7))
    pt = [float(noeud.longitude), float(noeud.latitude)]
    a = _arrondi(substring(ligne, 0, d).coords)
    b = _arrondi(substring(ligne, d, ligne.length).coords)
    a[-1], b[0] = pt, pt

    fin_orig = troncon.noeud_fin
    suite = TronconRoute.objects.create(
        nom=troncon.nom, type_voie=troncon.type_voie, categorie=troncon.categorie,
        interet=troncon.interet, commune_nom=troncon.commune_nom, source=troncon.source,
        vitesse_kmh=troncon.vitesse_kmh, praticable=troncon.praticable,
        noeud_debut=noeud, noeud_fin=fin_orig, geometrie=b, longueur_m=longueur_geodesique_m(b))
    troncon.noeud_fin = noeud
    troncon.geometrie = a
    troncon.longueur_m = longueur_geodesique_m(a)
    troncon.save()

    for acces in VillageAccesRoute.objects.filter(troncon=troncon):
        if acces.fraction > fraction:
            acces.troncon = suite
            acces.fraction = (acces.fraction - fraction) / (1 - fraction)
        else:
            acces.fraction = acces.fraction / fraction if fraction else 0
        acces.save(update_fields=['troncon', 'fraction'])
    return noeud


@transaction.atomic
def raccorder(from_noeud_id, waypoints, fin_lon, fin_lat):
    """Crée un tronçon manuel du nœud `from_noeud_id` jusqu'au réseau principal.

    `waypoints` : points intermédiaires [[lon, lat], ...]. Le point final est ramené sur
    le tronçon du réseau principal le plus proche (erreur s'il en est à plus de 300 m).
    """
    comps = _graphe()
    if not comps:
        raise RaccordInvalide("Aucun réseau routier.")
    principale = comps[0]
    depart = NoeudRoute.objects.filter(id=from_noeud_id).first()
    if depart is None or depart.id in principale:
        raise RaccordInvalide("Le point de départ doit être sur un morceau isolé du réseau.")

    candidats = list(TronconRoute.objects.filter(noeud_debut_id__in=principale)
                     .select_related('noeud_debut', 'noeud_fin'))
    p = Point(fin_lon, fin_lat)
    lignes = [LineString(t.geometrie) for t in candidats]
    idx = int(STRtree(lignes).nearest(p))
    cible, ligne = candidats[idx], lignes[idx]
    q = nearest_points(ligne, p)[0]
    if haversine_m(p.x, p.y, q.x, q.y) > SEUIL_ECART_MAX_M:
        raise RaccordInvalide("Le point d'arrivée est à plus de 300 m du réseau principal : rapproche-le d'une route.")

    # Raccroche à un nœud existant s'il est tout proche, sinon découpe le tronçon visé.
    for n in (cible.noeud_debut, cible.noeud_fin):
        if haversine_m(float(n.longitude), float(n.latitude), q.x, q.y) <= BORNE_NOEUD_M:
            arrivee = n
            break
    else:
        arrivee = _decouper(cible, ligne.project(q, normalized=True))

    trace = [[float(depart.longitude), float(depart.latitude)]]
    trace += [[round(float(x), 7), round(float(y), 7)] for x, y in waypoints]
    trace.append([float(arrivee.longitude), float(arrivee.latitude)])
    if len(trace) < 2 or trace[0] == trace[-1]:
        raise RaccordInvalide("Tracé invalide.")

    t = TronconRoute.objects.create(
        nom='Raccord manuel', type_voie='raccord manuel', categorie='sentier', source='manuel',
        noeud_debut=depart, noeud_fin=arrivee, geometrie=trace, longueur_m=longueur_geodesique_m(trace))

    # La coupure fait désormais partie du réseau principal.
    comp = next(c for c in comps if depart.id in c)
    VillageAccesRoute.objects.filter(troncon__noeud_debut_id__in=comp).update(reseau_principal=True)
    return t
