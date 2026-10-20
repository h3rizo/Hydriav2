"""Lecture des shapefiles administratifs (UTM 38S) -> enregistrements prêts à importer, et rattachement à la base.

Quatre niveaux : région, district, commune, fokontany. Deux sources : le shapefile lui-même (nécessite pyproj pour
passer en WGS84) ou un fichier JSON préparé par `importer_contours --ecrire-json` (aucune dépendance : c'est ce qu'on
envoie sur le serveur, qui n'a pas pyproj).
"""
import json
import os
import re
import unicodedata
from collections import defaultdict

# Tolérances de simplification (degrés) : (fine, simplifiée) ; 0,0001° ≈ 11 m.
TOLERANCES = {
    'region': (0.001, 0.01),
    'district': (0.0005, 0.005),
    'commune': (0.0003, 0.003),
    'fokontany': (0.0002, 0.001),
}
FICHIERS = {'region': 'region', 'district': 'district', 'communes': 'commune', 'commune': 'commune', 'fokontany': 'fokontany'}


def normaliser(texte):
    """Minuscules, sans accents ni ponctuation : « Ambohimangakely-II » == « ambohimangakely ii »."""
    texte = unicodedata.normalize('NFKD', texte or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', texte).strip()


def niveau_depuis_fichier(chemin):
    return FICHIERS.get(os.path.splitext(os.path.basename(chemin))[0].lower())


def _arrondir(coordonnees):
    if isinstance(coordonnees[0], (int, float)):
        return [round(coordonnees[0], 5), round(coordonnees[1], 5)]
    return [_arrondir(c) for c in coordonnees]


def _geojson(geom):
    from shapely.geometry import mapping
    m = mapping(geom)
    return {'type': m['type'], 'coordinates': _arrondir(m['coordinates'])}


def _polygones(geom):
    """Garde uniquement la partie surfacique d'une géométrie réparée (make_valid peut renvoyer une collection)."""
    from shapely.geometry import MultiPolygon, Polygon
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    morceaux = [g for g in getattr(geom, 'geoms', []) if isinstance(g, (Polygon, MultiPolygon))]
    plats = [p for m in morceaux for p in (m.geoms if isinstance(m, MultiPolygon) else [m])]
    return MultiPolygon(plats) if plats else geom


def _champ(attributs, prefixe):
    """Valeur du champ dont le nom commence par `prefixe` (certains noms du .dbf sont mal encodés : « Enclav� »)."""
    for nom, valeur in attributs.items():
        if nom.lower().startswith(prefixe.lower()):
            return valeur.strip() if isinstance(valeur, str) else (valeur or '')
    return ''


def _t(attributs, cle):
    valeur = attributs.get(cle)
    return valeur.strip() if isinstance(valeur, str) else ('' if valeur is None else str(valeur))


def _attributs(niveau, a):
    """Champs communs d'un enregistrement selon le niveau."""
    if niveau == 'region':
        return {'cle': f"{_t(a, 'REG_PCODE')}|{normaliser(_t(a, 'REGION'))}", 'nom': _t(a, 'REGION'), 'p_code': _t(a, 'REG_PCODE'), 'c_code': _t(a, 'R_CODE'),
                'region_nom': _t(a, 'REGION'), 'region_pcode': _t(a, 'REG_PCODE')}
    if niveau == 'district':
        return {'cle': f"{_t(a, 'DIST_PCODE')}|{normaliser(_t(a, 'DISTRICT'))}", 'nom': _t(a, 'DISTRICT'), 'p_code': _t(a, 'DIST_PCODE'), 'c_code': _t(a, 'D_CODE'),
                'district_nom': _t(a, 'DISTRICT'), 'district_pcode': _t(a, 'DIST_PCODE'),
                'region_nom': _t(a, 'REGION'), 'region_pcode': _t(a, 'REG_PCODE'), 'type_admin': _t(a, 'ADMIN')}
    if niveau == 'commune':
        return {'cle': _t(a, 'OBJECTID'), 'nom': _t(a, 'COMMUNE'), 'p_code': _t(a, 'P_CODE'), 'c_code': _t(a, 'C_CODE'),
                'commune_nom': _t(a, 'COMMUNE'), 'district_nom': _t(a, 'DISTRICT'), 'district_pcode': _t(a, 'DIST_PCODE'),
                'region_nom': _t(a, 'REGION'), 'region_pcode': _t(a, 'REG_PCODE'),
                'type_admin': _t(a, 'ADMIN'), 'inter_aide': _t(a, 'INTER_AIDE'),
                'enclave': _champ(a, 'Enclav'), 'accessibilite': _champ(a, 'Accessibil'),
                'statut_soakoja': _t(a, 'Soakoja'), 'ouvrages': _t(a, 'Ouvrages'),
                'superficie_km2': float(a['AREA']) if a.get('AREA') is not None else None}
    return {'cle': _t(a, 'OBJECTID'), 'nom': _t(a, 'FOKONTANY'), 'p_code': _t(a, 'P_CODE'), 'c_code': _t(a, 'C_CODE'),
            'commune_nom': _t(a, 'COMMUNE'), 'district_nom': _t(a, 'DISTRICT'), 'district_pcode': _t(a, 'DIST_PCODE'),
            'region_nom': _t(a, 'REGION'), 'region_pcode': _t(a, 'REG_PCODE'), 'enclave': _champ(a, 'Enclav'),
            'superficie_km2': float(a['AREA']) if a.get('AREA') is not None else None}


def rendre_cles_uniques(enregistrements):
    """Les shapefiles répètent parfois un code ou un OBJECTID (régions au code partagé, district en deux polygones…) :
    la 2e occurrence devient « cle~2 », etc. L'ordre du fichier étant stable, la réimportation retrouve les mêmes clés."""
    vues = defaultdict(int)
    for e in enregistrements:
        vues[e['cle']] += 1
        if vues[e['cle']] > 1:
            e['cle'] = f"{e['cle']}~{vues[e['cle']]}"
    return enregistrements


def lire_shapefile(chemin, niveau):
    """Liste de dicts (un par entité) avec géométries WGS84 simplifiées en deux niveaux. Les formes vides sont ignorées."""
    import shapefile
    from pyproj import CRS, Transformer
    from shapely.geometry import shape
    from shapely.ops import transform
    from shapely.validation import make_valid

    crs = CRS.from_wkt(open(chemin[:-4] + '.prj', encoding='utf-8', errors='ignore').read())
    vers_wgs84 = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True).transform
    fine, simple = TOLERANCES[niveau]

    lecteur = shapefile.Reader(chemin, encoding='utf-8')
    noms = [f[0] for f in lecteur.fields[1:]]
    resultats, ignorees = [], 0
    for i in range(len(lecteur)):
        try:
            geom = shape(lecteur.shape(i).__geo_interface__)
            attributs = dict(zip(noms, lecteur.record(i)))
        except Exception:                      # forme vide ou illisible
            ignorees += 1
            continue
        if geom.is_empty:
            ignorees += 1
            continue
        if not geom.is_valid:
            geom = _polygones(make_valid(geom))
        geom = transform(vers_wgs84, geom)
        ouest, sud, est, nord = geom.bounds
        resultats.append({
            **_attributs(niveau, attributs),
            'geometrie': _geojson(geom.simplify(fine, preserve_topology=True)),
            'geometrie_simple': _geojson(geom.simplify(simple, preserve_topology=True)),
            'ouest': round(ouest, 5), 'sud': round(sud, 5), 'est': round(est, 5), 'nord': round(nord, 5),
        })
    return rendre_cles_uniques(resultats), ignorees


