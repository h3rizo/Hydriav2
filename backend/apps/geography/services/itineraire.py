"""Calcul d'itinéraires entre villages sur le réseau routier.

Le graphe networkx est construit une fois (puis mis en cache tant que les tronçons ne changent
pas) : un nœud par NoeudRoute, une arête par TronconRoute. Pour chaque requête on ajoute deux
nœuds virtuels « A » et « B » placés exactement là où chaque village se projette sur son
tronçon, reliés aux deux extrémités de ce tronçon. Le trajet à pied village -> route est
ajouté séparément (il ne dépend pas du chemin choisi).
"""
import threading
from collections import defaultdict

import networkx as nx
from django.db.models import Max
from shapely.geometry import LineString
from shapely.ops import substring

from apps.geography.models_routes import TronconRoute, VillageAccesRoute

from .voies_config import PROFIL_DEFAUT, PROFILS, VITESSE_MARCHE_KMH

CRITERES = ('temps', 'distance')
PROFILS_VALIDES = tuple(PROFILS)


class ItineraireIntrouvable(Exception):
    pass


def vitesse_kmh(t, profil=PROFIL_DEFAUT):
    """Vitesse moyenne du tronçon pour un profil. La surcharge manuelle `vitesse_kmh` ne vaut que pour les
    engins motorisés : à pied, on garde la vitesse de marche."""
    if t.vitesse_kmh and profil != 'pied':
        return t.vitesse_kmh
    table = PROFILS[profil]
    cle = 'raccord' if t.source == 'raccord' else t.categorie
    return table.get(cle) or table['autre']


def _secondes(metres, kmh):
    return metres / (kmh * 1000 / 3600)


def _durees(metres, vitesses):
    """Attributs d'arête `t_<profil>` : durée en secondes pour chaque profil de déplacement."""
    return {f't_{p}': _secondes(metres, v) for p, v in vitesses.items()}


