"""Création d'un village en cliquant sur la carte.

Trois outils :
  * `lieu_du_point` : devine fokontany / commune / district / région d'un point d'après les contours importés
    (polygones des shapefiles) et retrouve les objets correspondants de la base ;
  * `lister` : listes en cascade (régions, puis districts d'une région, communes d'un district, fokontany d'une commune) ;
  * `creer_village` : crée le village et le rattache au réseau routier (`VillageAccesRoute`) pour qu'il soit tout de suite
    routable et apparaisse dans les villages éloignés de toute route s'il l'est.
"""
from decimal import Decimal

from django.db import transaction
from shapely.geometry import Point, shape

from apps.geography.models import Commune, District, Fokontany, Region, Village
from apps.geography.models_contours import ContourAdmin
from apps.geography.models_routes import TronconRoute, VillageAccesRoute

from .contours_communes import normaliser
from .coupures import _graphe
from .lieux import acces_point, dans_madagascar
from .itineraire import ItineraireIntrouvable
from .reseau_routier import haversine_m

NIVEAUX = ('region', 'district', 'commune', 'fokontany')
DISTANCE_DOUBLON_M = 100.0


class VillageInvalide(Exception):
    pass


class VillageProche(Exception):
    """Des villages existent déjà à moins de 100 m : l'utilisateur doit confirmer."""
    def __init__(self, proches):
        super().__init__('Des villages existent déjà tout près.')
        self.proches = proches


# --------------------------------------------------------------------------------------------- cascade

def lister(niveau, parent=None):
    """[{id, nom}] triés par nom : régions, ou enfants du niveau supérieur (`parent` = id du parent)."""
    if niveau == 'region':
        qs = Region.objects.all().order_by('nom_region').values_list('id', 'nom_region')
    elif niveau == 'district':
        qs = District.objects.filter(region_id=parent).order_by('nom_district').values_list('id', 'nom_district')
    elif niveau == 'commune':
        qs = Commune.objects.filter(district_id=parent).order_by('nom_commune').values_list('id', 'nom_commune')
    elif niveau == 'fokontany':
        qs = Fokontany.objects.filter(commune_id=parent).order_by('nom_fokontany').values_list('id', 'nom_fokontany')
    else:
        raise VillageInvalide('Niveau invalide.')
    return [{'id': str(pk), 'nom': nom} for pk, nom in qs]


# --------------------------------------------------------------------------------------------- détection

def _contour_contenant(niveau, lon, lat):
    """Contour du niveau qui contient le point (rectangle englobant d'abord, puis géométrie fine), ou None."""
    p = Point(lon, lat)
    candidats = ContourAdmin.objects.filter(niveau=niveau, ouest__lte=lon, est__gte=lon, sud__lte=lat, nord__gte=lat)
    for k in candidats:
        try:
            if shape(k.geometrie).buffer(0).contains(p):
                return k
        except Exception:
            continue
    return None


def _trouver(modele, champ, nom, **filtres):
    """Id de l'objet de la base de ce nom (sans accents), s'il est unique parmi ceux du parent."""
    cible = normaliser(nom)
    memes = [o for o in modele.objects.filter(**filtres) if normaliser(getattr(o, champ)) == cible]
    return memes[0].pk if len(memes) == 1 else None


