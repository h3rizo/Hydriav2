"""
Vues pour le recoupement des indemnités points d'eau (compte 621102)
Paiements forfaitaires avec extraction du point d'eau depuis la description
Plafond: 5000 Ar par tranche
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Sum
from decimal import Decimal
from collections import defaultdict

from .models import BaseDiameX
from apps.billing.models import PointEau
from apps.organization.models import Base, Organisation, CompteTable
from apps.organization.scoping import get_gestionnaire_organisations_queryset, get_user_accessible_gestionnaire_ids
from .extracteurs_description import extraire_ouvrage_et_mois_generique


PLAFOND_INDEMNITE_PE_ANNUEL = Decimal('40000')


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_allowed_progs(user):
    if getattr(user, 'is_superuser', False):
        return None
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if not gestionnaire_ids:
        return []
    return list(
        Base.objects.filter(organisation_id__in=gestionnaire_ids)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )


@login_required
def recoupement_indemnites_pe(request):
    """
    Page de recoupement des indemnités points d'eau (compte 621102)

    Affichage par organisation des points d'eau avec leurs paiements
    + Section des lignes non extraites (algorithme n'a pas pu identifier le PE)
    """
    # Récupérer l'organisation de l'utilisateur connecté
    organisation_user = None
    if hasattr(request.user, 'employe') and request.user.employe:
        if request.user.employe.base and request.user.employe.base.organisation:
            organisation_user = request.user.employe.base.organisation
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)

    # Filtres
    filter_organisation = request.GET.get('organisation', '')
    filter_mois = request.GET.get('mois', '')
    filter_point_eau = request.GET.get('point_eau', '')
    filter_anomalie = request.GET.get('anomalie', '')  # depassement, non_extrait

    # Récupérer dynamiquement le compte 621102 depuis CompteTable
    comptes_indemnites = CompteTable.objects.filter(
        nom_table='indemnites_pe',
        actif=True
    ).select_related('compte').values_list('compte__compte', flat=True)

    comptes_cat = list(comptes_indemnites)

    # Si aucun compte trouvé, utiliser le compte par défaut
    if not comptes_cat:
        comptes_cat = ['621102']

    # Récupérer toutes les entrées DiameX avec ce compte
    diamex_qs = BaseDiameX.objects.filter(
        compte_code__in=comptes_cat
    ).order_by('-date_m')
    allowed_progs = _get_allowed_progs(request.user)
    if allowed_progs is not None:
        diamex_qs = diamex_qs.filter(prog__in=allowed_progs)

    # Filtre par mois
    if filter_mois:
        try:
            year, month = filter_mois.split('-')
            diamex_qs = diamex_qs.filter(date_m__year=int(year), date_m__month=int(month))
        except (ValueError, AttributeError):
            pass

    # Extraire point d'eau depuis description pour chaque ligne
    paiements_par_pe = defaultdict(list)
    lignes_non_extraites = []
    lignes_type_pe_invalide = []  # Nouvelle liste pour les anomalies de type
    stats_anomalies = {
        'depassement_annuel': 0,
        'non_extrait': 0,
        'type_pe_invalide': 0,  # Nouvelle stat
        'total_lignes': 0,
        'total_extrait': 0
    }

    for entry in diamex_qs:
        stats_anomalies['total_lignes'] += 1

        # Tenter l'extraction du point d'eau via l'extracteur générique
        # qui utilise extraire_indemnite_rbf_ppmh pour le compte 621102
        try:
            extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code) or {}
        except Exception:
            extraction = {}

        point_eau_obj = extraction.get('point_eau_obj')
        ouvrage_obj = extraction.get('ouvrage_obj')
        point_eau_idxls_extrait = extraction.get('point_eau_idxls')

        # Si un point d'eau a été trouvé, récupérer son IDxls
        # (mÃªme si l'IDxls n'était pas dans la description)
        point_eau_idxls_final = point_eau_idxls_extrait
        if point_eau_obj and hasattr(point_eau_obj, 'idxls'):
            point_eau_idxls_final = point_eau_obj.idxls

        # Récupérer le nom depuis le point d'eau ou l'ouvrage
        point_eau_nom = None
        if point_eau_obj:
            point_eau_nom = point_eau_obj.nomabonne or point_eau_obj.code_point_eau
        elif extraction.get('ouvrage_nom'):
            point_eau_nom = extraction.get('ouvrage_nom')
        else:
            point_eau_nom = 'Non extrait'

        montant_paye = entry.montant_out or 0
        annee_paiement = entry.date_m.year if entry.date_m else None

        # Détecter anomalie de type PE : ouvrage trouvé + IDxls extrait mais pas de PE BF/PMH/PMHI
        type_pe_invalide = False
        if ouvrage_obj and point_eau_idxls_extrait and not point_eau_obj:
            # Vérifier si un PE existe avec cet IDxls mais d'un type non éligible
            pe_trouve = PointEau.objects.filter(
                ouvrage=ouvrage_obj,
                idxls=point_eau_idxls_extrait
            ).select_related('type_point_eau').first()

            if pe_trouve:
                type_pe = pe_trouve.type_point_eau.nom_type if pe_trouve.type_point_eau else 'Sans type'
                type_pe_invalide = True
                stats_anomalies['type_pe_invalide'] += 1
                # Ajouter info sur le type invalide
                point_eau_nom = f"{pe_trouve.nomabonne or pe_trouve.code_point_eau} (Type: {type_pe} - NON ELIGIBLE)"

        paiement_info = {
            'id_diamex': entry.id,
            'id_access': entry.id_access,
            'prog': entry.prog,
            'date_m': entry.date_m,
            'annee_paiement': annee_paiement,
            'description': entry.description,
            'montant_out': float(montant_paye),
            'depasse_plafond': False,
            'point_eau_obj': point_eau_obj,
            'point_eau_nom': point_eau_nom,
            'point_eau_idxls': point_eau_idxls_final,  # IDxls du point d'eau trouvé (depuis description OU objet)
            'type_indemnite': extraction.get('type_indemnite'),  # RBF ou PPMH
            'ouvrage_nom': extraction.get('ouvrage_nom'),  # Nom de l'ouvrage extrait
            'scan': entry.scan,
            'fichier_source': entry.fichier_source,
            'type_pe_invalide': type_pe_invalide  # Indicateur d'anomalie
        }

        if point_eau_obj:
            # Extraction réussie - grouper par point d'eau
            stats_anomalies['total_extrait'] += 1
            pe_key = str(point_eau_obj.id)
            paiements_par_pe[pe_key].append(paiement_info)
        elif type_pe_invalide:
            # Anomalie : PE trouvé mais type non éligible (Kiosque, BP, etc.)
            lignes_type_pe_invalide.append(paiement_info)
        else:
            # Extraction échouée
            stats_anomalies['non_extrait'] += 1
            lignes_non_extraites.append(paiement_info)

    # Filtrer par organisation - récupérer les points d'eau de l'organisation
    # NOTE: Ne PAS filtrer par modalité de paiement car les indemnités RBF/PPMH peuventêtre
    # payées mÃªme si la modalité actuelle n'est plus forfaitaire (paiements rétroactifs,
    # ouvrages en transition, etc.)
    # On affiche tous les points d'eau qui ont reçu des indemnités, quelle que soit leur modalité
    points_eau_qs = PointEau.objects.all()

    # Si l'utilisateur a une organisation, filtrer automatiquement par celle-ci
    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            points_eau_qs = points_eau_qs.filter(
                ouvrage__modalites_gestion__gestionnaire_id__in=gestionnaire_ids,
                ouvrage__modalites_gestion__date_fin__isnull=True  # Modalité active
            )
        else:
            points_eau_qs = points_eau_qs.none()
    elif filter_organisation and filter_organisation != 'all':
        # Sinon, utiliser le filtre manuel (pour les admins/superusers)
        points_eau_qs = points_eau_qs.filter(
            ouvrage__modalites_gestion__gestionnaire_id=filter_organisation,
            ouvrage__modalites_gestion__date_fin__isnull=True  # Modalité active
        )

    # Filtrer par nom point d'eau
    if filter_point_eau:
        points_eau_qs = points_eau_qs.filter(
            Q(nomabonne__icontains=filter_point_eau) |
            Q(code_point_eau__icontains=filter_point_eau)
        )

    points_eau_qs = points_eau_qs.select_related(
        'ouvrage',
        'ouvrage__type_ouvrage',
        'parcelle__village__fokontany__commune',
        'parcelle__village__fokontany__commune__district'
    ).order_by(
        'parcelle__village__fokontany__commune__district__nom_district',
        'parcelle__village__fokontany__commune__nom_commune',
        'ouvrage__nom_ouvrage',
        'nomabonne'
    )

    # Construire les résultats par point d'eau avec regroupement hiérarchique
    resultats_par_district = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for pe in points_eau_qs:
        pe_key = str(pe.id)
        paiements = paiements_par_pe.get(pe_key, [])

        totaux_annuels = defaultdict(Decimal)
        for paiement in paiements:
            annee_paiement = paiement.get('annee_paiement')
            if annee_paiement is None:
                continue
            totaux_annuels[annee_paiement] += Decimal(str(paiement.get('montant_out') or 0))

        annees_depassement = []
        for annee_paiement, total_annuel in totaux_annuels.items():
            depasse = total_annuel > PLAFOND_INDEMNITE_PE_ANNUEL
            if depasse:
                annees_depassement.append({
                    'annee': annee_paiement,
                    'total': float(total_annuel),
                })
                stats_anomalies['depassement_annuel'] += 1

            for paiement in paiements:
                if paiement.get('annee_paiement') == annee_paiement:
                    paiement['depasse_plafond'] = depasse
                    paiement['total_annuel'] = float(total_annuel)

        # Calculer totaux et anomalies
        nb_paiements = len(paiements)
        total_paye = sum(p['montant_out'] for p in paiements)
        nb_depassements = len(annees_depassement)

        # Filtrer par anomalie si demandé
        if filter_anomalie == 'depassement' and nb_depassements == 0:
            continue

        # Récupérer le gestionnaire via la modalité de gestion active
        gestionnaire_nom = None
        if pe.ouvrage:
            modalite_active = pe.ouvrage.modalites_gestion.filter(date_fin__isnull=True).first()
            if modalite_active and modalite_active.gestionnaire:
                gestionnaire_nom = modalite_active.gestionnaire.nom_organisation

        # Déterminer la hiérarchie géographique
        district = None
        commune = None
        ouvrage = None

        if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
            if pe.parcelle.village.fokontany.commune:
                commune = pe.parcelle.village.fokontany.commune
                if commune.district:
                    district = commune.district

        if pe.ouvrage:
            ouvrage = pe.ouvrage

        # Clés pour regroupement
        district_key = district.nom_district if district else 'Sans district'
        commune_key = commune.nom_commune if commune else 'Sans commune'
        ouvrage_key = ouvrage.nom_ouvrage if ouvrage else 'Sans ouvrage'

        point_eau_data = {
            'point_eau': pe,
            'gestionnaire_nom': gestionnaire_nom,
            'nb_paiements': nb_paiements,
            'total_paye': total_paye,
            'nb_depassements': nb_depassements,
            'annees_depassement': sorted(annees_depassement, key=lambda item: item['annee'], reverse=True),
            'paiements': sorted(paiements, key=lambda x: x['date_m'] or '', reverse=True),
            'district_obj': district,
            'commune_obj': commune,
            'ouvrage_obj': ouvrage
        }

        resultats_par_district[district_key][commune_key][ouvrage_key].append(point_eau_data)

    # Filtrer selon type d'anomalie demandé
    if filter_anomalie == 'non_extrait':
        resultats_par_district = {}  # On affiche seulement les non extraites
        lignes_type_pe_invalide = []  # Masquer aussi les anomalies de type
    elif filter_anomalie == 'type_invalide':
        resultats_par_district = {}  # On affiche seulement les types invalides
        lignes_non_extraites = []  # Masquer les non extraites

    # Organisations pour filtre (seulement si l'utilisateur n'a pas d'organisation assignée)
    organisations = []
    if gestionnaire_ids is None:
        organisations = get_gestionnaire_organisations_queryset()

    # Calculer les stats globales depuis les résultats hiérarchiques
    total_points_eau = 0
    total_paiements = 0
    total_montant = 0
    total_depassements = 0

    for district_data in resultats_par_district.values():
        for commune_data in district_data.values():
            for ouvrage_data in commune_data.values():
                for pe_data in ouvrage_data:
                    total_points_eau += 1
                    total_paiements += pe_data['nb_paiements']
                    total_montant += pe_data['total_paye']
                    total_depassements += pe_data['nb_depassements']

    stats_globales = {
        'total_points_eau': total_points_eau,
        'total_paiements': total_paiements,
        'total_montant': total_montant,
        'total_depassements': total_depassements,
        'total_non_extrait': len(lignes_non_extraites),
        'total_type_pe_invalide': len(lignes_type_pe_invalide)
    }

    # Convertir récursivement les defaultdict en dict pour le template
    resultats_par_district_dict = {}
    for district_key, communes in resultats_par_district.items():
        resultats_par_district_dict[district_key] = {}
        for commune_key, ouvrages in communes.items():
            resultats_par_district_dict[district_key][commune_key] = dict(ouvrages)

    context = {
        'resultats_par_district': resultats_par_district_dict,  # Convertir en dict normal pour template
        'lignes_non_extraites': lignes_non_extraites,
        'lignes_type_pe_invalide': lignes_type_pe_invalide,  # Nouvelle liste d'anomalies
        'stats_globales': stats_globales,
        'stats_anomalies': stats_anomalies,
        'organisations': organisations,
        'organisation_user': organisation_user,  # Organisation de l'utilisateur connecté
        'comptes_cat': comptes_cat,
        'filter_organisation': filter_organisation,
        'filter_mois': filter_mois,
        'filter_point_eau': filter_point_eau,
        'filter_anomalie': filter_anomalie,
    }

    return render(request, 'accounting/recoupement_indemnites_pe.html', context)
