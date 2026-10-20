"""Édition sur la carte : recherche de village, modification d'un village (nom, fokontany, position) et d'un tronçon de route
(déplacer / ajouter / supprimer des sommets, y compris les nœuds partagés aux jonctions).

Cohérence à maintenir quand la géométrie change :
  * un nœud déplacé entraîne tous les tronçons qui s'y rattachent (premier / dernier point de leur géométrie) ;
  * `longueur_m` est recalculée ;
  * les accès des villages (`VillageAccesRoute`) stockent une fraction le long du tronçon : ils sont reprojetés.
"""
from decimal import Decimal

from django.db import transaction
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from apps.geography.models import Fokontany, Village
from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute

from .contours_communes import normaliser
from .coupures import _graphe
from .lieux import acces_point, dans_madagascar
from .itineraire import ItineraireIntrouvable
from .reseau_routier import haversine_m, longueur_geodesique_m
from .trace_libre import CATEGORIES_LIGNE, MAX_POINTS
from .villages_carte import VillageInvalide, VillageProche, _villages_proches, lieu_du_point


class EditionInvalide(Exception):
    pass


# --------------------------------------------------------------------------------------------- villages

def _fiche(v):
    return {'id': str(v.id), 'nom': v.nom_village,
            'lon': float(v.longitude) if v.longitude is not None else None,
            'lat': float(v.latitude) if v.latitude is not None else None,
            'fokontany': v.fokontany.nom_fokontany if v.fokontany_id else '',
            'commune': v.fokontany.commune.nom_commune if v.fokontany_id and v.fokontany.commune_id else ''}


def rechercher_villages(q, limite=15):
    """Villages dont le nom contient `q` (sans tenir compte des accents ni de la casse), ceux qui commencent par `q` d'abord."""
    cible = normaliser(q or '')
    if len(cible) < 2:
        return []
    base = (Village.objects.filter(latitude__isnull=False, longitude__isnull=False)
            .select_related('fokontany__commune').order_by('nom_village'))
    trouves = [v for v in base.filter(nom_village__icontains=q.strip()[:60])[:200]]
    if len(trouves) < limite:                       # repli sans accents sur l'ensemble des noms
        deja = {v.pk for v in trouves}
        trouves += [v for v in base if v.pk not in deja and cible in normaliser(v.nom_village)][:200]
    trouves.sort(key=lambda v: (not normaliser(v.nom_village).startswith(cible), normaliser(v.nom_village)))
    return [_fiche(v) for v in trouves[:limite]]


def villages_zone(ouest, sud, est, nord, limite=600):
    """Villages géolocalisés dans un rectangle (pour les afficher et les choisir sur la carte). Retourne (liste, tronque)."""
    qs = (Village.objects.filter(longitude__range=(ouest, est), latitude__range=(sud, nord))
          .order_by('nom_village').values_list('id', 'nom_village', 'longitude', 'latitude')[:limite + 1])
    lignes = list(qs)
    return ([{'id': str(i), 'nom': n, 'lon': float(lo), 'lat': float(la)} for i, n, lo, la in lignes[:limite]], len(lignes) > limite)


def detail_village(village_id):
    v = Village.objects.select_related('fokontany__commune__district__region').filter(pk=village_id).first()
    if v is None:
        raise EditionInvalide('Village introuvable.')
    d = _fiche(v)
    f = v.fokontany
    d['hierarchie'] = {} if f is None else {
        'region': {'id': str(f.commune.district.region_id), 'nom': f.commune.district.region.nom_region},
        'district': {'id': str(f.commune.district_id), 'nom': f.commune.district.nom_district},
        'commune': {'id': str(f.commune_id), 'nom': f.commune.nom_commune},
        'fokontany': {'id': str(f.id), 'nom': f.nom_fokontany}}
    acces = VillageAccesRoute.objects.filter(village=v).first()
    d['distance_route_m'] = round(acces.distance_m) if acces else None
    return d


