"""
Vues pour l'analyse de l'utilisation des pièces de rechange
"""
import json
from django.shortcuts import render
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Sum, Count, Q, F, DecimalField, Value
from django.db.models.functions import Coalesce
from decimal import Decimal
from apps.planning.models import PlanningDetail, BonLivraison, Designation, Planning, TypeDesignation
from apps.planning.grading import get_ouvrage_grading
from apps.billing.models import PointEau
from apps.organization.models import Ouvrage
from apps.geography.models import District, Commune


def analyse_pieces_rechange(request):
    """
    Page d'analyse de l'utilisation des pièces de rechange

    Analyse basée sur:
    - PlanningDetails avec designation.concerne_livraison=True
    - BonLivraison avec designation.concerne_livraison=True
    - Filtre: seulement les ouvrages qui ont des points d'eau

    Filtres disponibles:
    - district_id: Filtrer par district
    - commune_ids: Filtrer par communes (IDs séparés par virgule)
    - ouvrage_ids: Filtrer par ouvrages (IDs séparés par virgule)
    - type_designation_ids: Filtrer par types de désignation (IDs séparés par virgule)
    - top_n: Nombre de résultats par classement (10, 20 ou 30)
    """

    # =========================================================================
    # 0. RÉCUPÉRATION DES PARAMÈTRES DE FILTRAGE
    # =========================================================================

    district_id = request.GET.get('district_id')
    commune_ids_str = request.GET.get('commune_ids', '')
    ouvrage_ids_str = request.GET.get('ouvrage_ids', '')
    type_designation_ids_str = request.GET.get('type_designation_ids', '')
    try:
        top_limit = int(request.GET.get('top_n', 10))
    except (TypeError, ValueError):
        top_limit = 10
    if top_limit not in (10, 20, 30):
        top_limit = 10

    # Convertir les IDs en listes
    commune_ids = [cid.strip() for cid in commune_ids_str.split(',') if cid.strip()]
    ouvrage_ids = [oid.strip() for oid in ouvrage_ids_str.split(',') if oid.strip()]
    type_designation_ids = [tid.strip() for tid in type_designation_ids_str.split(',') if tid.strip()]

    # =========================================================================
    # 1. RÉCUPÉRATION DES DONNÉES DE BASE AVEC FILTRES
    # =========================================================================

    # Récupérer les IDs des ouvrages qui ont des points d'eau (avec filtres géographiques)
    # FILTRAGE CRITIQUE : Seulement les ouvrages dont le type existe (type_ouvrage.existe=True)
    ouvrages_qs = PointEau.objects.filter(
        ouvrage__isnull=False,
        ouvrage__type_ouvrage__existe=True  # ✅ Filtre ajouté
    )

    # Appliquer les filtres géographiques
    if ouvrage_ids:
        ouvrages_qs = ouvrages_qs.filter(ouvrage_id__in=ouvrage_ids)
    elif commune_ids:
        # Filtrer par commune via parcelle -> village -> fokontany -> commune
        ouvrages_qs = ouvrages_qs.filter(parcelle__village__fokontany__commune_id__in=commune_ids)
    elif district_id:
        # Filtrer par district via commune
        ouvrages_qs = ouvrages_qs.filter(parcelle__village__fokontany__commune__district_id=district_id)

    ouvrages_avec_pe_ids = ouvrages_qs.values_list('ouvrage_id', flat=True).distinct()

    # Désignations de pièces de rechange (concerne_livraison=True)
    # FILTRAGE CRITIQUE : Seulement les types spécifiés
    types_autorises = ['Accessoire galva', 'Accessoire plastique', 'Accessoire PMH', 'Quincaillerie']
    designations_pieces = Designation.objects.filter(
        concerne_livraison=True,
        actif=True,
        type_designation__nom__in=types_autorises  # ✅ Filtre ajouté
    )

    # =========================================================================
    # 2. DONNÉES DEPUIS PLANNINGDETAIL
    # =========================================================================

    # PlanningDetails avec pièces de rechange pour ouvrages avec PE
    # On filtre via point_eau ou equipement_constitutif
    planning_details = PlanningDetail.objects.filter(
        Q(point_eau__ouvrage_id__in=ouvrages_avec_pe_ids) |
        Q(equipement_constitutif__ouvrage_id__in=ouvrages_avec_pe_ids),
        designation__concerne_livraison=True,
        designation__actif=True,
        designation__type_designation__nom__in=types_autorises  # ✅ Filtre types ajouté
    ).select_related('designation', 'point_eau__ouvrage', 'equipement_constitutif__ouvrage', 'planning')

    # Appliquer le filtre par type de désignation (filtre utilisateur)
    if type_designation_ids:
        planning_details = planning_details.filter(designation__type_designation_id__in=type_designation_ids)

    # =========================================================================
    # 3. DONNÉES DEPUIS BON DE LIVRAISON
    # =========================================================================

    # BonLivraison - Filtrer par géographie via point_eau ou equipement
    # FILTRAGE CRITIQUE : Seulement les ouvrages filtrés géographiquement
    bons_livraison = BonLivraison.objects.filter(
        Q(point_eau__ouvrage_id__in=ouvrages_avec_pe_ids) |
        Q(equipement__ouvrage_id__in=ouvrages_avec_pe_ids),
        designation__concerne_livraison=True,
        designation__actif=True,
        designation__type_designation__nom__in=types_autorises  # ✅ Filtre types ajouté
    ).select_related('designation', 'planning')

    # Appliquer le filtre par type de désignation (filtre utilisateur)
    if type_designation_ids:
        bons_livraison = bons_livraison.filter(designation__type_designation_id__in=type_designation_ids)

    # =========================================================================
    # 4. STATISTIQUES GLOBALES
    # =========================================================================

    # Total quantités utilisées
    total_qty_planning = planning_details.aggregate(
        total=Coalesce(Sum('quantity', output_field=DecimalField()), Value(0, output_field=DecimalField()))
    )['total'] or 0

    total_qty_livraison = bons_livraison.aggregate(
        total=Coalesce(Sum('quantite', output_field=DecimalField()), Value(0, output_field=DecimalField()))
    )['total'] or 0

    total_quantite = Decimal(str(total_qty_planning)) + Decimal(str(total_qty_livraison))

    # Total montants (BonLivraison n'a pas de champ montant)
    total_montant_planning = planning_details.aggregate(
        total=Coalesce(Sum('montant', output_field=DecimalField()), Value(0, output_field=DecimalField()))
    )['total'] or 0

    # BonLivraison : calculer montant = quantite × prix_unitaire de la désignation
    total_montant_livraison = Decimal('0')
    for bon in bons_livraison.select_related('designation'):
        quantite = Decimal(str(bon.quantite or 0))
        prix_unitaire = Decimal(str(bon.designation.prix_unitaire or 0))
        total_montant_livraison += quantite * prix_unitaire  # ✅ Calcul correct

    total_montant = Decimal(str(total_montant_planning)) + total_montant_livraison

    # Nombre de pièces différentes utilisées
    pieces_distinctes_planning = planning_details.values('designation_id').distinct().count()
    pieces_distinctes_livraison = bons_livraison.values('designation_id').distinct().count()
    pieces_distinctes_ids = set(
        list(planning_details.values_list('designation_id', flat=True).distinct()) +
        list(bons_livraison.values_list('designation_id', flat=True).distinct())
    )
    nb_pieces_differentes = len(pieces_distinctes_ids)

    # Nombre d'ouvrages concernés - extraction via relations
    ouvrages_from_pd = set()
    for pd in planning_details:
        if pd.point_eau and pd.point_eau.ouvrage_id:
            ouvrages_from_pd.add(str(pd.point_eau.ouvrage_id))
        elif pd.equipement_constitutif and pd.equipement_constitutif.ouvrage_id:
            ouvrages_from_pd.add(str(pd.equipement_constitutif.ouvrage_id))

    ouvrages_from_bl = set()
    for bl in bons_livraison:
        if bl.point_eau and bl.point_eau.ouvrage_id:
            ouvrages_from_bl.add(str(bl.point_eau.ouvrage_id))
        elif bl.equipement and bl.equipement.ouvrage_id:
            ouvrages_from_bl.add(str(bl.equipement.ouvrage_id))

    ouvrages_concernes_ids = ouvrages_from_pd | ouvrages_from_bl
    nb_ouvrages_concernes = len(ouvrages_concernes_ids)

    stats_globales = {
        'total_quantite': float(total_quantite),
        'total_montant': float(total_montant),
        'nb_pieces_differentes': nb_pieces_differentes,
        'nb_ouvrages_concernes': nb_ouvrages_concernes,
        'nb_utilisations': planning_details.count() + bons_livraison.count()
    }

    # DEBUG: Afficher les stats calculées
    print("=" * 80)
    print("DEBUG STATS GLOBALES")
    print(f"District ID: {district_id}")
    print(f"Commune IDs: {commune_ids}")
    print(f"Ouvrage IDs: {ouvrage_ids}")
    print(f"PlanningDetails count: {planning_details.count()}")
    print(f"BonLivraison count: {bons_livraison.count()}")
    print(f"Stats calculees: {stats_globales}")
    print("=" * 80)

    # =========================================================================
    # 5. PIÈCES LES PLUS UTILISÉES (par quantité)
    # =========================================================================

    # Agréger par designation_id depuis les deux sources
    pieces_usage = {}

    # Depuis PlanningDetail
    for detail in planning_details.values('designation_id', 'designation__nom').annotate(
        total_qty=Coalesce(Sum('quantity', output_field=DecimalField()), Value(0, output_field=DecimalField())),
        total_montant=Coalesce(Sum('montant', output_field=DecimalField()), Value(0, output_field=DecimalField())),
        nb_utilisations=Count('id')
    ):
        desig_id = str(detail['designation_id'])
        if desig_id not in pieces_usage:
            pieces_usage[desig_id] = {
                'designation_id': desig_id,
                'nom': detail['designation__nom'],
                'quantite': 0,
                'montant': 0,
                'nb_utilisations': 0
            }
        pieces_usage[desig_id]['quantite'] += float(detail['total_qty'])
        pieces_usage[desig_id]['montant'] += float(detail['total_montant'])
        pieces_usage[desig_id]['nb_utilisations'] += detail['nb_utilisations']

    # Depuis BonLivraison - Calculer montant = quantite × prix_unitaire
    for bon in bons_livraison.select_related('designation'):
        desig_id = str(bon.designation_id)
        if desig_id not in pieces_usage:
            pieces_usage[desig_id] = {
                'designation_id': desig_id,
                'nom': bon.designation.nom,
                'quantite': 0,
                'montant': 0,
                'nb_utilisations': 0
            }

        quantite_bon = float(bon.quantite or 0)
        prix_unitaire = float(bon.designation.prix_unitaire or 0)
        montant_bon = quantite_bon * prix_unitaire  # ✅ Calcul correct

        pieces_usage[desig_id]['quantite'] += quantite_bon
        pieces_usage[desig_id]['montant'] += montant_bon  # ✅ Ajout du montant calculé
        pieces_usage[desig_id]['nb_utilisations'] += 1

    # Trier par quantité décroissante
    top_pieces_quantite = sorted(
        pieces_usage.values(),
        key=lambda x: x['quantite'],
        reverse=True
    )[:top_limit]

    # Trier par montant décroissant
    top_pieces_montant = sorted(
        pieces_usage.values(),
        key=lambda x: x['montant'],
        reverse=True
    )[:top_limit]

    # =========================================================================
    # 6. OUVRAGES QUI UTILISENT LE PLUS DE PIÈCES (relatif et absolu)
    # =========================================================================

    # Agréger par ouvrage - en itérant manuellement car pas de champ ouvrage_id direct
    ouvrages_usage = {}

    # Convertir ouvrages_avec_pe_ids en set pour vérification rapide
    ouvrages_filtres_set = set(str(oid) for oid in ouvrages_avec_pe_ids)

    # Depuis PlanningDetail
    for pd in planning_details:
        ouvrage = None
        if pd.point_eau and pd.point_eau.ouvrage:
            ouvrage = pd.point_eau.ouvrage
        elif pd.equipement_constitutif and pd.equipement_constitutif.ouvrage:
            ouvrage = pd.equipement_constitutif.ouvrage

        if ouvrage:
            ouv_id = str(ouvrage.id)

            # VÉRIFICATION CRITIQUE : Ne garder que les ouvrages filtrés
            if ouv_id not in ouvrages_filtres_set:
                continue

            if ouv_id not in ouvrages_usage:
                ouvrages_usage[ouv_id] = {
                    'ouvrage_id': ouv_id,
                    'nom': ouvrage.nom_ouvrage,
                    'quantite': 0,
                    'montant': 0,
                    'designations': set()
                }
            ouvrages_usage[ouv_id]['quantite'] += float(pd.quantity or 0)
            ouvrages_usage[ouv_id]['montant'] += float(pd.montant or 0)
            if pd.designation_id:
                ouvrages_usage[ouv_id]['designations'].add(str(pd.designation_id))

    # Depuis BonLivraison - avec select_related pour avoir la désignation
    for bl in bons_livraison.select_related('designation'):
        ouvrage = None
        if bl.point_eau and bl.point_eau.ouvrage:
            ouvrage = bl.point_eau.ouvrage
        elif bl.equipement and bl.equipement.ouvrage:
            ouvrage = bl.equipement.ouvrage

        if ouvrage:
            ouv_id = str(ouvrage.id)

            # VÉRIFICATION CRITIQUE : Ne garder que les ouvrages filtrés
            if ouv_id not in ouvrages_filtres_set:
                continue

            if ouv_id not in ouvrages_usage:
                ouvrages_usage[ouv_id] = {
                    'ouvrage_id': ouv_id,
                    'nom': ouvrage.nom_ouvrage,
                    'quantite': 0,
                    'montant': 0,
                    'designations': set()
                }

            quantite_bl = float(bl.quantite or 0)
            prix_unitaire = float(bl.designation.prix_unitaire or 0)
            montant_bl = quantite_bl * prix_unitaire  # ✅ Calcul correct

            ouvrages_usage[ouv_id]['quantite'] += quantite_bl
            ouvrages_usage[ouv_id]['montant'] += montant_bl  # ✅ Ajout du montant calculé
            if bl.designation_id:
                ouvrages_usage[ouv_id]['designations'].add(str(bl.designation_id))

    # Convertir les sets de designations en nombre
    for usage in ouvrages_usage.values():
        usage['nb_pieces_diff'] = len(usage['designations'])
        del usage['designations']  # Retirer le set (non sérialisable en JSON)

    # Ajouter le nombre de points d'eau par ouvrage
    nb_pe_par_ouvrage = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_usage.keys()
    ).values('ouvrage_id').annotate(
        nb_pe=Count('id')
    )

    nb_pe_dict = {str(item['ouvrage_id']): item['nb_pe'] for item in nb_pe_par_ouvrage}

    for ouv_id, usage in ouvrages_usage.items():
        nb_pe = nb_pe_dict.get(ouv_id, 1)  # Éviter division par 0
        usage['nb_points_eau'] = nb_pe
        usage['quantite_par_pe'] = usage['quantite'] / nb_pe if nb_pe > 0 else 0
        usage['montant_par_pe'] = usage['montant'] / nb_pe if nb_pe > 0 else 0

    # Récupérer le grading de chaque ouvrage
    for ouv_id, usage in ouvrages_usage.items():
        grading = get_ouvrage_grading(ouv_id)
        usage['grading'] = grading

    # Tri absolu (par quantité totale)
    top_ouvrages_absolu = sorted(
        ouvrages_usage.values(),
        key=lambda x: x['quantite'],
        reverse=True
    )[:top_limit]

    # Tri relatif (par quantité par point d'eau)
    top_ouvrages_relatif = sorted(
        ouvrages_usage.values(),
        key=lambda x: x['quantite_par_pe'],
        reverse=True
    )[:top_limit]

    # =========================================================================
    # 7. DONNÉES POUR GRAPHIQUES
    # =========================================================================

    # Graphique top pièces quantité
    graphique_pieces_qty = {
        'labels': [p['nom'][:30] for p in top_pieces_quantite],
        'data': [p['quantite'] for p in top_pieces_quantite]
    }

    # Graphique top pièces montant
    graphique_pieces_montant = {
        'labels': [p['nom'][:30] for p in top_pieces_montant],
        'data': [p['montant'] for p in top_pieces_montant]
    }

    # Graphique top ouvrages absolu
    graphique_ouvrages_absolu = {
        'labels': [o['nom'][:30] for o in top_ouvrages_absolu],
        'data': [o['quantite'] for o in top_ouvrages_absolu]
    }

    # Graphique top ouvrages relatif
    graphique_ouvrages_relatif = {
        'labels': [o['nom'][:30] for o in top_ouvrages_relatif],
        'data': [round(o['quantite_par_pe'], 2) for o in top_ouvrages_relatif]
    }

    # =========================================================================
    # 8. DONNÉES POUR LES FILTRES
    # =========================================================================

    # Liste des districts
    districts = District.objects.all().order_by('nom_district')

    # Liste des communes (filtrées par district si sélectionné)
    communes_qs = Commune.objects.all()
    if district_id:
        communes_qs = communes_qs.filter(district_id=district_id)
    communes = communes_qs.order_by('nom_commune')

    # Liste des ouvrages (filtrés par commune si sélectionnée)
    # FILTRAGE CRITIQUE : Seulement les ouvrages dont le type existe
    ouvrages_filtre_qs = Ouvrage.objects.filter(
        id__in=ouvrages_avec_pe_ids,
        type_ouvrage__existe=True  # ✅ Filtre ajouté pour cohérence
    )
    ouvrages_filtre = ouvrages_filtre_qs.order_by('nom_ouvrage')

    # Liste des types de désignation (seulement ceux utilisés dans les pièces de rechange)
    # FILTRAGE CRITIQUE : Seulement les 4 types autorisés
    types_designation = TypeDesignation.objects.filter(
        designations__concerne_livraison=True,
        designations__actif=True,
        nom__in=types_autorises  # ✅ Filtre types ajouté
    ).distinct().order_by('nom')

    # =========================================================================
    # 9. RENDU DU TEMPLATE
    # =========================================================================

    # Récupérer les noms des éléments sélectionnés pour l'affichage
    selected_district_obj = None
    selected_communes_objs = []
    selected_ouvrages_objs = []
    selected_types_objs = []

    if district_id:
        selected_district_obj = districts.filter(id=district_id).first()

    if commune_ids:
        selected_communes_objs = communes.filter(id__in=commune_ids)

    if ouvrage_ids:
        selected_ouvrages_objs = ouvrages_filtre.filter(id__in=ouvrage_ids)

    if type_designation_ids:
        selected_types_objs = types_designation.filter(id__in=type_designation_ids)

    # =========================================================================
    # 10. SÉRIALISATION JSON POUR JAVASCRIPT
    # =========================================================================

    # Sérialiser les données pour JavaScript (drill-down interactivity)
    top_pieces_quantite_json = json.dumps(top_pieces_quantite, cls=DjangoJSONEncoder, ensure_ascii=False)
    top_pieces_montant_json = json.dumps(top_pieces_montant, cls=DjangoJSONEncoder, ensure_ascii=False)
    top_ouvrages_absolu_json = json.dumps(top_ouvrages_absolu, cls=DjangoJSONEncoder, ensure_ascii=False)
    top_ouvrages_relatif_json = json.dumps(top_ouvrages_relatif, cls=DjangoJSONEncoder, ensure_ascii=False)
    stats_globales_json = json.dumps(stats_globales, cls=DjangoJSONEncoder, ensure_ascii=False)

    context = {
        'stats_globales': stats_globales,
        'top_pieces_quantite': top_pieces_quantite,
        'top_pieces_montant': top_pieces_montant,
        'top_ouvrages_absolu': top_ouvrages_absolu,
        'top_ouvrages_relatif': top_ouvrages_relatif,
        'graphique_pieces_qty': graphique_pieces_qty,
        'graphique_pieces_montant': graphique_pieces_montant,
        'graphique_ouvrages_absolu': graphique_ouvrages_absolu,
        'graphique_ouvrages_relatif': graphique_ouvrages_relatif,
        # Données JSON pour JavaScript
        'top_pieces_quantite_json': top_pieces_quantite_json,
        'top_pieces_montant_json': top_pieces_montant_json,
        'top_ouvrages_absolu_json': top_ouvrages_absolu_json,
        'top_ouvrages_relatif_json': top_ouvrages_relatif_json,
        'stats_globales_json': stats_globales_json,
        # Données pour les filtres
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages_filtre,
        'types_designation': types_designation,
        # Valeurs sélectionnées
        'selected_district': district_id,
        'selected_communes': commune_ids,
        'selected_ouvrages': ouvrage_ids,
        'selected_type_designations': type_designation_ids,
        'top_limit': top_limit,
        # Objets sélectionnés (pour affichage des noms)
        'selected_district_obj': selected_district_obj,
        'selected_communes_objs': selected_communes_objs,
        'selected_ouvrages_objs': selected_ouvrages_objs,
        'selected_types_objs': selected_types_objs,
    }

    return render(request, 'planning/analyse_pieces_rechange.html', context)


