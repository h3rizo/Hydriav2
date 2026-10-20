"""Lieux quelconques (base, position GPS) rattachés au réseau routier.

Un village est rattaché au réseau par `VillageAccesRoute`. Un lieu qui n'est pas un village (une base
en ville, une position GPS) n'a pas cette ligne : on calcule alors son point d'accès à la volée, en
projetant la position sur le tronçon praticable le plus proche (index spatial en mémoire).
"""
from shapely.geometry import Point
from shapely.ops import nearest_points

from . import index_spatial
from . import itineraire as it
from .reseau_routier import haversine_m

# Emprise approximative de Madagascar : hors de ce cadre, la position est jugée erronée.
LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = 43.0, 51.0, -26.0, -11.5


def dans_madagascar(lon, lat):
    return LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX


def acces_point(lon, lat, nom='Lieu'):
    """Point d'accès au réseau (même forme que `itineraire.acces_village`) pour une position GPS.

    Lève ItineraireIntrouvable si la position est hors de Madagascar ou si aucun tronçon praticable n'existe.
    """
    if not dans_madagascar(lon, lat):
        raise it.ItineraireIntrouvable("Position hors de Madagascar.")
    ix = index_spatial.index()
    if not ix.ids:
        raise it.ItineraireIntrouvable("Aucun réseau routier chargé.")
    praticables = it.reseau().troncons
    p = Point(lon, lat)
    # Tronçon le plus proche ; si ce n'est pas un tronçon praticable on élargit à ses voisins immédiats.
    i = int(ix.arbre.nearest(p))
    if ix.ids[i] not in praticables:
        marge = 0.05
        candidats = [int(j) for j in ix.arbre.query(p.buffer(marge)) if ix.ids[int(j)] in praticables]
        if not candidats:
            raise it.ItineraireIntrouvable("Aucune route praticable à proximité.")
        i = min(candidats, key=lambda j: ix.lignes[j].distance(p))
    ligne = ix.lignes[i]
    q = nearest_points(ligne, p)[0]
    return {'troncon_id': ix.ids[i], 'fraction': ligne.project(q, normalized=True),
            'distance_m': haversine_m(lon, lat, q.x, q.y), 'lon': q.x, 'lat': q.y,
            'village_lon': lon, 'village_lat': lat, 'nom': nom}


def acces_base(base):
    """Point d'accès au réseau du lieu de départ d'une base, ou None si elle n'est pas localisée."""
    lieu = base.lieu_depart
    if lieu is None:
        return None
    lon, lat, libelle = lieu
    if base.latitude_depart is None and base.village_depart_id:
        try:                                        # village seul : on utilise son rattachement officiel
            return it.acces_village(base.village_depart_id)
        except it.ItineraireIntrouvable:
            pass
    return acces_point(lon, lat, nom=libelle)
