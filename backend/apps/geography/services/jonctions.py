"""Jonctions manquantes du réseau routier.

Une jonction est « suspecte » quand un nœud du réseau est tout près (quelques mètres à
quelques centaines de mètres) d'une autre route sans qu'on puisse l'y rejoindre par le
réseau en moins de `ecart_m` mètres : les deux routes devraient probablement se toucher.

  * `chercher`        : liste les candidats (pour contrôle manuel ou réparation) ;
  * `relier`          : crée le tronçon de jonction (en découpant la route visée si besoin) ;
  * `nettoyer_auto`   : relie automatiquement tous les écarts <= `tol_m`, du plus petit au plus grand.
"""
from collections import namedtuple

import networkx as nx
from django.db import transaction
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from apps.geography.models_routes import NoeudRoute, TronconRoute

from .coupures import _decouper
from .reseau_routier import haversine_m, longueur_geodesique_m

M_PAR_DEGRE = 111_000.0
INF = float('inf')

Donnees = namedtuple('Donnees', 'G coords lignes tids debuts fins longueurs arbre')


def charger():
    """Charge le réseau en mémoire : graphe pondéré par la longueur + géométries."""
    G = nx.Graph()
    tids, lignes, debuts, fins, longueurs = [], [], [], [], []
    for tid, a, b, geom, longueur in TronconRoute.objects.values_list(
            'id', 'noeud_debut_id', 'noeud_fin_id', 'geometrie', 'longueur_m'):
        if a == b:
            continue
        tids.append(tid)
        lignes.append(LineString(geom))
        debuts.append(a)
        fins.append(b)
        longueurs.append(longueur)
        if not G.has_edge(a, b) or G[a][b]['longueur'] > longueur:
            G.add_edge(a, b, longueur=longueur)
    coords = {n.id: (float(n.longitude), float(n.latitude))
              for n in NoeudRoute.objects.filter(id__in=list(G.nodes))}
    return Donnees(G, coords, lignes, tids, debuts, fins, longueurs, STRtree(lignes))


def chercher(data, rayon_m=250.0, ecart_m=3000.0):
    """Candidats de jonction, du plus proche au plus éloigné."""
    rayon_deg = rayon_m / M_PAR_DEGRE
    resultat = []
    for noeud_id, xy in data.coords.items():
        p = Point(xy)
        proches = []
        for idx in data.arbre.query(p.buffer(rayon_deg)):
            idx = int(idx)
            if noeud_id in (data.debuts[idx], data.fins[idx]):
                continue
            ligne = data.lignes[idx]
            q = nearest_points(ligne, p)[0]
            d = haversine_m(p.x, p.y, q.x, q.y)
            if d <= rayon_m:
                proches.append((d, idx, ligne.project(q, normalized=True), q))
        if not proches:
            continue
        atteints = nx.single_source_dijkstra_path_length(data.G, noeud_id, cutoff=ecart_m, weight='longueur')
        for d, idx, f, q in proches:
            L = data.longueurs[idx]
            par_reseau = min(atteints.get(data.debuts[idx], INF) + f * L,
                             atteints.get(data.fins[idx], INF) + (1 - f) * L)
            if par_reseau <= ecart_m:
                continue
            resultat.append({
                'noeud_id': noeud_id, 'troncon_id': data.tids[idx], 'fraction': f,
                'distance_m': d, 'from': list(xy), 'to': [q.x, q.y], 'idx': idx,
            })
    resultat.sort(key=lambda c: c['distance_m'])
    return resultat


@transaction.atomic
def relier(noeud_id, troncon_id, fraction, snap_m=3.0):
    """Relie `noeud_id` au point `fraction` du tronçon visé ; retourne le tronçon de jonction.

    Si le nœud se trouve déjà exactement sur la route, la découpe suffit à les relier : on
    retourne alors None (aucun tronçon de jonction n'est nécessaire).
    """
    noeud = NoeudRoute.objects.get(id=noeud_id)
    t = TronconRoute.objects.select_related('noeud_debut', 'noeud_fin').get(id=troncon_id)
    q = LineString(t.geometrie).interpolate(fraction, normalized=True)
    for n in (t.noeud_debut, t.noeud_fin):
        if haversine_m(float(n.longitude), float(n.latitude), q.x, q.y) <= snap_m:
            cible = n
            break
    else:
        cible = _decouper(t, fraction)
    if cible.id == noeud.id:
        return None
    trace = [[float(noeud.longitude), float(noeud.latitude)], [float(cible.longitude), float(cible.latitude)]]
    return TronconRoute.objects.create(
        nom='Jonction', type_voie='jonction', categorie='autre', source='raccord',
        noeud_debut=noeud, noeud_fin=cible, geometrie=trace, longueur_m=longueur_geodesique_m(trace))


def nettoyer_auto(tol_m=25.0, ecart_m=3000.0, passes=3, dry_run=False, log=None):
    """Relie les jonctions dont l'écart est <= tol_m. Retourne le nombre de jonctions créées."""
    total = 0
    for numero in range(1, passes + 1):
        data = charger()
        candidats = chercher(data, rayon_m=tol_m, ecart_m=ecart_m)
        touches, faits = set(), 0
        for c in candidats:
            if c['troncon_id'] in touches:     # déjà découpé/modifié pendant cette passe : repris à la suivante
                continue
            idx, G = c['idx'], data.G
            L, f = data.longueurs[idx], c['fraction']
            da, db = data.debuts[idx], data.fins[idx]
            atteints = nx.single_source_dijkstra_path_length(G, c['noeud_id'], cutoff=ecart_m, weight='longueur')
            if min(atteints.get(da, INF) + f * L, atteints.get(db, INF) + (1 - f) * L) <= ecart_m:
                continue                         # une jonction précédente a déjà réglé ce cas
            if not dry_run:
                relier(c['noeud_id'], c['troncon_id'], f)
                touches.add(c['troncon_id'])
            # Mise à jour approchée du graphe en mémoire pour ne pas créer de doublons.
            d = c['distance_m']
            G.add_edge(c['noeud_id'], da, longueur=d + f * L)
            G.add_edge(c['noeud_id'], db, longueur=d + (1 - f) * L)
            faits += 1
        total += faits
        if log:
            log(f"[INFO] Passe {numero} : {faits} jonction(s){' (simulation)' if dry_run else ''}")
        if not faits or dry_run:
            break
    return total