def lire_source(chemin, niveau=None):
    """(niveau, enregistrements, ignorées) depuis un shapefile ou un JSON préparé."""
    if chemin.lower().endswith('.json'):
        with open(chemin, encoding='utf-8') as f:
            contenu = json.load(f)
        return contenu['niveau'], contenu['enregistrements'], 0
    niveau = niveau or niveau_depuis_fichier(chemin)
    if niveau not in TOLERANCES:
        raise ValueError("Niveau inconnu : précisez --niveau region|district|commune|fokontany.")
    enregistrements, ignorees = lire_shapefile(chemin, niveau)
    return niveau, enregistrements, ignorees


def _cles_contour(niveau, k):
    n = normaliser
    if niveau == 'region':
        return [(n(k.nom),)]
    if niveau == 'district':
        return [(n(k.nom), n(k.region_nom)), (n(k.nom),)]
    if niveau == 'commune':
        return [(n(k.nom), n(k.district_nom)), (n(k.nom),)]
    return [(n(k.nom), n(k.commune_nom), n(k.district_nom)), (n(k.nom), n(k.commune_nom)), (n(k.nom),)]


def _objets_base(niveau):
    """[(objet, [clés du plus précis au moins précis])] des objets de la base pour ce niveau."""
    from apps.geography.models import Commune, District, Fokontany, Region
    n = normaliser
    if niveau == 'region':
        return [(o, [(n(o.nom_region),)]) for o in Region.objects.all()]
    if niveau == 'district':
        return [(o, [(n(o.nom_district), n(o.region.nom_region)), (n(o.nom_district),)])
                for o in District.objects.select_related('region')]
    if niveau == 'commune':
        return [(o, [(n(o.nom_commune), n(o.district.nom_district)), (n(o.nom_commune),)])
                for o in Commune.objects.select_related('district')]
    return [(o, [(n(o.nom_fokontany), n(o.commune.nom_commune), n(o.commune.district.nom_district)),
                 (n(o.nom_fokontany), n(o.commune.nom_commune)), (n(o.nom_fokontany),)])
            for o in Fokontany.objects.select_related('commune__district')]


