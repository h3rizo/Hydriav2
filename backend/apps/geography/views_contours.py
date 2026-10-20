"""API GeoJSON des contours administratifs (région, district, commune, fokontany), chargés par zone visible.

Les polygones viennent de `ContourAdmin` (import des shapefiles) : aucune dépendance à PostGIS. La population et
le nombre de villages ne sont calculés que pour les contours reliés à un objet de la base (`objet_id`).
"""
from django.db.models import Count, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Commune, District, Fokontany, Region
from .models_contours import ContourAdmin

MAX_CONTOURS = 3000
# Au-dessus de ce zoom on sert la géométrie détaillée, en dessous la version très simplifiée.
ZOOM_DETAIL = {'region': 8, 'district': 9, 'commune': 10, 'fokontany': 12}

_MODELES = {'region': Region, 'district': District, 'commune': Commune, 'fokontany': Fokontany}
_VILLAGES = {
    'region': 'districts__communes__fokontanys__villages',
    'district': 'communes__fokontanys__villages',
    'commune': 'fokontanys__villages',
    'fokontany': 'villages',
}


def _stats(niveau, ids):
    """{objet_id: (population, nb_villages)} pour les objets de la base reliés aux contours renvoyés."""
    if not ids:
        return {}
    chemin = _VILLAGES[niveau]
    lignes = (_MODELES[niveau].objects.filter(pk__in=ids)
              .annotate(population=Sum(f'{chemin}__parcelles__nombre_habitants'),
                        nb_villages=Count(chemin, distinct=True))
              .values_list('pk', 'population', 'nb_villages'))
    return {pk: (population, nb) for pk, population, nb in lignes}


def contours_features(niveau, bbox=None, zoom=None, limite=MAX_CONTOURS):
    """(features GeoJSON, tronqué ?) des contours d'un niveau dans une zone (ouest, sud, est, nord)."""
    qs = ContourAdmin.objects.filter(niveau=niveau)
    if bbox:
        ouest, sud, est, nord = bbox
        qs = qs.filter(ouest__lte=est, est__gte=ouest, sud__lte=nord, nord__gte=sud)
    contours = list(qs.order_by('nom')[:limite + 1])
    tronque = len(contours) > limite
    contours = contours[:limite]
    fin = zoom is not None and zoom >= ZOOM_DETAIL[niveau]
    stats = _stats(niveau, [k.objet_id for k in contours if k.objet_id])

    features = []
    for k in contours:
        population, nb_villages = stats.get(k.objet_id, (None, None))
        features.append({
            'type': 'Feature',
            'properties': {
                'id': k.cle, 'niveau': niveau, 'nom': k.nom, 'code': k.p_code,
                'commune': k.commune_nom or None, 'district': k.district_nom or None, 'region': k.region_nom or None,
                'type_admin': k.type_admin or None, 'inter_aide': k.inter_aide or None, 'enclave': k.enclave or None,
                'accessibilite': k.accessibilite or None, 'statut_soakoja': k.statut_soakoja or None,
                'ouvrages': k.ouvrages or None, 'superficie_km2': round(k.superficie_km2, 1) if k.superficie_km2 else None,
                'en_base': k.objet_id is not None, 'population': population, 'nb_villages': nb_villages,
            },
            'geometry': k.geometrie if fin else k.geometrie_simple,
        })
    return features, tronque


def _lire_bbox(texte):
    try:
        ouest, sud, est, nord = (float(v) for v in texte.split(','))
    except (ValueError, AttributeError):
        return None
    return ouest, sud, est, nord


@api_view(['GET'])
@permission_classes([AllowAny])
def api_geojson_contours(request):
    """?niveau=region|district|commune|fokontany&bbox=ouest,sud,est,nord&zoom=N

    Sans bbox on renvoie tout le niveau (raisonnable pour région, district et commune ; pour les fokontany
    — 17 000 polygones — la zone est obligatoire).
    """
    niveau = request.GET.get('niveau', '')
    if niveau not in _MODELES:
        return Response({'error': 'niveau invalide (region, district, commune, fokontany).'}, status=400)
    bbox = _lire_bbox(request.GET.get('bbox')) if request.GET.get('bbox') else None
    if request.GET.get('bbox') and bbox is None:
        return Response({'error': 'bbox invalide (ouest,sud,est,nord).'}, status=400)
    if niveau == 'fokontany' and bbox is None:
        return Response({'error': 'bbox requis pour les fokontany.'}, status=400)
    try:
        zoom = float(request.GET['zoom']) if 'zoom' in request.GET else None
    except ValueError:
        return Response({'error': 'zoom invalide.'}, status=400)
    features, tronque = contours_features(niveau, bbox, zoom)
    return Response({'type': 'FeatureCollection', 'features': features, 'tronque': tronque,
                     'nb_total': ContourAdmin.objects.filter(niveau=niveau).count()})