class Reseau:
    def __init__(self):
        self.G = nx.Graph()
        self.troncons = {}
        for t in TronconRoute.objects.filter(praticable=True):
            if t.noeud_debut_id == t.noeud_fin_id:
                continue
            vitesses = {p: vitesse_kmh(t, p) for p in PROFILS}
            self.troncons[t.id] = {
                'debut': t.noeud_debut_id, 'fin': t.noeud_fin_id, 'coords': t.geometrie,
                'longueur': t.longueur_m, 'vitesses': vitesses, 'categorie': t.categorie,
            }
            durees = _durees(t.longueur_m, vitesses)
            ancien = self.G.get_edge_data(t.noeud_debut_id, t.noeud_fin_id)
            # arêtes parallèles : on garde la plus rapide (profil par défaut)
            if ancien is None or durees[f't_{PROFIL_DEFAUT}'] < ancien[f't_{PROFIL_DEFAUT}']:
                self.G.add_edge(t.noeud_debut_id, t.noeud_fin_id, tid=t.id, longueur=t.longueur_m, **durees)

    def _orienter(self, tid, de):
        coords = self.troncons[tid]['coords']
        return coords if self.troncons[tid]['debut'] == de else coords[::-1]

    def _virtuel(self, H, nom, acces):
        """Ajoute le nœud virtuel `nom` sur le tronçon d'accès ; retourne la ligne shapely."""
        info = self.troncons.get(acces['troncon_id'])
        if info is None:
            raise ItineraireIntrouvable("Le tronçon d'accès de ce village n'est plus praticable.")
        ligne = LineString(info['coords'])
        d = acces['fraction'] * ligne.length
        vers_debut = list(substring(ligne, 0, d).coords)[::-1]
        vers_fin = list(substring(ligne, d, ligne.length).coords)
        for noeud, geom, part in ((info['debut'], vers_debut, acces['fraction']),
                                  (info['fin'], vers_fin, 1 - acces['fraction'])):
            m = part * info['longueur']
            H.add_edge(nom, noeud, longueur=m, **_durees(m, info['vitesses']),
                       geom=[list(c) for c in geom], categorie=info['categorie'], virtuel=nom)
        return ligne

    def itineraire(self, a, b, critere='temps', profil=PROFIL_DEFAUT):
        """a, b : dict(troncon_id, fraction, distance_m, lon, lat, village_lon, village_lat)."""
        r = self.itineraires_depuis(a, {0: b}, critere, profil=profil)[0]
        if isinstance(r, Exception):
            raise r
        return r

    def itineraires_depuis(self, a, cibles, critere='temps', H=None, profil=PROFIL_DEFAUT):
        """Itinéraires de `a` vers plusieurs destinations avec un seul calcul de plus court chemin.

        `cibles` : {clé: acces}. Retourne {clé: résultat | ItineraireIntrouvable}.
        `H` : copie privée du graphe, réutilisable d'un appel à l'autre (les nœuds virtuels y sont
        retirés à la fin) ; évite de recopier tout le graphe pour chaque village de départ.
        """
        if critere not in CRITERES:
            raise ValueError('critere invalide')
        if profil not in PROFILS:
            raise ValueError('profil invalide')
        if H is None:
            H = self.G.copy()
        try:
            return self._itineraires_depuis(H, a, cibles, critere, profil)
        finally:
            H.remove_nodes_from([n for n in list(H.nodes) if n == 'A' or isinstance(n, tuple)])

    def _itineraires_depuis(self, H, a, cibles, critere, profil):
        ligne_a = self._virtuel(H, 'A', a)
        sortie, noeuds = {}, {}
        for cle_b, b in cibles.items():
            try:
                nom = ('B', cle_b)
                self._virtuel(H, nom, b)
                noeuds[cle_b] = nom
            except ItineraireIntrouvable as exc:
                sortie[cle_b] = exc
                continue
            if a['troncon_id'] == b['troncon_id']:
                # Deux villages sur le même tronçon : trajet direct sans passer par les extrémités.
                info = self.troncons[a['troncon_id']]
                da, db = a['fraction'] * ligne_a.length, b['fraction'] * ligne_a.length
                geom = list(substring(ligne_a, da, db).coords)
                m = abs(a['fraction'] - b['fraction']) * info['longueur']
                H.add_edge('A', nom, longueur=m, **_durees(m, info['vitesses']),
                           geom=[list(c) for c in geom], categorie=info['categorie'], virtuel='A')

        poids = f't_{profil}' if critere == 'temps' else 'longueur'
        # Exploration limitée aux environs (3 h de trajet / 80 km) : suffisant pour des villages voisins et
        # bien plus rapide ; si une destination n'est pas atteinte, on recommence sans limite.
        limite = 3 * 3600 if critere == 'temps' else 80_000
        pred, _ = nx.dijkstra_predecessor_and_distance(H, 'A', weight=poids, cutoff=limite)
        if any(nom not in pred for nom in noeuds.values()):
            pred, _ = nx.dijkstra_predecessor_and_distance(H, 'A', weight=poids)
        for cle_b, nom in noeuds.items():
            if nom not in pred:
                sortie[cle_b] = ItineraireIntrouvable(
                    "Aucun chemin entre ces deux villages : le réseau routier est coupé.")
                continue
            chemin = [nom]
            while chemin[-1] != 'A':
                chemin.append(pred[chemin[-1]][0])
            sortie[cle_b] = self._formater(H, chemin[::-1], a, cibles[cle_b], profil)
        return sortie

    def _formater(self, H, chemin, a, b, profil=PROFIL_DEFAUT):
        trace = [[a['village_lon'], a['village_lat']], [a['lon'], a['lat']]]
        route_m = route_s = 0.0
        repartition = defaultdict(float)
        for u, v in zip(chemin, chemin[1:]):
            e = H[u][v]
            route_m += e['longueur']
            route_s += e[f't_{profil}']
            if 'geom' in e:
                g = e['geom']
                # Géométrie stockée en partant du nœud virtuel `virtuel` : on inverse si on la parcourt à l'envers.
                if e['virtuel'] != u:
                    g = g[::-1]
                repartition[e['categorie']] += e['longueur']
            else:
                g = self._orienter(e['tid'], u)
                repartition[self.troncons[e['tid']]['categorie']] += e['longueur']
            trace.extend([list(p) for p in g])
        trace.extend([[b['lon'], b['lat']], [b['village_lon'], b['village_lat']]])
        trace = [p for i, p in enumerate(trace) if i == 0 or p != trace[i - 1]]

        marche_m = a['distance_m'] + b['distance_m']
        if marche_m:
            repartition['marche'] += marche_m
        return {
            'distance_m': route_m + marche_m,
            'duree_s': route_s + _secondes(marche_m, VITESSE_MARCHE_KMH),
            'marche_m': marche_m,
            'geometrie': trace,
            'repartition_m': dict(repartition),
            'profil': profil,
        }


_cache = {'sig': None, 'reseau': None}
_verrou = threading.Lock()


def reseau():
    agg = TronconRoute.objects.aggregate(m=Max('updated_at'))
    sig = (TronconRoute.objects.count(), agg['m'])
    with _verrou:
        if _cache['sig'] != sig:
            _cache['reseau'], _cache['sig'] = Reseau(), sig
        return _cache['reseau']


def acces_village(village_id):
    a = VillageAccesRoute.objects.select_related('village').filter(village_id=village_id).first()
    if a is None:
        raise ItineraireIntrouvable("Ce village n'est pas rattaché au réseau routier (GPS manquant ?).")
    return {'troncon_id': a.troncon_id, 'fraction': a.fraction, 'distance_m': a.distance_m,
            'lon': float(a.longitude), 'lat': float(a.latitude),
            'village_lon': float(a.village.longitude), 'village_lat': float(a.village.latitude),
            'nom': a.village.nom_village}


def acces_villages(village_ids):
    """{village_id: acces} pour plusieurs villages en une requête (les villages sans accès sont absents)."""
    out = {}
    for a in VillageAccesRoute.objects.select_related('village').filter(village_id__in=list(village_ids)):
        out[a.village_id] = {
            'troncon_id': a.troncon_id, 'fraction': a.fraction, 'distance_m': a.distance_m,
            'lon': float(a.longitude), 'lat': float(a.latitude),
            'village_lon': float(a.village.longitude), 'village_lat': float(a.village.latitude),
            'nom': a.village.nom_village}
    return out


def itineraire_villages(depart_id, arrivee_id, critere='temps', profil=PROFIL_DEFAUT):
    a, b = acces_village(depart_id), acces_village(arrivee_id)
    res = reseau().itineraire(a, b, critere, profil)
    res['depart'], res['arrivee'] = a['nom'], b['nom']
    return res