def rattacher(niveau, contours):
    """Renseigne `objet_id` : correspondance de nom la plus précise qui soit unique des deux côtés.

    Retourne {'rattaches': n, 'ambigus': n, 'sans_correspondance': n}.
    """
    objets = _objets_base(niveau)
    contours = list(contours)
    nb_cles = len(_cles_contour(niveau, contours[0])) if contours else 0
    index_base = [defaultdict(list) for _ in range(nb_cles)]
    for objet, cles in objets:
        for i, cle in enumerate(cles):
            index_base[i][cle].append(objet)
    compte_contours = [defaultdict(int) for _ in range(nb_cles)]
    cles_par_contour = {}
    for k in contours:
        cles = _cles_contour(niveau, k)
        cles_par_contour[k.pk] = cles
        for i, cle in enumerate(cles):
            compte_contours[i][cle] += 1

    bilan = {'rattaches': 0, 'ambigus': 0, 'sans_correspondance': 0}
    utilises = set()
    for k in contours:
        trouve, ambigu = None, False
        for i, cle in enumerate(cles_par_contour[k.pk]):
            candidats = index_base[i].get(cle, [])
            if not candidats:
                continue
            if len(candidats) == 1 and compte_contours[i][cle] == 1 and candidats[0].pk not in utilises:
                trouve = candidats[0]
                break
            ambigu = True
        if trouve is None:
            bilan['ambigus' if ambigu else 'sans_correspondance'] += 1
            if k.objet_id is not None:
                k.objet_id = None
                k.save(update_fields=['objet_id', 'updated_at'])
            continue
        utilises.add(trouve.pk)
        if k.objet_id != trouve.pk:
            k.objet_id = trouve.pk
            k.save(update_fields=['objet_id', 'updated_at'])
        bilan['rattaches'] += 1
    return bilan


def contour_commune(commune):
    """Contour importé d'une `Commune` de la base : lien `objet_id`, sinon même nom et même district, sinon nom unique."""
    from apps.geography.models_contours import ContourAdmin

    contours = ContourAdmin.objects.filter(niveau='commune')
    trouve = contours.filter(objet_id=commune.id).first()
    if trouve:
        return trouve
    nom, district = normaliser(commune.nom_commune), normaliser(commune.district.nom_district)
    memes_noms = [k for k in contours.filter(nom__istartswith=commune.nom_commune[:3]) if normaliser(k.nom) == nom]
    exacts = [k for k in memes_noms if normaliser(k.district_nom) == district]
    if len(exacts) == 1:
        return exacts[0]
    return memes_noms[0] if len(memes_noms) == 1 else None


def polygones_commune(commune, max_voisines=20):
    """Features GeoJSON de la commune (selected=True) et de ses voisines : les contours dont le rectangle touche le sien.

    Liste vide si la commune n'a pas de contour importé.
    """
    from apps.geography.models_contours import ContourAdmin

    choisie = contour_commune(commune)
    if choisie is None:
        return []
    voisines = (ContourAdmin.objects.filter(niveau='commune', ouest__lte=choisie.est, est__gte=choisie.ouest,
                                            sud__lte=choisie.nord, nord__gte=choisie.sud)
                .exclude(pk=choisie.pk).order_by('nom')[:max_voisines])

    return [_feature_contour(choisie, 'commune', True)] + [_feature_contour(k, 'commune', False) for k in voisines]


