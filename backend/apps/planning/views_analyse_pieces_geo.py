"""
Vues pour l'analyse de l'utilisation des pièces de rechange par géographie (Commune et District)
"""
import json
from django.shortcuts import render
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Sum, Count, Q, F, DecimalField, Value
from django.db.models.functions import Coalesce
from decimal import Decimal
from apps.planning.models import PlanningDetail, BonLivraison, Designation, Planning, TypeDesignation
from apps.billing.models import PointEau
from apps.organization.models import Ouvrage
from apps.geography.models import District, Commune, Fokontany, Village


def analyse_pieces_par_commune(request):
    """
    Page d'analyse de l'utilisation des pièces de rechange par COMMUNE

    Analyse basée sur:
    - PlanningDetails avec designation.concerne_livraison=True
    - BonLivraison avec designation.concerne_livraison=True
    - Groupement par commune via la chaîne: Ouvrage → PointEau → Parcelle → Village → Fokontany → Commune

    Filtres disponibles:
    - district_id: Filtrer par district
    - commune_ids: Filtrer par communes (IDs séparés par virgule)
    - type_designation_ids: Filtrer par types de désignation (IDs séparés par virgule)
    """

    # =========================================================================
    # 0. RÉCUPÉRATION DES PARAMÈTRES DE FILTRAGE
    # =========================================================================

    district_id = request.GET.get('district_id')
    commune_ids_str = request.GET.get('commune_ids', '')
    type_designation_ids_str = request.GET.get('type_designation_ids', '')

    # Convertir les IDs en listes
    commune_ids = [cid.strip() for cid in commune_ids_str.split(',') if cid.strip()]
    type_designation_ids = [tid.strip() for tid in type_designation_ids_str.split(',') if tid.strip()]

    # =========================================================================
    # 1. RÉCUPÉRATION DES DONNÉES DE BASE AVEC FILTRES
    # =========================================================================

    # Types de désignations autorisés (4 types spécifiques)
    types_autorises = ['Accessoire galva', 'Accessoire plastique', 'Accessoire PMH', 'Quincaillerie']

    # Récupérer les ouvrages filtrés géographiquement avec leurs communes
    points_eau_qs = PointEau.objects.select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district'
    ).filter(
        ouvrage__type_ouvrage__existe=True
    )

    # Filtrer par district
    if district_id:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district_id=district_id
        )

    # Filtrer par communes
    if commune_ids:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune_id__in=commune_ids
        )

    # Extraire les IDs d'ouvrages et mapper ouvrage → commune
    ouvrage_commune_map = {}  # {ouvrage_id: commune_info}
    ouvrages_avec_pe_ids = []

    for pe in points_eau_qs:
        if pe.ouvrage_id and pe.parcelle and pe.parcelle.village:
            if pe.parcelle.village.fokontany and pe.parcelle.village.fokontany.commune:
                commune = pe.parcelle.village.fokontany.commune
                ouvrage_commune_map[str(pe.ouvrage_id)] = {
                    'commune_id': str(commune.id),
                    'commune_nom': commune.nom_commune,
                    'district_nom': commune.district.nom_district if commune.district else 'N/A'
                }
                ouvrages_avec_pe_ids.append(pe.ouvrage_id)

    ouvrages_avec_pe_ids = list(set(ouvrages_avec_pe_ids))

    # =========================================================================
    # 2. DONNÉES DEPUIS PLANNING DETAILS
    # =========================================================================

    planning_details = PlanningDetail.objects.filter(
        Q(point_eau__ouvrage_id__in=ouvrages_avec_pe_ids) |
        Q(equipement_constitutif__ouvrage_id__in=ouvrages_avec_pe_ids),
        designation__concerne_livraison=True,
        designation__actif=True,
        designation__type_designation__nom__in=types_autorises
    ).select_related('designation', 'point_eau__ouvrage', 'equipement_constitutif__ouvrage')

    # Filtrer par types de désignation si spécifié
    if type_designation_ids:
        planning_details = planning_details.filter(designation__type_designation_id__in=type_designation_ids)

    # =========================================================================
    # 3. DONNÉES DEPUIS BON DE LIVRAISON
    # =========================================================================

    bons_livraison = BonLivraison.objects.filter(
        Q(point_eau__ouvrage_id__in=ouvrages_avec_pe_ids) |
        Q(equipement__ouvrage_id__in=ouvrages_avec_pe_ids),
        designation__concerne_livraison=True,
        designation__actif=True,
        designation__type_designation__nom__in=types_autorises
    ).select_related('designation', 'point_eau__ouvrage', 'equipement__ouvrage')

    # Filtrer par types de désignation si spécifié
    if type_designation_ids:
        bons_livraison = bons_livraison.filter(designation__type_designation_id__in=type_designation_ids)

    # =========================================================================
    # 4. AGRÉGATION PAR COMMUNE
    # =========================================================================

    communes_usage = {}  # {commune_id: {...}}

    # Depuis PlanningDetail
    for pd in planning_details:
        ouvrage_id = None
        if pd.point_eau and pd.point_eau.ouvrage_id:
            ouvrage_id = str(pd.point_eau.ouvrage_id)
        elif pd.equipement_constitutif and pd.equipement_constitutif.ouvrage_id:
            ouvrage_id = str(pd.equipement_constitutif.ouvrage_id)

        if not ouvrage_id or ouvrage_id not in ouvrage_commune_map:
            continue

        commune_info = ouvrage_commune_map[ouvrage_id]
        commune_id = commune_info['commune_id']

        if commune_id not in communes_usage:
            communes_usage[commune_id] = {
                'commune_id': commune_id,
                'commune_nom': commune_info['commune_nom'],
                'district_nom': commune_info['district_nom'],
                'quantite': 0,
                'montant': 0,
                'designations': set(),
                'ouvrages': set()
            }

        quantite_pd = float(pd.quantite or 0)
        montant_pd = float(pd.montant or 0)

        communes_usage[commune_id]['quantite'] += quantite_pd
        communes_usage[commune_id]['montant'] += montant_pd
        if pd.designation_id:
            communes_usage[commune_id]['designations'].add(str(pd.designation_id))
        if ouvrage_id:
            communes_usage[commune_id]['ouvrages'].add(ouvrage_id)

    # Depuis BonLivraison
    for bl in bons_livraison:
        ouvrage_id = None
        if bl.point_eau and bl.point_eau.ouvrage_id:
            ouvrage_id = str(bl.point_eau.ouvrage_id)
        elif bl.equipement and bl.equipement.ouvrage_id:
            ouvrage_id = str(bl.equipement.ouvrage_id)

        if not ouvrage_id or ouvrage_id not in ouvrage_commune_map:
            continue

        commune_info = ouvrage_commune_map[ouvrage_id]
        commune_id = commune_info['commune_id']

        if commune_id not in communes_usage:
            communes_usage[commune_id] = {
                'commune_id': commune_id,
                'commune_nom': commune_info['commune_nom'],
                'district_nom': commune_info['district_nom'],
                'quantite': 0,
                'montant': 0,
                'designations': set(),
                'ouvrages': set()
            }

        quantite_bl = float(bl.quantite or 0)
        prix_unitaire = float(bl.designation.prix_unitaire or 0)
        montant_bl = quantite_bl * prix_unitaire

        communes_usage[commune_id]['quantite'] += quantite_bl
        communes_usage[commune_id]['montant'] += montant_bl
        if bl.designation_id:
            communes_usage[commune_id]['designations'].add(str(bl.designation_id))
        if ouvrage_id:
            communes_usage[commune_id]['ouvrages'].add(ouvrage_id)

    # Convertir les sets en nombres
    for usage in communes_usage.values():
        usage['nb_pieces_diff'] = len(usage['designations'])
        usage['nb_ouvrages'] = len(usage['ouvrages'])
        del usage['designations']
        del usage['ouvrages']

    # Ajouter le nombre de points d'eau par commune
    nb_pe_par_commune = {}
    for pe in points_eau_qs:
        if pe.ouvrage_id and str(pe.ouvrage_id) in ouvrage_commune_map:
            commune_id = ouvrage_commune_map[str(pe.ouvrage_id)]['commune_id']
            nb_pe_par_commune[commune_id] = nb_pe_par_commune.get(commune_id, 0) + 1

    for commune_id, usage in communes_usage.items():
        nb_pe = nb_pe_par_commune.get(commune_id, 1)
        usage['nb_points_eau'] = nb_pe
        usage['quantite_par_pe'] = usage['quantite'] / nb_pe if nb_pe > 0 else 0
        usage['montant_par_pe'] = usage['montant'] / nb_pe if nb_pe > 0 else 0

    # Tri absolu (par quantité totale)
    top_communes_absolu = sorted(
        communes_usage.values(),
        key=lambda x: x['quantite'],
        reverse=True
    )[:10]

    # Tri relatif (par quantité par point d'eau)
    top_communes_relatif = sorted(
        communes_usage.values(),
        key=lambda x: x['quantite_par_pe'],
        reverse=True
    )[:10]

    # =========================================================================
    # 5. TOP 10 PIÈCES (même logique que vue par ouvrage)
    # =========================================================================

    pieces_usage = {}

    for pd in planning_details:
        desig_id = str(pd.designation_id)
        if desig_id not in pieces_usage:
            pieces_usage[desig_id] = {
                'designation_id': desig_id,
                'nom': pd.designation.nom,
                'quantite': 0,
                'montant': 0,
                'nb_utilisations': 0
            }

        pieces_usage[desig_id]['quantite'] += float(pd.quantite or 0)
        pieces_usage[desig_id]['montant'] += float(pd.montant or 0)
        pieces_usage[desig_id]['nb_utilisations'] += 1

    for bl in bons_livraison:
        desig_id = str(bl.designation_id)
        if desig_id not in pieces_usage:
            pieces_usage[desig_id] = {
                'designation_id': desig_id,
                'nom': bl.designation.nom,
                'quantite': 0,
                'montant': 0,
                'nb_utilisations': 0
            }

        quantite_bl = float(bl.quantite or 0)
        prix_unitaire = float(bl.designation.prix_unitaire or 0)

        pieces_usage[desig_id]['quantite'] += quantite_bl
        pieces_usage[desig_id]['montant'] += quantite_bl * prix_unitaire
        pieces_usage[desig_id]['nb_utilisations'] += 1

    top_pieces_quantite = sorted(
        pieces_usage.values(),
        key=lambda x: x['quantite'],
        reverse=True
    )[:10]

    top_pieces_montant = sorted(
        pieces_usage.values(),
        key=lambda x: x['montant'],
        reverse=True
    )[:10]

    # =========================================================================
    # 6. STATISTIQUES GLOBALES
    # =========================================================================

    total_quantite = sum(u['quantite'] for u in communes_usage.values())
    total_montant = sum(u['montant'] for u in communes_usage.values())
    nb_communes_concernees = len(communes_usage)
    nb_pieces_differentes = len(pieces_usage)
    nb_utilisations = sum(p['nb_utilisations'] for p in pieces_usage.values())

    stats_globales = {
        'total_quantite': total_quantite,
        'total_montant': total_montant,
        'nb_pieces_differentes': nb_pieces_differentes,
        'nb_communes_concernees': nb_communes_concernees,
        'nb_utilisations': nb_utilisations
    }

    # =========================================================================
    # 7. DONNÉES POUR GRAPHIQUES
    # =========================================================================

    graphique_pieces_qty = {
        'labels': [p['nom'][:30] for p in top_pieces_quantite],
        'data': [p['quantite'] for p in top_pieces_quantite]
    }

    graphique_pieces_montant = {
        'labels': [p['nom'][:30] for p in top_pieces_montant],
        'data': [p['montant'] for p in top_pieces_montant]
    }

    graphique_communes_absolu = {
        'labels': [c['commune_nom'][:30] for c in top_communes_absolu],
        'data': [c['quantite'] for c in top_communes_absolu]
    }

    graphique_communes_relatif = {
        'labels': [c['commune_nom'][:30] for c in top_communes_relatif],
        'data': [round(c['quantite_par_pe'], 2) for c in top_communes_relatif]
    }

    # =========================================================================
    # 8. SÉRIALISATION JSON POUR JAVASCRIPT
    # =========================================================================

    top_pieces_quantite_json = json.dumps(top_pieces_quantite, cls=DjangoJSONEncoder)
    top_pieces_montant_json = json.dumps(top_pieces_montant, cls=DjangoJSONEncoder)
    top_communes_absolu_json = json.dumps(top_communes_absolu, cls=DjangoJSONEncoder)
    top_communes_relatif_json = json.dumps(top_communes_relatif, cls=DjangoJSONEncoder)
    stats_globales_json = json.dumps(stats_globales, cls=DjangoJSONEncoder)

    # =========================================================================
    # 9. DONNÉES POUR LES FILTRES
    # =========================================================================

    districts = District.objects.all().order_by('nom_district')

    communes_qs = Commune.objects.all()
    if district_id:
        communes_qs = communes_qs.filter(district_id=district_id)
    communes = communes_qs.order_by('nom_commune')

    types_designation = TypeDesignation.objects.filter(nom__in=types_autorises).order_by('nom')

    # =========================================================================
    # 10. CONTEXTE POUR LE TEMPLATE
    # =========================================================================

    context = {
        # Graphiques
        'graphique_pieces_qty': graphique_pieces_qty,
        'graphique_pieces_montant': graphique_pieces_montant,
        'graphique_communes_absolu': graphique_communes_absolu,
        'graphique_communes_relatif': graphique_communes_relatif,

        # Tableaux
        'top_pieces_quantite': top_pieces_quantite,
        'top_pieces_montant': top_pieces_montant,
        'top_communes_absolu': top_communes_absolu,
        'top_communes_relatif': top_communes_relatif,

        # Statistiques
        'stats_globales': stats_globales,

        # Filtres
        'districts': districts,
        'communes': communes,
        'types_designation': types_designation,

        # Sélections actuelles
        'district_id': district_id,
        'commune_ids': commune_ids,
        'type_designation_ids': type_designation_ids,

        # JSON pour JavaScript
        'top_pieces_quantite_json': top_pieces_quantite_json,
        'top_pieces_montant_json': top_pieces_montant_json,
        'top_communes_absolu_json': top_communes_absolu_json,
        'top_communes_relatif_json': top_communes_relatif_json,
        'stats_globales_json': stats_globales_json,

        # Niveau d'analyse
        'niveau_analyse': 'commune'
    }

    return render(request, 'planning/analyse_pieces_par_commune.html', context)