def api_detail_piece(request, designation_id):
    """
    API pour récupérer les détails d'une pièce spécifique
    Retourne tous les PlanningDetail et BonLivraison qui utilisent cette pièce
    """
    from django.http import JsonResponse
    import traceback

    try:
        # Récupérer la désignation
        designation = Designation.objects.get(id=designation_id)
    except Designation.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Désignation introuvable'}, status=404)
    except Exception as e:
        # Capturer toutes les erreurs et les retourner en JSON
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        print(f"ERREUR dans api_detail_piece: {error_msg}")
        print(error_traceback)
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {error_msg}',
            'traceback': error_traceback
        }, status=500)

    # Récupérer les PlanningDetails
    planning_details = PlanningDetail.objects.filter(
        designation_id=designation_id
    ).select_related(
        'planning',
        'planning__employe',
        'point_eau',
        'point_eau__ouvrage',
        'equipement_constitutif',
        'equipement_constitutif__ouvrage'
    ).order_by('-planning__date')[:100]

    # Récupérer les BonLivraison
    bons_livraison = BonLivraison.objects.filter(
        designation_id=designation_id
    ).select_related(
        'planning',
        'planning__employe',
        'point_eau',
        'point_eau__ouvrage',
        'equipement',
        'equipement__ouvrage'
    ).order_by('-planning__date')[:100]

    # Formatter les données
    details_list = []

    # Depuis PlanningDetail
    for pd in planning_details:
        ouvrage_nom = None
        if pd.point_eau and pd.point_eau.ouvrage:
            ouvrage_nom = pd.point_eau.ouvrage.nom_ouvrage
        elif pd.equipement_constitutif and pd.equipement_constitutif.ouvrage:
            ouvrage_nom = pd.equipement_constitutif.ouvrage.nom_ouvrage

        details_list.append({
            'type': 'PlanningDetail',
            'date': pd.planning.date.strftime('%d/%m/%Y') if pd.planning and pd.planning.date else '',
            'employe': pd.planning.employe.nom_complet if pd.planning and pd.planning.employe else '',
            'ouvrage': ouvrage_nom or '',
            'quantite': float(pd.quantite or 0),
            'montant': float(pd.montant or 0),
            'point_eau': pd.point_eau.code_point_eau if pd.point_eau else '',
            'equipement': pd.equipement_constitutif.nom if pd.equipement_constitutif else '',
        })

    # Depuis BonLivraison
    for bl in bons_livraison:
        ouvrage_nom = None
        if bl.point_eau and bl.point_eau.ouvrage:
            ouvrage_nom = bl.point_eau.ouvrage.nom_ouvrage
        elif bl.equipement and bl.equipement.ouvrage:
            ouvrage_nom = bl.equipement.ouvrage.nom_ouvrage

        # Calculer montant = quantite × prix_unitaire
        quantite = float(bl.quantite or 0)
        prix_unitaire = float(designation.prix_unitaire or 0)
        montant = quantite * prix_unitaire

        details_list.append({
            'type': 'Bon Livraison',
            'date': bl.planning.date.strftime('%d/%m/%Y') if bl.planning and bl.planning.date else '',
            'employe': bl.planning.employe.nom_complet if bl.planning and bl.planning.employe else '',
            'ouvrage': ouvrage_nom or '',
            'quantite': quantite,
            'montant': montant,
            'point_eau': bl.point_eau.code_point_eau if bl.point_eau else '',
            'equipement': bl.equipement.nom if bl.equipement else '',
        })

    # Trier par date décroissante
    details_list.sort(key=lambda x: x['date'], reverse=True)

    # Statistiques
    total_quantite = sum(d['quantite'] for d in details_list)
    total_montant = sum(d['montant'] for d in details_list)

    return JsonResponse({
        'success': True,
        'designation': {
            'id': str(designation.id),
            'nom': designation.nom,
            'type': designation.type_designation.nom if designation.type_designation else 'N/A',
            'prix_unitaire': float(designation.prix_unitaire or 0),
            'unite': designation.unite or '',
            'actif': designation.actif
        },
        'stats': {
            'total_quantite': float(total_quantite),
            'total_montant': float(total_montant),
            'nb_utilisations': len(details_list)
        },
        'details': details_list
    })


