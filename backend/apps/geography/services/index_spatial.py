"""Index spatial en mémoire des tronçons (rectangle englobant de chaque route).

Chercher les routes « près d'un point » d'après leurs seules extrémités rate les longues routes
qui passent à côté sans qu'aucune extrémité soit proche. Ici on indexe la géométrie entière
(STRtree shapely), reconstruite seulement quand le réseau change.
"""
import threading
from collections import namedtuple

from django.db.models import Max
from shapely.geometry import LineString, box
from shapely.strtree import STRtree

from apps.geography.models_routes import TronconRoute

Index = namedtuple('Index', 'ids debuts fins lignes categories sources arbre')

_cache = {'sig': None, 'index': None}
_verrou = threading.Lock()


def index():
    agg = TronconRoute.objects.aggregate(m=Max('updated_at'))
    sig = (TronconRoute.objects.count(), agg['m'])
    with _verrou:
        if _cache['sig'] != sig:
            ids, debuts, fins, lignes, cats, srcs = [], [], [], [], [], []
            for tid, a, b, geom, cat, src in TronconRoute.objects.values_list(
                    'id', 'noeud_debut_id', 'noeud_fin_id', 'geometrie', 'categorie', 'source'):
                ids.append(tid); debuts.append(a); fins.append(b)
                lignes.append(LineString(geom)); cats.append(cat); srcs.append(src)
            _cache['index'] = Index(ids, debuts, fins, lignes, cats, srcs, STRtree(lignes))
            _cache['sig'] = sig
        return _cache['index']


def dans_boite(lon, lat, marge_deg):
    """Positions (dans l'index) des tronçons dont le rectangle englobant touche le carré autour du point."""
    ix = index()
    zone = box(lon - marge_deg, lat - marge_deg, lon + marge_deg, lat + marge_deg)
    return ix, [int(i) for i in ix.arbre.query(zone)]


def feature(ix, i):
    return {'type': 'Feature',
            'properties': {'id': str(ix.ids[i]), 'categorie': ix.categories[i], 'source': ix.sources[i]},
            'geometry': {'type': 'LineString', 'coordinates': [list(c) for c in ix.lignes[i].coords]}}