@transaction.atomic
def modifier_village(village_id, nom, fokontany_id, lon, lat, confirmer_proches=False):
    """Met à jour nom / fokontany / position, et recalcule l'accès au réseau si la position change."""
    v = Village.objects.select_for_update(of=('self',)).filter(pk=village_id).first()
    if v is None:
        raise EditionInvalide('Village introuvable.')
    nom = (nom or '').strip()
    if not nom:
        raise VillageInvalide('Le nom du village est obligatoire.')
    if len(nom) > 255:
        raise VillageInvalide('Nom trop long (255 caractères maximum).')
    if not dans_madagascar(lon, lat):
        raise VillageInvalide('Position hors de Madagascar.')
    fokontany = Fokontany.objects.filter(pk=fokontany_id).first()
    if fokontany is None:
        raise VillageInvalide('Choisis le fokontany de rattachement.')
    autres = Village.objects.filter(fokontany=fokontany).exclude(pk=v.pk).values_list('nom_village', flat=True)
    if any(normaliser(x) == normaliser(nom) for x in autres):
        raise VillageInvalide(f"Un village « {nom} » existe déjà dans le fokontany {fokontany.nom_fokontany}.")

    ancien = (float(v.longitude), float(v.latitude)) if v.longitude is not None and v.latitude is not None else None
    deplace = ancien is None or haversine_m(ancien[0], ancien[1], lon, lat) > 0.5
    if deplace:
        proches = [p for p in _villages_proches(lon, lat) if p['id'] != str(v.id)]
        if proches and not confirmer_proches:
            raise VillageProche(proches)

    v.nom_village, v.fokontany = nom, fokontany
    v.latitude, v.longitude = Decimal(f'{lat:.7f}'), Decimal(f'{lon:.7f}')
    v.save()

    distance = None
    if deplace:
        VillageAccesRoute.objects.filter(village=v).delete()
        try:
            a = acces_point(lon, lat, nom=nom)
            troncon = TronconRoute.objects.only('noeud_debut_id').get(pk=a['troncon_id'])
            comps = _graphe()
            VillageAccesRoute.objects.create(
                village=v, troncon_id=a['troncon_id'], fraction=a['fraction'], distance_m=a['distance_m'],
                longitude=Decimal(f"{a['lon']:.7f}"), latitude=Decimal(f"{a['lat']:.7f}"),
                reseau_principal=bool(comps) and troncon.noeud_debut_id in comps[0])
            distance = round(a['distance_m'])
        except (ItineraireIntrouvable, TronconRoute.DoesNotExist):
            pass
        _invalider_liaisons([v.pk])
    else:
        acces = VillageAccesRoute.objects.filter(village=v).first()
        distance = round(acces.distance_m) if acces else None
    return {'village': v, 'distance_route_m': distance, 'deplace': deplace}


def _invalider_liaisons(village_ids):
    """Marque à recalculer les liaisons routières touchant ces villages (la courbe est périmée)."""
    from django.db.models import Q
    from apps.geography.models import LiaisonVillage
    try:
        LiaisonVillage.objects.filter(Q(village_source_id__in=village_ids) | Q(village_cible_id__in=village_ids)) \
            .update(route_calculee_le=None)
    except Exception:       # le suivi des liaisons est facultatif : ne jamais bloquer l'édition
        pass


# --------------------------------------------------------------------------------------------- tronçons

def detail_troncon(troncon_id):
    t = TronconRoute.objects.select_related('noeud_debut', 'noeud_fin').filter(pk=troncon_id).first()
    if t is None:
        raise EditionInvalide('Tronçon introuvable.')

    def partage(n):
        return (TronconRoute.objects.filter(noeud_debut=n).exclude(pk=t.pk).count()
                + TronconRoute.objects.filter(noeud_fin=n).exclude(pk=t.pk).count())
    return {'id': str(t.id), 'nom': t.nom, 'categorie': t.categorie, 'source': t.source,
            'longueur_m': round(t.longueur_m), 'points': t.geometrie,
            'debut_partage': partage(t.noeud_debut), 'fin_partage': partage(t.noeud_fin)}


def _valider_points(points):
    if not isinstance(points, list) or len(points) < 2:
        raise EditionInvalide('Une route a besoin d\'au moins 2 points.')
    if len(points) > MAX_POINTS:
        raise EditionInvalide('Trop de points.')
    propres = []
    for p in points:
        try:
            lon, lat = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            raise EditionInvalide('Points invalides.')
        if not dans_madagascar(lon, lat):
            raise EditionInvalide('Un point est hors de Madagascar.')
        c = [round(lon, 7), round(lat, 7)]
        if not propres or c != propres[-1]:
            propres.append(c)
    if len(propres) < 2:
        raise EditionInvalide('Les points sont tous identiques.')
    return propres


