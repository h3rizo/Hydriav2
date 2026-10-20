"""Calcul des itinéraires routiers des liaisons entre villages.

Pour chaque liaison on enregistre le tracé réel (courbe), la distance et la durée par la route.
Les valeurs saisies à la main (`distance_km`, `temps_acces_minutes`) ne sont jamais écrasées
sauf demande explicite (`forcer_distances`) ; elles sont seulement complétées quand elles sont vides.
"""
from collections import Counter, defaultdict
from decimal import Decimal

from django.db.models import Max, Q
from django.utils import timezone
from shapely.geometry import LineString

from apps.geography.models import LiaisonVillage
from apps.geography.models_routes import TronconRoute

from . import itineraire as it
from .reseau_routier import haversine_m
from .voies_config import PROFIL_DEFAUT, PROFIL_PAR_MOYEN_ACCES

CHAMPS = ['trace_route', 'distance_route_km', 'duree_route_min', 'route_statut', 'route_calculee_le',
          'distance_km', 'temps_acces_minutes']


def hors_route(liaison):
    return liaison.type_route == 'riviere' or liaison.moyen_acces == 'pirogue'


def profil_de(liaison):
    """Profil de déplacement d'une liaison : son moyen d'accès, moto par défaut."""
    return PROFIL_PAR_MOYEN_ACCES.get(liaison.moyen_acces or '', PROFIL_DEFAUT)


def _distance_vol_oiseau_km(liaison):
    """Distance à vol d'oiseau en km, arrondie à 0,01 (celle que le remplissage automatique d'origine
    écrit dans distance_km), ou None si un des villages n'a pas de GPS."""
    s, c = liaison.village_source, liaison.village_cible
    if None in (s.latitude, s.longitude, c.latitude, c.longitude):
        return None
    return round(haversine_m(float(s.longitude), float(s.latitude), float(c.longitude), float(c.latitude)) / 1000, 2)


def _proche(a, b, tolerance):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tolerance


def distance_est_automatique(liaison):
    """Vrai si distance_km n'est pas une saisie manuelle : vide, ou valeur générée automatiquement
    (distance à vol d'oiseau du premier remplissage, ou ancienne distance par la route)."""
    d = liaison.distance_km
    return d is None or _proche(d, _distance_vol_oiseau_km(liaison), 0.02) or _proche(d, liaison.distance_route_km, 0.011)


def temps_est_automatique(liaison):
    """Vrai si temps_acces_minutes est vide ou égal à l'ancienne durée par la route (donc non saisi à la main)."""
    t = liaison.temps_acces_minutes
    return t is None or (liaison.duree_route_min is not None and t == liaison.duree_route_min)


def liaisons_a_recalculer():
    """Liaisons jamais calculées, ou calculées avant la dernière modification du réseau."""
    dernier = TronconRoute.objects.aggregate(m=Max('updated_at'))['m']
    q = Q(route_calculee_le__isnull=True)
    if dernier:
        q |= Q(route_calculee_le__lt=dernier)
    return LiaisonVillage.objects.filter(q)


TOLERANCE_SIMPLIFICATION_DEG = 2e-5   # ~2 m : invisible à l'écran, divise la taille des tracés par 3 à 5


def simplifier(points):
    """Douglas-Peucker en gardant les extrémités ; coordonnées arrondies à ~10 cm."""
    if len(points) <= 2:
        return points
    ligne = LineString(points).simplify(TOLERANCE_SIMPLIFICATION_DEG, preserve_topology=False)
    return [[round(x, 6), round(y, 6)] for x, y in ligne.coords]


def _appliquer(liaison, statut, res, maintenant, forcer_distances):
    liaison.route_statut = statut
    liaison.route_calculee_le = maintenant
    if statut != 'ok':
        liaison.trace_route = liaison.distance_route_km = liaison.duree_route_min = None
        return
    km = res['distance_m'] / 1000
    minutes = max(1, round(res['duree_s'] / 60))
    # Valeurs générées automatiquement (distance à vol d'oiseau, ancien calcul) : remplacées par le calcul actuel.
    # Une valeur saisie à la main n'est jamais touchée, sauf avec --forcer-distances.
    remplacer_distance = forcer_distances or distance_est_automatique(liaison)
    remplacer_temps = forcer_distances or temps_est_automatique(liaison)
    liaison.trace_route = simplifier(res['geometrie'])
    liaison.distance_route_km = round(km, 2)
    liaison.duree_route_min = minutes
    if remplacer_distance:
        liaison.distance_km = Decimal(f"{km:.2f}")
    if remplacer_temps:
        liaison.temps_acces_minutes = minutes


def calculer(liaisons, critere='temps', forcer_distances=False, dry_run=False):
    """Calcule et enregistre les itinéraires. Retourne un Counter des statuts (ok, introuvable, ignore)."""
    liaisons = list(liaisons)
    stats = Counter()
    if not liaisons:
        return stats
    acces = it.acces_villages({v for l in liaisons for v in (l.village_source_id, l.village_cible_id)})
    reseau = it.reseau()
    maintenant = timezone.now()
    par_source = defaultdict(list)

    for l in liaisons:
        if hors_route(l):
            _appliquer(l, 'ignore', None, maintenant, forcer_distances)
            stats['ignore'] += 1
        elif l.village_source_id not in acces or l.village_cible_id not in acces:
            _appliquer(l, 'introuvable', None, maintenant, forcer_distances)
            stats['introuvable'] += 1
        else:
            par_source[l.village_source_id].append(l)

    H = reseau.G.copy()      # une seule copie pour tout le lot : les nœuds virtuels sont retirés après chaque source
    # Un calcul par (village de départ, profil de déplacement) : le profil vient du moyen d'accès de la liaison.
    par_source_profil = defaultdict(list)
    for source_id, groupe in par_source.items():
        for l in groupe:
            par_source_profil[(source_id, profil_de(l))].append(l)
    for (source_id, profil), groupe in par_source_profil.items():
        resultats = reseau.itineraires_depuis(
            acces[source_id], {l.pk: acces[l.village_cible_id] for l in groupe}, critere, H=H, profil=profil)
        for l in groupe:
            r = resultats[l.pk]
            statut = 'introuvable' if isinstance(r, Exception) else 'ok'
            _appliquer(l, statut, None if statut != 'ok' else r, maintenant, forcer_distances)
            stats[statut] += 1

    if not dry_run:
        LiaisonVillage.objects.bulk_update(liaisons, CHAMPS, batch_size=500)
    return stats


def calculer_une(liaison):
    """Version tolérante pour les écrans : ne lève jamais d'exception (le calcul est facultatif)."""
    try:
        calculer([liaison])
    except Exception:  # réseau absent, base incohérente... la liaison reste simplement en ligne droite
        return False
    return True