def api_detail_ouvrage(request, ouvrage_id):
    """
    API pour récupérer les détails d'un ouvrage spécifique
    Retourne toutes les pièces utilisées pour cet ouvrage
    """
    from django.http import JsonResponse
    import traceback

    try:
        # Récupérer l'ouvrage
        ouvrage = Ouvrage.objects.get(id=ouvrage_id)
    except Ouvrage.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Ouvrage introuvable'}, status=404)
    except Exception as e:
        # Capturer toutes les erreurs et les retourner en JSON
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        print(f"ERREUR dans api_detail_ouvrage: {error_msg}")
        print(error_traceback)
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {error_msg}',
            'traceback': error_traceback
        }, status=500)

    # Récupérer les PlanningDetails pour cet ouvrage
    planning_details = PlanningDetail.objects.filter(
        Q(point_eau__ouvrage_id=ouvrage_id) |
        Q(equipement_constitutif__ouvrage_id=ouvrage_id),
        designation__concerne_livraison=True
    ).select_related(
        'designation',
        'planning',
        'planning__employe'
    ).order_by('-planning__date')[:200]

    # Récupérer les BonLivraison pour cet ouvrage
    bons_livraison = BonLivraison.objects.filter(
        Q(point_eau__ouvrage_id=ouvrage_id) |
        Q(equipement__ouvrage_id=ouvrage_id),
        designation__concerne_livraison=True
    ).select_related(
        'designation',
        'planning',
        'planning__employe'
    ).order_by('-planning__date')[:200]

    # Agréger par pièce
    pieces_usage = {}

    # Depuis PlanningDetail
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

        pieces_usage[desig_id]['quantite'] += float(pd.quantity or 0)
        pieces_usage[desig_id]['montant'] += float(pd.montant or 0)
        pieces_usage[desig_id]['nb_utilisations'] += 1

    # Depuis BonLivraison
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

        quantite = float(bl.quantite or 0)
        prix_unitaire = float(bl.designation.prix_unitaire or 0)

        pieces_usage[desig_id]['quantite'] += quantite
        pieces_usage[desig_id]['montant'] += quantite * prix_unitaire
        pieces_usage[desig_id]['nb_utilisations'] += 1

    # Convertir en liste et trier
    pieces_list = sorted(
        pieces_usage.values(),
        key=lambda x: x['montant'],
        reverse=True
    )

    # Statistiques globales
    total_quantite = sum(p['quantite'] for p in pieces_list)
    total_montant = sum(p['montant'] for p in pieces_list)
    nb_pieces_diff = len(pieces_list)

    # Récupérer les infos géographiques via les points d'eau
    point_eau = ouvrage.pointeau_set.select_related(
        'parcelle__village__fokontany__commune'
    ).first()

    village_nom = ''
    commune_nom = ''
    if point_eau and point_eau.parcelle:
        if point_eau.parcelle.village:
            village_nom = point_eau.parcelle.village.nom_village
            if point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune:
                commune_nom = point_eau.parcelle.village.fokontany.commune.nom_commune

    nb_points_eau = ouvrage.pointeau_set.count()

    return JsonResponse({
        'success': True,
        'ouvrage': {
            'id': str(ouvrage.id),
            'nom': ouvrage.nom_ouvrage,
            'type': ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else 'N/A',
            'village': village_nom or 'N/A',
            'commune': commune_nom or 'N/A'
        },
        'stats': {
            'nb_points_eau': nb_points_eau,
            'total_quantite': float(total_quantite),
            'total_montant': float(total_montant),
            'nb_pieces_differentes': nb_pieces_diff
        },
        'pieces': pieces_list
    })