def _reprojeter_acces(troncon_ids):
    """Recalcule fraction / point projeté / distance des accès de villages sur ces tronçons (géométrie modifiée)."""
    for acces in VillageAccesRoute.objects.filter(troncon_id__in=troncon_ids).select_related('village', 'troncon'):
        v = acces.village
        if v.longitude is None or v.latitude is None:
            continue
        ligne = LineString(acces.troncon.geometrie)
        p = Point(float(v.longitude), float(v.latitude))
        q = nearest_points(ligne, p)[0]
        acces.fraction = ligne.project(q, normalized=True)
        acces.distance_m = haversine_m(p.x, p.y, q.x, q.y)
        acces.longitude, acces.latitude = Decimal(f'{q.x:.7f}'), Decimal(f'{q.y:.7f}')
        acces.save(update_fields=['fraction', 'distance_m', 'longitude', 'latitude', 'updated_at'])
    _invalider_liaisons(list(VillageAccesRoute.objects.filter(troncon_id__in=troncon_ids).values_list('village_id', flat=True)))


def _deplacer_noeud(noeud, lon, lat, touches):
    """Déplace `noeud` ; fusionne avec un nœud déjà présent à l'arrivée. Retourne le nœud final.

    Chaque tronçon rattaché voit son premier/dernier point suivre le nœud ; `touches` reçoit leurs ids.
    """
    cible = (Decimal(f'{lon:.7f}'), Decimal(f'{lat:.7f}'))
    if (noeud.longitude, noeud.latitude) == cible:
        return noeud
    autre = NoeudRoute.objects.filter(longitude=cible[0], latitude=cible[1]).exclude(pk=noeud.pk).first()
    pt = [round(lon, 7), round(lat, 7)]
    if autre is not None:
        TronconRoute.objects.filter(noeud_debut=noeud).update(noeud_debut=autre)
        TronconRoute.objects.filter(noeud_fin=noeud).update(noeud_fin=autre)
        final = autre
        noeud.delete()
    else:
        noeud.longitude, noeud.latitude = cible
        noeud.save()
        final = noeud
    for t in TronconRoute.objects.filter(noeud_debut=final) | TronconRoute.objects.filter(noeud_fin=final):
        g = list(t.geometrie)
        if t.noeud_debut_id == final.pk:
            g[0] = pt
        if t.noeud_fin_id == final.pk:
            g[-1] = pt
        t.geometrie, t.longueur_m = g, longueur_geodesique_m(g)
        t.save()
        touches.add(t.pk)
    return final


@transaction.atomic
def modifier_troncon(troncon_id, points, categorie=None, nom=None):
    """Remplace la géométrie d'un tronçon (sommets déplacés / ajoutés / supprimés).

    Les extrémités sont des nœuds : si elles bougent, le nœud est déplacé et tous les tronçons voisins le suivent.
    """
    t = TronconRoute.objects.select_for_update(of=('self',)).select_related('noeud_debut', 'noeud_fin').filter(pk=troncon_id).first()
    if t is None:
        raise EditionInvalide('Tronçon introuvable.')
    if categorie is not None and categorie not in CATEGORIES_LIGNE + ('autre',):
        raise EditionInvalide('Catégorie inconnue.')
    pts = _valider_points(points)
    if len(pts) == 2 and pts[0] == pts[1]:
        raise EditionInvalide('Une route ne peut pas être un point.')

    touches = {t.pk}
    debut, fin = t.noeud_debut, t.noeud_fin
    if debut.pk == fin.pk:
        raise EditionInvalide('Tronçon bouclé sur un même nœud : non modifiable ici.')
    nouveau_debut = _deplacer_noeud(debut, pts[0][0], pts[0][1], touches)
    # le nœud de fin a pu être fusionné/supprimé si debut==fin cible : on le relit
    fin = NoeudRoute.objects.filter(pk=fin.pk).first() or fin
    nouveau_fin = _deplacer_noeud(fin, pts[-1][0], pts[-1][1], touches)

    t.refresh_from_db()
    if nouveau_debut.pk == nouveau_fin.pk:
        raise EditionInvalide('Le début et la fin se retrouveraient sur le même nœud.')
    t.geometrie, t.longueur_m = pts, longueur_geodesique_m(pts)
    if categorie is not None:
        t.categorie = categorie
    if nom is not None:
        t.nom = nom.strip()[:255]
    t.save()
    _reprojeter_acces(list(touches))
    return {'troncon': t, 'troncons_touches': len(touches)}