def lieu_du_point(lon, lat):
    """Hiérarchie administrative d'un point d'après les contours, avec les ids de la base quand ils existent.

    Retourne {niveau: {'nom': str, 'id': str | None}} pour les niveaux trouvés ; {} si le point est hors de tout contour.
    """
    contours = {n: _contour_contenant(n, lon, lat) for n in NIVEAUX}
    # Les noms des niveaux supérieurs peuvent venir d'un contour plus fin (le fokontany porte commune/district/région).
    fin = next((k for k in (contours['fokontany'], contours['commune'], contours['district'], contours['region']) if k), None)
    if fin is None:
        return {}
    noms = {
        'region': (contours['region'] and contours['region'].nom) or fin.region_nom,
        'district': (contours['district'] and contours['district'].nom) or fin.district_nom,
        'commune': (contours['commune'] and contours['commune'].nom) or fin.commune_nom or '',
        'fokontany': contours['fokontany'].nom if contours['fokontany'] else '',
    }
    lieu, parent = {}, None
    for niveau, modele, champ, filtre in (('region', Region, 'nom_region', None), ('district', District, 'nom_district', 'region_id'),
                                          ('commune', Commune, 'nom_commune', 'district_id'), ('fokontany', Fokontany, 'nom_fokontany', 'commune_id')):
        nom = noms[niveau]
        if not nom:
            continue
        k = contours[niveau]
        identifiant = k.objet_id if k is not None and k.objet_id else (
            _trouver(modele, champ, nom, **({filtre: parent} if filtre and parent else {})) if (parent or niveau == 'region') else None)
        lieu[niveau] = {'nom': nom, 'id': str(identifiant) if identifiant else None}
        parent = identifiant
    return lieu


# --------------------------------------------------------------------------------------------- création

def _villages_proches(lon, lat, rayon_m=DISTANCE_DOUBLON_M):
    marge = rayon_m / 111000 * 1.5
    candidats = (Village.objects.filter(longitude__range=(lon - marge, lon + marge), latitude__range=(lat - marge, lat + marge))
                 .select_related('fokontany'))
    proches = []
    for v in candidats:
        d = haversine_m(lon, lat, float(v.longitude), float(v.latitude))
        if d <= rayon_m:
            proches.append({'id': str(v.id), 'nom': v.nom_village, 'distance_m': round(d),
                            'fokontany': v.fokontany.nom_fokontany if v.fokontany_id else ''})
    return sorted(proches, key=lambda x: x['distance_m'])


@transaction.atomic
def creer_village(nom, fokontany_id, lon, lat, confirmer_proches=False):
    """Crée le village et son accès au réseau routier. Retourne {'village', 'distance_route_m'}."""
    nom = (nom or '').strip()
    if not nom:
        raise VillageInvalide('Le nom du village est obligatoire.')
    if len(nom) > 255:
        raise VillageInvalide('Nom trop long (255 caractères maximum).')
    if not dans_madagascar(lon, lat):
        raise VillageInvalide('Position hors de Madagascar.')
    fokontany = Fokontany.objects.filter(pk=fokontany_id).select_related('commune__district__region').first()
    if fokontany is None:
        raise VillageInvalide('Choisis le fokontany de rattachement.')
    if any(normaliser(v) == normaliser(nom) for v in Village.objects.filter(fokontany=fokontany).values_list('nom_village', flat=True)):
        raise VillageInvalide(f"Un village « {nom} » existe déjà dans le fokontany {fokontany.nom_fokontany}.")
    proches = _villages_proches(lon, lat)
    if proches and not confirmer_proches:
        raise VillageProche(proches)

    village = Village.objects.create(nom_village=nom, fokontany=fokontany,
                                     latitude=Decimal(f'{lat:.7f}'), longitude=Decimal(f'{lon:.7f}'))
    distance = None
    try:
        a = acces_point(lon, lat, nom=nom)
        troncon = TronconRoute.objects.only('noeud_debut_id').get(pk=a['troncon_id'])
        comps = _graphe()
        VillageAccesRoute.objects.create(
            village=village, troncon_id=a['troncon_id'], fraction=a['fraction'], distance_m=a['distance_m'],
            longitude=Decimal(f"{a['lon']:.7f}"), latitude=Decimal(f"{a['lat']:.7f}"),
            reseau_principal=bool(comps) and troncon.noeud_debut_id in comps[0])
        distance = round(a['distance_m'])
    except (ItineraireIntrouvable, TronconRoute.DoesNotExist):
        pass                                   # pas de réseau chargé : le village est créé sans accès routier
    return {'village': village, 'distance_route_m': distance}
