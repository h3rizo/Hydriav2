"""Construction d'un réseau routier propre à partir d'un shapefile de polylignes.

Étapes :
  1. lecture (shapefile ignore les géométries vides) ;
  2. noeudage : `unary_union` coupe toutes les lignes à chaque intersection ;
  3. raccords : une extrémité isolée proche d'un autre tracé y est reliée ;
  4. attribution : chaque tronçon hérite du type de l'original le plus important.
"""
import math
from collections import Counter

import shapefile
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union
from shapely.strtree import STRtree

from .voies_config import CATEGORIE_PAR_TYPE, RANG_CATEGORIE, TOLERANCE_RACCORD_M

M_PAR_DEGRE = 111_000.0
EPS = 1e-7  # ~1 cm : tolérance d'identité entre un tronçon et son tracé d'origine


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def longueur_geodesique_m(coords):
    return sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(coords, coords[1:]))


def categorie_de(type_voie):
    return CATEGORIE_PAR_TYPE.get((type_voie or '').strip().lower(), 'autre')


def lire_shapefile(chemin):
    """Retourne (lignes, attributs) ; une ligne par partie, attributs répétés."""
    lecteur = shapefile.Reader(chemin, encoding='utf-8', encodingErrors='replace')
    champs = [f[0] for f in lecteur.fields[1:]]
    lignes, attrs, ignores = [], [], 0
    for i in range(len(lecteur)):
        try:
            forme = lecteur.shape(i)
            if not forme.points:
                raise ValueError('vide')
            rec = dict(zip(champs, lecteur.record(i)))
        except Exception:
            ignores += 1
            continue
        bornes = list(forme.parts) + [len(forme.points)]
        for a, b in zip(bornes, bornes[1:]):
            pts = forme.points[a:b]
            if len(pts) >= 2:
                lignes.append(LineString(pts))
                attrs.append(rec)
    return lignes, attrs, ignores


def _segments(union):
    return [g for g in getattr(union, 'geoms', [union]) if isinstance(g, LineString) and len(g.coords) >= 2]


def _raccords(segments, tol_deg):
    """Segments courts reliant chaque extrémité isolée au tracé voisin le plus proche."""
    degre = Counter()
    for s in segments:
        degre[tuple(s.coords[0])] += 1
        degre[tuple(s.coords[-1])] += 1
    arbre = STRtree(segments)
    raccords = []
    for xy, d in degre.items():
        if d != 1:
            continue
        p = Point(xy)
        meilleur, dmin = None, tol_deg
        for idx in arbre.query(p.buffer(tol_deg)):
            seg = segments[idx]
            dist = seg.distance(p)
            if dist < EPS:  # c'est le tronçon qui porte ce bout, ou il le touche déjà
                continue
            if dist < dmin:
                meilleur, dmin = seg, dist
        if meilleur is not None:
            q = nearest_points(p, meilleur)[1]
            raccords.append(LineString([xy, (q.x, q.y)]))
    return raccords


def construire_reseau(chemin_shp, tolerance_m=TOLERANCE_RACCORD_M):
    """Retourne (troncons, stats). Chaque tronçon : dict prêt à devenir un TronconRoute."""
    lignes, attrs, ignores = lire_shapefile(chemin_shp)
    arbre_orig = STRtree(lignes)

    nodees = _segments(unary_union(lignes))
    raccords = _raccords(nodees, tolerance_m / M_PAR_DEGRE)
    finales = _segments(unary_union(lignes + raccords)) if raccords else nodees

    troncons = []
    for seg in finales:
        coords = [(round(x, 7), round(y, 7)) for x, y in seg.coords]
        if coords[0] == coords[-1] or len(coords) < 2:
            continue
        milieu = seg.interpolate(0.5, normalized=True)
        meilleur = None
        for idx in arbre_orig.query(milieu.buffer(EPS)):
            if lignes[idx].distance(milieu) > EPS:
                continue
            cat = categorie_de(attrs[idx].get('TYPE'))
            if meilleur is None or RANG_CATEGORIE.index(cat) < RANG_CATEGORIE.index(meilleur[0]):
                meilleur = (cat, attrs[idx])
        if meilleur is None:
            cat, a, source = 'autre', {}, 'raccord'
        else:
            cat, a = meilleur
            source = 'shapefile'
        troncons.append({
            'nom': (a.get('NAME') or '').strip()[:255],
            'type_voie': (a.get('TYPE') or '').strip()[:80],
            'categorie': cat if source == 'shapefile' else 'autre',
            'interet': (a.get('INTERET') or '').strip()[:20],
            'commune_nom': (a.get('COMMUNE') or '').strip()[:60],
            'source': source,
            'coords': coords,
            'longueur_m': longueur_geodesique_m(coords),
        })

    stats = {
        'lignes_lues': len(lignes),
        'formes_ignorees': ignores,
        'troncons': len(troncons),
        'raccords': sum(1 for t in troncons if t['source'] == 'raccord'),
        'km_total': sum(t['longueur_m'] for t in troncons) / 1000,
    }
    return troncons, stats
