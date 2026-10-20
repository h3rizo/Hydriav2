"""Tournées d'agent : ordre optimal des visites et itinéraire réel entre chaque étape.

À partir d'un village de départ et d'une liste de villages à visiter, on calcule les trajets
routiers entre toutes les paires (un seul plus court chemin par village de départ), puis on
cherche l'ordre qui minimise le temps (ou la distance) total :
  * jusqu'à `MAX_EXACT` étapes : solution exacte (Held-Karp, programmation dynamique) ;
  * au-delà : plus proche voisin amélioré par 2-opt (très bon en pratique, pas garanti optimal).
Les étapes inaccessibles par le réseau sont signalées à part et exclues du calcul.
"""
from itertools import combinations

from . import itineraire as it

MAX_EXACT = 11        # 2^11 * 11^2 : instantané
MAX_ETAPES = 30       # au-delà, la matrice complète devient inutilement lourde
INF = 1e15


class TourneeInvalide(Exception):
    pass


def _cout(r, critere):
    if r is None:
        return INF
    return r['duree_s'] if critere == 'temps' else r['distance_m']


def matrice(ids, critere='temps', profil=it.PROFIL_DEFAUT):
    """Retourne (acces, trajets) : trajets[(i, j)] = résultat d'itinéraire, ou None si aucun chemin."""
    acces = it.acces_villages(ids)
    reseau = it.reseau()
    H = reseau.G.copy()
    trajets = {}
    for i in ids:
        if i not in acces:
            continue
        cibles = {j: acces[j] for j in ids if j != i and j in acces}
        for j, r in reseau.itineraires_depuis(acces[i], cibles, critere, H=H, profil=profil).items():
            trajets[(i, j)] = None if isinstance(r, Exception) else r
    return acces, trajets


def _held_karp(depart, etapes, cout, retour):
    n = len(etapes)
    dp = {}
    for k in range(n):
        dp[(1 << k, k)] = (cout(depart, etapes[k]), -1)
    for taille in range(2, n + 1):
        for sous in combinations(range(n), taille):
            masque = sum(1 << k for k in sous)
            for k in sous:
                prec = masque ^ (1 << k)
                meilleur = (INF * 10, -1)
                for m in sous:
                    if m == k:
                        continue
                    c = dp[(prec, m)][0] + cout(etapes[m], etapes[k])
                    if c < meilleur[0]:
                        meilleur = (c, m)
                dp[(masque, k)] = meilleur
    plein = (1 << n) - 1
    fin = min(range(n), key=lambda k: dp[(plein, k)][0] + (cout(etapes[k], depart) if retour else 0))
    ordre, masque, k = [], plein, fin
    while k != -1:
        ordre.append(etapes[k])
        masque, k = masque ^ (1 << k), dp[(masque, k)][1]
    return ordre[::-1]


def _longueur(depart, ordre, cout, retour):
    pts = [depart] + list(ordre) + ([depart] if retour else [])
    return sum(cout(a, b) for a, b in zip(pts, pts[1:]))


def _plus_proche_voisin_2opt(depart, etapes, cout, retour):
    restant, ordre, courant = list(etapes), [], depart
    while restant:
        suivant = min(restant, key=lambda e: cout(courant, e))
        ordre.append(suivant)
        restant.remove(suivant)
        courant = suivant
    ameliore = True
    while ameliore:
        ameliore = False
        base = _longueur(depart, ordre, cout, retour)
        for i in range(len(ordre) - 1):
            for j in range(i + 1, len(ordre)):
                essai = ordre[:i] + ordre[i:j + 1][::-1] + ordre[j + 1:]
                c = _longueur(depart, essai, cout, retour)
                if c < base - 1e-9:
                    ordre, base, ameliore = essai, c, True
    return ordre


def ordre_optimal(depart, etapes, cout, retour=True):
    """Ordre de visite minimisant le coût total. `cout(a, b)` : coût du trajet a -> b."""
    if len(etapes) <= 1:
        return list(etapes)
    if len(etapes) <= MAX_EXACT:
        return _held_karp(depart, etapes, cout, retour)
    return _plus_proche_voisin_2opt(depart, etapes, cout, retour)


def calculer(depart_id, etapes_ids, retour=True, critere='temps', profil=it.PROFIL_DEFAUT):
    """Tournée optimisée.

    `etapes_ids` est pris dans l'ordre « naturel » (ex. ordre du planning) : il sert de référence pour
    mesurer le gain de l'optimisation. Retourne un dict (voir clés ci-dessous) ou lève TourneeInvalide.
    """
    if critere not in it.CRITERES:
        raise TourneeInvalide('Critère invalide.')
    if profil not in it.PROFILS_VALIDES:
        raise TourneeInvalide('Profil de déplacement invalide.')
    vus, etapes = set(), []
    for e in etapes_ids:
        if e != depart_id and e not in vus:
            vus.add(e)
            etapes.append(e)
    if len(etapes) > MAX_ETAPES:
        raise TourneeInvalide(f"Trop d'étapes ({len(etapes)}) : maximum {MAX_ETAPES}.")

    acces, trajets = matrice([depart_id] + etapes, critere, profil)
    if depart_id not in acces:
        raise TourneeInvalide("Le village de départ n'est pas rattaché au réseau routier.")
    sans_acces = [e for e in etapes if e not in acces]
    joignables = [e for e in etapes if e in acces and trajets.get((depart_id, e)) is not None]
    inaccessibles = sans_acces + [e for e in etapes if e in acces and e not in joignables]

    def cout(a, b):
        return _cout(trajets.get((a, b)), critere)

    ordre = ordre_optimal(depart_id, joignables, cout, retour)
    reference = [e for e in etapes if e in joignables]

    def total(seq):
        pts = [depart_id] + list(seq) + ([depart_id] if retour else [])
        return (sum((trajets[(a, b)] or {'distance_m': 0})['distance_m'] for a, b in zip(pts, pts[1:])),
                sum((trajets[(a, b)] or {'duree_s': 0})['duree_s'] for a, b in zip(pts, pts[1:])))

    pts = [depart_id] + ordre + ([depart_id] if retour else [])
    legs = []
    for a, b in zip(pts, pts[1:]):
        r = trajets[(a, b)]
        legs.append({'de': a, 'vers': b, 'distance_m': r['distance_m'], 'duree_s': r['duree_s'],
                     'geometrie': r['geometrie'], 'repartition_m': r['repartition_m']})
    dist, duree = total(ordre)
    dist_ref, duree_ref = total(reference)
    return {
        'depart': depart_id, 'ordre': ordre, 'retour': retour, 'critere': critere, 'profil': profil, 'legs': legs,
        'distance_m': dist, 'duree_s': duree,
        'reference': {'distance_m': dist_ref, 'duree_s': duree_ref},
        'gain_distance_m': max(0.0, dist_ref - dist), 'gain_duree_s': max(0.0, duree_ref - duree),
        'inaccessibles': inaccessibles, 'acces': acces,
    }
