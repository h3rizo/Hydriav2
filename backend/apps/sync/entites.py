"""Registre des types d'entités synchronisées et résolution de leur chemin hiérarchique.

Arborescence territoire (décision Q3 : le fokontany est inclus) :

    Région > District > Commune > Fokontany > Village > Ouvrage > (Équipements | Points d'eau)
    Type d'activité > Activité

Un ouvrage est rangé sous le village de son premier point d'eau géolocalisé (un ouvrage n'a pas de
village propre dans le modèle) ; sans point d'eau localisé, il n'a pas de parent territorial.
"""
from django.apps import apps

# type -> (modèle 'app.Modèle', attribut du nom affiché)
ENTITES = {
    'region': ('geography.Region', 'nom_region'),
    'district': ('geography.District', 'nom_district'),
    'commune': ('geography.Commune', 'nom_commune'),
    'fokontany': ('geography.Fokontany', 'nom_fokontany'),
    'village': ('geography.Village', 'nom_village'),
    'ouvrage': ('organization.Ouvrage', 'nom_ouvrage'),
    'equipement': ('infrastructure.EquipementConstitutif', 'nom'),
    'point_eau': ('billing.PointEau', 'nomabonne'),
    'activite': ('planning.Activite', 'nom'),
}

# Entités dont la visibilité dépend de la gestion de l'ouvrage.
FAMILLE_OUVRAGE = ('ouvrage', 'equipement', 'point_eau')

_CHAINE_GEO = {
    'region': '',
    'district': 'region',
    'commune': 'district__region',
    'fokontany': 'commune__district__region',
    'village': 'fokontany__commune__district__region',
}


def modele(entity_type):
    chemin = ENTITES.get(entity_type)
    return apps.get_model(chemin[0]) if chemin else None


def existe(entity_type, entity_id):
    classe = modele(entity_type)
    if classe is None:
        return False
    try:
        return classe.objects.filter(pk=entity_id).exists()
    except (ValueError, TypeError):
        return False


def _noeud(entity_type, objet):
    return {'type': entity_type, 'id': str(objet.pk), 'nom': str(getattr(objet, ENTITES[entity_type][1]) or '')}


def _chaine_geographique(entity_type, objet):
    """[région, district, commune, fokontany, village] jusqu'à ``entity_type`` inclus."""
    noeuds = []
    courant = objet
    type_courant = entity_type
    parents = {'district': ('region', 'region'), 'commune': ('district', 'district'),
               'fokontany': ('commune', 'commune'), 'village': ('fokontany', 'fokontany')}
    while True:
        noeuds.append(_noeud(type_courant, courant))
        if type_courant not in parents:
            break
        type_courant, attribut = parents[type_courant][0], parents[type_courant][1]
        courant = getattr(courant, attribut)
        if courant is None:
            break
    return list(reversed(noeuds))


def _village_de_ouvrage(ouvrage_id):
    from apps.billing.models import PointEau
    point = (
        PointEau.objects.filter(ouvrage_id=ouvrage_id, parcelle__village__isnull=False)
        .select_related('parcelle__village__fokontany__commune__district__region')
        .order_by('code_point_eau', 'id')
        .first()
    )
    return point.parcelle.village if point else None


def chemin(entity_type, entity_id, cache=None):
    """Liste de nœuds ``{type, id, nom}`` de la racine à l'entité, ou None si elle n'existe plus."""
    cache = {} if cache is None else cache
    cle = (entity_type, str(entity_id))
    if cle in cache:
        return cache[cle]
    cache[cle] = None
    classe = modele(entity_type)
    if classe is None:
        return None

    select = {
        'region': [], 'district': ['region'], 'commune': ['district__region'],
        'fokontany': ['commune__district__region'],
        'village': ['fokontany__commune__district__region'],
        'ouvrage': [], 'equipement': ['ouvrage'], 'point_eau': ['ouvrage', 'parcelle__village'],
        'activite': ['type_activite'],
    }[entity_type]
    try:
        objet = classe.objects.select_related(*select).filter(pk=entity_id).first()
    except (ValueError, TypeError):
        objet = None
    if objet is None:
        return None

    if entity_type in _CHAINE_GEO:
        resultat = _chaine_geographique(entity_type, objet)
    elif entity_type == 'ouvrage':
        village = _village_de_ouvrage(objet.pk)
        resultat = (_chaine_geographique('village', village) if village else []) + [_noeud('ouvrage', objet)]
    elif entity_type == 'equipement':
        parent = chemin('ouvrage', objet.ouvrage_id, cache) if objet.ouvrage_id else []
        resultat = (parent or []) + [_noeud('equipement', objet)]
    elif entity_type == 'point_eau':
        if objet.ouvrage_id:
            parent = chemin('ouvrage', objet.ouvrage_id, cache) or []
        elif objet.parcelle_id and objet.parcelle.village_id:
            parent = chemin('village', objet.parcelle.village_id, cache) or []
        else:
            parent = []
        resultat = parent + [_noeud('point_eau', objet)]
    else:  # activite
        type_activite = objet.type_activite
        resultat = [
            {'type': 'type_activite', 'id': str(type_activite.pk), 'nom': str(type_activite.nomtype or '')},
            _noeud('activite', objet),
        ]
    cache[cle] = resultat
    return resultat