def _feature_contour(k, role, selected=False):
    """Feature GeoJSON d'un contour pour les cartes des pages de détail (`role` : district, commune, fokontany)."""
    details = [f'{libelle} : {valeur}' for libelle, valeur in (
        ('Type', k.type_admin), ('Statut Soakoja', k.statut_soakoja), ('Accessibilité', k.accessibilite),
        ('Enclavée', k.enclave), ("Intervention d'aide", k.inter_aide)) if valeur]
    return {'type': 'Feature',
            'properties': {'id': str(k.objet_id or k.pk), 'nom': k.nom, 'role': role, 'selected': selected,
                           'details': details, 'district': k.district_nom},
            'geometry': k.geometrie}


def _choisir(candidats, par_precision):
    """Premier niveau de précision qui désigne un contour unique (ex. nom + commune, puis nom seul)."""
    for filtre in par_precision:
        retenus = [k for k in candidats if filtre(k)]
        if len(retenus) == 1:
            return retenus[0]
    return None


def contour_fokontany(fokontany):
    """Contour importé d'un `Fokontany` : lien `objet_id`, sinon nom + commune, sinon nom unique."""
    from apps.geography.models_contours import ContourAdmin

    contours = ContourAdmin.objects.filter(niveau='fokontany')
    lie = contours.filter(objet_id=fokontany.id).first()
    if lie:
        return lie
    nom, commune = normaliser(fokontany.nom_fokontany), normaliser(fokontany.commune.nom_commune)
    # 17 000 contours : on ne charge que les homonymes probables, sans leurs géométries, puis on relit le contour choisi
    candidats = [k for k in contours.filter(nom__istartswith=fokontany.nom_fokontany[:3]).defer('geometrie', 'geometrie_simple')
                 if normaliser(k.nom) == nom]
    choisi = _choisir(candidats, [lambda k: normaliser(k.commune_nom) == commune, lambda k: True])
    return contours.get(pk=choisi.pk) if choisi else None


def contour_district(district):
    """Contour importé d'un `District` : lien `objet_id`, sinon nom + région, sinon nom unique."""
    from apps.geography.models_contours import ContourAdmin

    contours = ContourAdmin.objects.filter(niveau='district')
    lie = contours.filter(objet_id=district.id).first()
    if lie:
        return lie
    nom, region = normaliser(district.nom_district), normaliser(district.region.nom_region)
    candidats = [k for k in contours if normaliser(k.nom) == nom]
    return _choisir(candidats, [lambda k: normaliser(k.region_nom) == region, lambda k: True])


def contours_village(village):
    """Contours à dessiner sur la carte d'un village : sa commune (fond) puis son fokontany (sélectionné)."""
    fokontany = getattr(village, 'fokontany', None)
    if fokontany is None:
        return []
    features = []
    commune = getattr(fokontany, 'commune', None)
    k_commune = contour_commune(commune) if commune is not None else None
    if k_commune:
        features.append(_feature_contour(k_commune, 'commune'))
    k_fokontany = contour_fokontany(fokontany)
    if k_fokontany:
        features.append(_feature_contour(k_fokontany, 'fokontany', True))
    return features


def contours_communes_de(communes, maximum=12):
    """Contours des communes données (carte d'un ouvrage : les communes qu'il dessert), sans doublon."""
    features, vues = [], set()
    for commune in communes:
        if commune is None or commune.pk in vues or len(vues) >= maximum:
            continue
        vues.add(commune.pk)
        k = contour_commune(commune)
        if k:
            features.append(_feature_contour(k, 'commune'))
    return features


def contours_district(district, maximum_communes=80):
    """Contour du district (sélectionné) et de ses communes, pour la page du district."""
    from apps.geography.models_contours import ContourAdmin

    k = contour_district(district)
    if k is None:
        return []
    communes = ContourAdmin.objects.filter(niveau='commune')
    communes = communes.filter(district_pcode=k.district_pcode) if k.district_pcode else communes.filter(district_nom=k.nom)
    return [_feature_contour(k, 'district', True)] + [
        _feature_contour(c, 'commune') for c in communes.order_by('nom')[:maximum_communes]]