def analyse_pieces_par_district(request):
    """
    Page d'analyse de l'utilisation des pièces de rechange par DISTRICT

    Analyse basée sur:
    - PlanningDetails avec designation.concerne_livraison=True
    - BonLivraison avec designation.concerne_livraison=True
    - Groupement par district via la chaîne: Ouvrage → PointEau → Parcelle → Village → Fokontany → Commune → District

    Filtres disponibles:
    - district_id: Filtrer par district spécifique
    - type_designation_ids: Filtrer par types de désignation (IDs séparés par virgule)
    """

    # =========================================================================
    # 0. RÉCUPÉRATION DES PARAMÈTRES DE FILTRAGE
    # =========================================================================

    district_id = request.GET.get('district_id')
    type_designation_ids_str = request.GET.get('type_designation_ids', '')

    # Convertir les IDs en listes
    type_designation_ids = [tid.strip() for tid in type_designation_ids_str.split(',') if tid.strip()]

    # =========================================================================
    # 1. RÉCUPÉRATION DES DONNÉES DE BASE AVEC FILTRES
    # =========================================================================

    # Types de désignations autorisés (4 types spécifiques)
    types_autorises = ['Accessoire galva', 'Accessoire plastique', 'Accessoire PMH', 'Quincaillerie']

    # Récupérer les ouvrages filtrés géographiquement avec leurs districts
    points_eau_qs = PointEau.objects.select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district'
    ).filter(
        ouvrage__type_ouvrage__existe=True
    )

    # Filtrer par district
    if district_id:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district_id=district_id
        )

    # Extraire les IDs d'ouvrages et mapper ouvrage → district
    ouvrage_district_map = {}  # {ouvrage_id: district_info}
    ouvrages_avec_pe_ids = []

    for pe in points_eau_qs:
        if pe.ouvrage_id and pe.parcelle and pe.parcelle.village:
            if pe.parcelle.village.fokontany and pe.parcelle.village.fokontany.commune:
                if pe.parcelle.village.fokontany.commune.district:
                    district = pe.parcelle.village.fokontany.commune.district
                    ouvrage_district_map[str(pe.ouvrage_id)] = {
                        'district_id': str(district.id),
                        'district_nom': district.nom_district
                    }
                    ouvrages_avec_pe_ids.append(pe.ouvrage_id)

    ouvrages_avec_pe_ids = list(set(ouvrages_avec_pe_ids))

    # =========================================================================
    # 2. DONNÉES DEPUIS PLANNING DETAILS
    # =========================================================================

    planning_details = PlanningDetail.objects.filter(
        Q(point_eau__ouvrage_id__in=ouvrages_avec_pe_ids) |
        Q(equipement_constitutif__ouvrage_id__in=ouvrages_avec_pe_ids),
        designation__concerne_livraison=True,
        designation__actif=True,
        designation__type_designation__nom__in=types_autorises
    ).select_related('designation', 'point_eau__ouvrage', 'equipement_constitutif__ouvrage')

    # Filtrer par types de désignation si spécifié
    if type_designation_ids:
        planning_details = planning_details.filter(designation__type_designation_id__in=type_designation_ids)

    # =========================================================================
    # 3. DONNÉES DEPUIS BON DE LIVRAISON
    # =========================================================================

    bons_livraison = BonLivraison.objects.filter(
        Q(point_eau__ouvrage_id__in=ouvrages_avec_pe_ids) |
        Q(equipement__ouvrage_id__in=ouvrages_avec_pe_ids),
        designation__concerne_livraison=True,
        designation__actif=True,
        designation__type_designation__nom__in=types_autorises
    ).select_related('designation', 'point_eau__ouvrage', 'equipement__ouvrage')

    # Filtrer par types de désignation si spécifié
    if type_designation_ids:
        bons_livraison = bons_livraison.filter(designation__type_designation_id__in=type_designation_ids)

    # =========================================================================
    # 4. AGRÉGATION PAR DISTRICT
    # =========================================================================

    districts_usage = {}  # {district_id: {...}}

    # Depuis PlanningDetail
    for pd in planning_details:
        ouvrage_id = None
        if pd.point_eau and pd.point_eau.ouvrage_id:
            ouvrage_id = str(pd.point_eau.ouvrage_id)
        elif pd.equipement_constitutif and pd.equipement_constitutif.ouvrage_id:
            ouvrage_id = str(pd.equipement_constitutif.ouvrage_id)

        if not ouvrage_id or ouvrage_id not in ouvrage_district_map:
            continue

        district_info = ouvrage_district_map[ouvrage_id]
        district_id_key = district_info['district_id']

        if district_id_key not in districts_usage:
            districts_usage[district_id_key] = {
                'district_id': district_id_key,
                'district_nom': district_info['district_nom'],
                'quantite': 0,
                'montant': 0,
                'designations': set(),
                'ouvrages': set()
            }

        quantite_pd = float(pd.quantite or 0)
        montant_pd = float(pd.montant or 0)

        districts_usage[district_id_key]['quantite'] += quantite_pd
        districts_usage[district_id_key]['montant'] += montant_pd
        if pd.designation_id:
            districts_usage[district_id_key]['designations'].add(str(pd.designation_id))
        if ouvrage_id:
            districts_usage[district_id_key]['ouvrages'].add(ouvrage_id)

    # Depuis BonLivraison
    for bl in bons_livraison:
        ouvrage_id = None
        if bl.point_eau and bl.point_eau.ouvrage_id:
            ouvrage_id = str(bl.point_eau.ouvrage_id)
        elif bl.equipement and bl.equipement.ouvrage_id:
            ouvrage_id = str(bl.equipement.ouvrage_id)

        if not ouvrage_id or ouvrage_id not in ouvrage_district_map:
            continue

        district_info = ouvrage_district_map[ouvrage_id]
        district_id_key = district_info['district_id']

        if district_id_key not in districts_usage:
            districts_usage[district_id_key] = {
                'district_id': district_id_key,
                'district_nom': district_info['district_nom'],
                'quantite': 0,
                'montant': 0,
                'designations': set(),
                'ouvrages': set()
            }

        quantite_bl = float(bl.quantite or 0)
        prix_unitaire = float(bl.designation.prix_unitaire or 0)
        montant_bl = quantite_bl * prix_unitaire

        districts_usage[district_id_key]['quantite'] += quantite_bl
        districts_usage[district_id_key]['montant'] += montant_bl
        if bl.designation_id:
            districts_usage[district_id_key]['designations'].add(str(bl.designation_id))
        if ouvrage_id:
            districts_usage[district_id_key]['ouvrages'].add(ouvrage_id)

    # Convertir les sets en nombres
    for usage in districts_usage.values():
        usage['nb_pieces_diff'] = len(usage['designations'])
        usage['nb_ouvrages'] = len(usage['ouvrages'])
        del usage['designations']
        del usage['ouvrages']

    # Ajouter le nombre de points d'eau par district
    nb_pe_par_district = {}
    for pe in points_eau_qs:
        if pe.ouvrage_id and str(pe.ouvrage_id) in ouvrage_district_map:
            district_id_key = ouvrage_district_map[str(pe.ouvrage_id)]['district_id']
            nb_pe_par_district[district_id_key] = nb_pe_par_district.get(district_id_key, 0) + 1

    for district_id_key, usage in districts_usage.items():
        nb_pe = nb_pe_par_district.get(district_id_key, 1)
        usage['nb_points_eau'] = nb_pe
        usage['quantite_par_pe'] = usage['quantite'] / nb_pe if nb_pe > 0 else 0
        usage['montant_par_pe'] = usage['montant'] / nb_pe if nb_pe > 0 else 0

    # Tri absolu (par quantité totale)
    top_districts_absolu = sorted(
        districts_usage.values(),
        key=lambda x: x['quantite'],
        reverse=True
    )[:10]

    # Tri relatif (par quantité par point d'eau)
    top_districts_relatif = sorted(
        districts_usage.values(),
        key=lambda x: x['quantite_par_pe'],
        reverse=True
    )[:10]

    # =========================================================================
    # 5. TOP 10 PIÈCES (même logique que vue par ouvrage)
    # =========================================================================

    pieces_usage = {}

    for pd in planning_details:
        desig_id = str(pd.designation_id)
        if desig_id not in pieces_usage:
            pieces_usage[desig_id] = {
                'designation_id': desig_id,
                'nom': pd.designation.nom,
                'quantite': 0,
                'montant': 0,
                'nb_utilisations': 0
            }

        pieces_usage[desig_id]['quantite'] += float(pd.quantite or 0)
        pieces_usage[desig_id]['montant'] += float(pd.montant or 0)
        pieces_usage[desig_id]['nb_utilisations'] += 1

    for bl in bons_livraison:
        desig_id = str(bl.designation_id)
        if desig_id not in pieces_usage:
            pieces_usage[desig_id] = {
                'designation_id': desig_id,
                'nom': bl.designation.nom,
                'quantite': 0,
                'montant': 0,
                'nb_utilisations': 0
            }

        quantite_bl = float(bl.quantite or 0)
        prix_unitaire = float(bl.designation.prix_unitaire or 0)

        pieces_usage[desig_id]['quantite'] += quantite_bl
        pieces_usage[desig_id]['montant'] += quantite_bl * prix_unitaire
        pieces_usage[desig_id]['nb_utilisations'] += 1

    top_pieces_quantite = sorted(
        pieces_usage.values(),
        key=lambda x: x['quantite'],
        reverse=True
    )[:10]

    top_pieces_montant = sorted(
        pieces_usage.values(),
        key=lambda x: x['montant'],
        reverse=True
    )[:10]

    # =========================================================================
    # 6. STATISTIQUES GLOBALES
    # =========================================================================

    total_quantite = sum(u['quantite'] for u in districts_usage.values())
    total_montant = sum(u['montant'] for u in districts_usage.values())
    nb_districts_concernes = len(districts_usage)
    nb_pieces_differentes = len(pieces_usage)
    nb_utilisations = sum(p['nb_utilisations'] for p in pieces_usage.values())

    stats_globales = {
        'total_quantite': total_quantite,
        'total_montant': total_montant,
        'nb_pieces_differentes': nb_pieces_differentes,
        'nb_districts_concernes': nb_districts_concernes,
        'nb_utilisations': nb_utilisations
    }

    # =========================================================================
    # 7. DONNÉES POUR GRAPHIQUES
    # =========================================================================

    graphique_pieces_qty = {
        'labels': [p['nom'][:30] for p in top_pieces_quantite],
        'data': [p['quantite'] for p in top_pieces_quantite]
    }

    graphique_pieces_montant = {
        'labels': [p['nom'][:30] for p in top_pieces_montant],
        'data': [p['montant'] for p in top_pieces_montant]
    }

    graphique_districts_absolu = {
        'labels': [d['district_nom'][:30] for d in top_districts_absolu],
        'data': [d['quantite'] for d in top_districts_absolu]
    }

    graphique_districts_relatif = {
        'labels': [d['district_nom'][:30] for d in top_districts_relatif],
        'data': [round(d['quantite_par_pe'], 2) for d in top_districts_relatif]
    }

    # =========================================================================
    # 8. SÉRIALISATION JSON POUR JAVASCRIPT
    # =========================================================================

    top_pieces_quantite_json = json.dumps(top_pieces_quantite, cls=DjangoJSONEncoder)
    top_pieces_montant_json = json.dumps(top_pieces_montant, cls=DjangoJSONEncoder)
    top_districts_absolu_json = json.dumps(top_districts_absolu, cls=DjangoJSONEncoder)
    top_districts_relatif_json = json.dumps(top_districts_relatif, cls=DjangoJSONEncoder)
    stats_globales_json = json.dumps(stats_globales, cls=DjangoJSONEncoder)

    # =========================================================================
    # 9. DONNÉES POUR LES FILTRES
    # =========================================================================

    districts = District.objects.all().order_by('nom_district')
    types_designation = TypeDesignation.objects.filter(nom__in=types_autorises).order_by('nom')

    # =========================================================================
    # 10. CONTEXTE POUR LE TEMPLATE
    # =========================================================================

    context = {
        # Graphiques
        'graphique_pieces_qty': graphique_pieces_qty,
        'graphique_pieces_montant': graphique_pieces_montant,
        'graphique_districts_absolu': graphique_districts_absolu,
        'graphique_districts_relatif': graphique_districts_relatif,

        # Tableaux
        'top_pieces_quantite': top_pieces_quantite,
        'top_pieces_montant': top_pieces_montant,
        'top_districts_absolu': top_districts_absolu,
        'top_districts_relatif': top_districts_relatif,

        # Statistiques
        'stats_globales': stats_globales,

        # Filtres
        'districts': districts,
        'types_designation': types_designation,

        # Sélection actuelle
        'district_id': district_id,
        'type_designation_ids': type_designation_ids,

        # JSON pour JavaScript
        'top_pieces_quantite_json': top_pieces_quantite_json,
        'top_pieces_montant_json': top_pieces_montant_json,
        'top_districts_absolu_json': top_districts_absolu_json,
        'top_districts_relatif_json': top_districts_relatif_json,
        'stats_globales_json': stats_globales_json,

        # Niveau d'analyse
        'niveau_analyse': 'district'
    }

    return render(request, 'planning/analyse_pieces_par_district.html', context)
