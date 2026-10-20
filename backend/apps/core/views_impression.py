"""
Vues d'impression pour les dashboards
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from apps.billing.models import PointEau, ModaliteGestion, Releve, PaiementForfaitaire
from apps.geography.models import Region, District, Commune
from apps.organization.models import Ouvrage
from apps.organization.scoping import apply_user_responsable_ouvrage_scope
from apps.accounting.dashboard_employee_filter import resolve_dashboard_employee_filter
from datetime import datetime
from decimal import Decimal
from apps.billing.tarifs_forfaitaires import tarif_pour_annee
from collections import defaultdict
import pytz
import calendar

def normalize_date(d):
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        try:
            return datetime.fromisoformat(d.replace(" ", "T")).date()
        except:
            try:
                return datetime.strptime(d.split(" ")[0], "%Y-%m-%d").date()
            except:
                return None
    return d


@login_required
def impression_paiements_forfaitaires(request):
    """
    Vue d'impression pour le dashboard des paiements forfaitaires
    """
    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    region_filter = request.GET.get('region', '')
    district_filter = request.GET.get('district', '')
    communes_param = request.GET.get('communes', '')  # Liste séparée par virgules
    commune_id = request.GET.get('commune', '')  # Filtre simple (fallback)
    communes_ids = [c for c in communes_param.split(',') if c] if communes_param else []
    ouvrage_id = request.GET.get('ouvrage', '')
    employe_filter = request.GET.get('employe', '')
    annee = int(request.GET.get('annee', str(datetime.now().year)))
    avec_dates = request.GET.get('avec_dates') == '1'
    calendrier = request.GET.get('calendrier') == '1'
    impayes_echus = request.GET.get('impayes_echus', '')
    recap_mois_raw = request.GET.get('recap_mois', '')
    regroupement_impression = request.GET.get('regroupement', 'commune')
    if regroupement_impression not in {'commune', 'employe'}:
        regroupement_impression = 'commune'
    try:
        recap_mois = int(recap_mois_raw)
        if recap_mois < 1 or recap_mois > 12:
            recap_mois = None
    except (TypeError, ValueError):
        recap_mois = None

    # CRITICAL: Récupérer uniquement les ouvrages avec modalité forfaitaire ou mixte
    ouvrages_forfaitaires_ids = set(
        ModaliteGestion.objects.filter(
        date_fin__isnull=True,  # Modalité active
        modalitepaiement__in=['forfaitaire', 'mixte']
        ).values_list('ouvrage_id', flat=True).distinct()
    )
    ouvrages_forfaitaires_ids = apply_user_responsable_ouvrage_scope(
        ouvrages_forfaitaires_ids,
        request.user,
    )
    employes_responsables, ouvrages_forfaitaires_ids = resolve_dashboard_employee_filter(
        ouvrages_forfaitaires_ids,
        employe_filter,
    )
    if employe_filter and not any(
        str(option.get('id', '')) == str(employe_filter)
        for option in employes_responsables
    ):
        employe_filter = ''
    if regroupement_impression == 'employe' and not employe_filter:
        regroupement_impression = 'commune'
    employe_nom = next((
        option.get('label', '')
        for option in employes_responsables
        if str(option.get('id', '')) == str(employe_filter)
    ), '')

    # Options géographiques disponibles pour les filtres
    points_eau_geo_base = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=ouvrages_forfaitaires_ids
    )

    region_ids = points_eau_geo_base.values_list(
        'parcelle__village__fokontany__commune__district__region_id', flat=True
    ).distinct()
    district_ids = points_eau_geo_base.values_list(
        'parcelle__village__fokontany__commune__district_id', flat=True
    ).distinct()
    commune_ids = points_eau_geo_base.values_list(
        'parcelle__village__fokontany__commune_id', flat=True
    ).distinct()

    regions = Region.objects.filter(id__in=region_ids).only(
        'id', 'nom_region'
    ).order_by('nom_region')
    districts_all = District.objects.filter(id__in=district_ids).select_related('region').only(
        'id', 'nom_district', 'region_id', 'region__id', 'region__nom_region'
    ).order_by('nom_district')
    communes_all = Commune.objects.filter(id__in=commune_ids).select_related('district__region').only(
        'id', 'nom_commune', 'district_id',
        'district__id', 'district__nom_district', 'district__region_id',
        'district__region__id', 'district__region__nom_region',
    ).order_by('district__nom_district', 'nom_commune')

    districts = districts_all
    if region_filter and region_filter != 'all':
        districts = districts.filter(region_id=region_filter)

    communes = communes_all
    if district_filter and district_filter != 'all':
        communes = communes.filter(district_id=district_filter)
    elif region_filter and region_filter != 'all':
        communes = communes.filter(district__region_id=region_filter)

    # Filtrer les points d'eau avec tarif forfaitaire non null ET modalité forfaitaire/mixte
    points_eau = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=ouvrages_forfaitaires_ids
    ).select_related(
        'ouvrage',
        'ouvrage__type_ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune'
    ).only(
        'id', 'code_point_eau', 'idxls', 'nomabonne', 'tarifforfaitaire', 'pourcentage_tarif',
        'datearretbranchement', 'ouvrage_id', 'type_point_eau_id', 'parcelle_id',
        'ouvrage__id', 'ouvrage__nom_ouvrage', 'ouvrage__saisonnier',
        'ouvrage__type_ouvrage_id', 'ouvrage__type_ouvrage__id',
        'ouvrage__type_ouvrage__nom_type_ouvrage',
        'type_point_eau__id', 'type_point_eau__nom_type',
        'parcelle__id', 'parcelle__village_id',
        'parcelle__village__id', 'parcelle__village__nom_village',
        'parcelle__village__fokontany_id',
        'parcelle__village__fokontany__id',
        'parcelle__village__fokontany__commune_id',
        'parcelle__village__fokontany__commune__id',
        'parcelle__village__fokontany__commune__nom_commune',
    )

    if region_filter and region_filter != 'all':
        points_eau = points_eau.filter(parcelle__village__fokontany__commune__district__region_id=region_filter)

    if district_filter and district_filter != 'all':
        points_eau = points_eau.filter(parcelle__village__fokontany__commune__district_id=district_filter)

    # Filtre par communes (multi-sélection ou simple)
    if communes_ids:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune_id__in=communes_ids)
    elif commune_id and commune_id != 'all':
        points_eau = points_eau.filter(parcelle__village__fokontany__commune_id=commune_id)

    if ouvrage_id:
        points_eau = points_eau.filter(ouvrage_id=ouvrage_id)

    mois_noms_complets = [
        'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
    ]
    recap_groupes = []
    recap_total_lignes = 0
    recap_total_quantite = 0
    recap_total_montant = Decimal('0')
    if recap_mois:
        recap_paiements = (
            PaiementForfaitaire.objects.filter(
                point_eau__in=points_eau,
                date_facture__year=annee,
                date_facture__month=recap_mois,
            )
            .select_related(
                'point_eau',
                'point_eau__ouvrage',
                'point_eau__parcelle__village__fokontany__commune',
                'planning',
                'planning__employe',
            )
            .only(
                'id', 'point_eau_id', 'planning_id', 'date_facture',
                'quantite', 'prix_unitaire', 'montant', 'numeroDiameX', 'baseDiameX',
                'point_eau__id', 'point_eau__idxls', 'point_eau__nomabonne',
                'point_eau__code_point_eau', 'point_eau__ouvrage_id', 'point_eau__parcelle_id',
                'point_eau__ouvrage__id', 'point_eau__ouvrage__nom_ouvrage',
                'point_eau__parcelle__id', 'point_eau__parcelle__village_id',
                'point_eau__parcelle__village__id',
                'point_eau__parcelle__village__fokontany_id',
                'point_eau__parcelle__village__fokontany__id',
                'point_eau__parcelle__village__fokontany__commune_id',
                'point_eau__parcelle__village__fokontany__commune__id',
                'point_eau__parcelle__village__fokontany__commune__nom_commune',
                'planning__id', 'planning__employe_id',
                'planning__employe__id', 'planning__employe__surnom',
                'planning__employe__prenom', 'planning__employe__nom',
            )
            .order_by(
                'planning__employe__surnom',
                'planning__employe__nom',
                'point_eau__parcelle__village__fokontany__commune__nom_commune',
                'point_eau__ouvrage__nom_ouvrage',
                'point_eau__idxls',
            )
        )
        grouped_rows = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for paiement in recap_paiements:
            point_eau = paiement.point_eau
            commune_obj = getattr(
                getattr(
                    getattr(getattr(point_eau, 'parcelle', None), 'village', None),
                    'fokontany',
                    None,
                ),
                'commune',
                None,
            )
            commune_nom = getattr(commune_obj, 'nom_commune', '') or 'Commune non renseignée'
            ouvrage_nom = getattr(getattr(point_eau, 'ouvrage', None), 'nom_ouvrage', '') or 'Ouvrage non renseigné'
            planning_employe = getattr(getattr(paiement, 'planning', None), 'employe', None)
            paiement_employe_nom = getattr(planning_employe, 'nom_affichage', '') or 'Non assigné'
            groupe_nom = (
                commune_nom
                if regroupement_impression == 'commune'
                else (employe_nom or paiement_employe_nom or 'Non assigné')
            )
            quantite = int(paiement.quantite or 0)
            prix_unitaire = Decimal(str(paiement.prix_unitaire or 0))
            montant = Decimal(str(paiement.montant or 0))
            grouped_rows[groupe_nom][commune_nom][ouvrage_nom].append({
                'idxls': point_eau.idxls or '-',
                'nom_abonne': point_eau.nomabonne or point_eau.code_point_eau or '-',
                'quantite': quantite,
                'prix_unitaire': prix_unitaire,
                'montant': montant,
                'statut': 'Payé' if paiement.est_paye else 'Non payé',
                'est_paye': paiement.est_paye,
            })
            recap_total_lignes += 1
            recap_total_quantite += quantite
            recap_total_montant += montant

        for groupe_nom in sorted(grouped_rows, key=lambda value: value.casefold()):
            communes_groupe = []
            groupe_quantite = 0
            groupe_montant = Decimal('0')
            for commune_nom in sorted(grouped_rows[groupe_nom], key=lambda value: value.casefold()):
                ouvrages_groupe = []
                for ouvrage_nom in sorted(grouped_rows[groupe_nom][commune_nom], key=lambda value: value.casefold()):
                    lignes = grouped_rows[groupe_nom][commune_nom][ouvrage_nom]
                    lignes.sort(key=lambda row: str(row['idxls']).casefold())
                    total_quantite = sum(row['quantite'] for row in lignes)
                    total_montant = sum((row['montant'] for row in lignes), Decimal('0'))
                    groupe_quantite += total_quantite
                    groupe_montant += total_montant
                    ouvrages_groupe.append({
                        'nom': ouvrage_nom,
                        'lignes': lignes,
                        'total_quantite': total_quantite,
                        'total_montant': total_montant,
                    })
                communes_groupe.append({
                    'nom': commune_nom,
                    'ouvrages': ouvrages_groupe,
                })
            recap_groupes.append({
                'nom': groupe_nom,
                'communes': communes_groupe,
                'total_quantite': groupe_quantite,
                'total_montant': groupe_montant,
            })

    # --- LOGIQUE YTD (Date Limite) ---
    today = datetime.now().date()
    debut_annee_limit = datetime(annee, 1, 1).date()
    fin_annee_limit = datetime(annee, 12, 31).date()
    
    if annee < today.year:
        limit_date = fin_annee_limit
    else:
        limit_date = min(today, fin_annee_limit)

    if limit_date < debut_annee_limit:
        limit_date = debut_annee_limit

    # --- HELPER FINANCIER (Dupliqué pour isolation) ---
    from apps.billing.models import CoupureEau
    def calculate_details_financiers(pe, annee, limit_date):
        tarif = tarif_pour_annee(pe, annee)
        if tarif == 0:
            return Decimal('0.00'), Decimal('0.00'), Decimal('0.00')

        debut_annee_calc = datetime(annee, 1, 1).date()

        if limit_date < debut_annee_calc:
            nb_mois_ecoules = 0
        else:
            delta_jours = (limit_date - debut_annee_calc).days + 1
            nb_mois_ecoules = int(round(delta_jours / 30.4))

            # CRITICAL: Compter au minimum 1 mois si on est dans l'année (évite 0 en début janvier)
            if nb_mois_ecoules == 0 and limit_date >= debut_annee_calc:
                nb_mois_ecoules = 1

        montant_brut = (tarif / 3) * nb_mois_ecoules

        # Décote basée sur les coupures
        or_debut = CoupureEau.objects.filter(point_eau=pe, date_evenement__lt=debut_annee_calc).order_by('-date_evenement').first()
        est_coupe = (or_debut and or_debut.type_evenement == 'coupure')
        date_debut_coupure = debut_annee_calc if est_coupe else None

        evenements = CoupureEau.objects.filter(point_eau=pe, date_evenement__year=annee, date_evenement__lte=limit_date).order_by('date_evenement')
        periodes = []

        for evt in evenements:
            if evt.type_evenement == 'remise':
                if est_coupe:
                    periodes.append({'debut': date_debut_coupure, 'fin': evt.date_evenement})
                    est_coupe = False
                    date_debut_coupure = None
                elif date_debut_coupure:
                    periodes.append({'debut': date_debut_coupure, 'fin': evt.date_evenement})
                    date_debut_coupure = None
            elif evt.type_evenement == 'coupure':
                if not est_coupe and not date_debut_coupure:
                    date_debut_coupure = evt.date_evenement
        
        if est_coupe or date_debut_coupure:
            d = date_debut_coupure if date_debut_coupure else debut_annee_calc
            periodes.append({'debut': d, 'fin': limit_date})

        decote = Decimal('0.00')
        for p in periodes:
            nb = int(round((p['fin'] - p['debut']).days / 30.4))
            decote += (tarif / 3) * nb

        net = max(Decimal('0.00'), montant_brut - decote)
        return montant_brut, decote, net

    # Construire les données pour l'impression
    points_eau_list = []
    mois_labels = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']

    # Statistiques globales
    nb_tout_paye = 0
    nb_partiellement_paye = 0
    nb_non_paye = 0
    nb_coupe = 0
    montant_prevu_total = Decimal('0.00')
    montant_planifie_total = Decimal('0.00')
    montant_paye_total = Decimal('0.00')
    decote_totale_globale = Decimal('0.00')

    for pe in points_eau:
        # Calculer les détails financiers YTD
        brut, decote_pe, net = calculate_details_financiers(pe, annee, limit_date)
        tarif = tarif_pour_annee(pe, annee)

        # Récupérer tous les paiements forfaitaires pour ce point d'eau
        paiements_pe = PaiementForfaitaire.objects.filter(point_eau=pe).select_related(
            'planning',
            'planning__employe',
        )

        # Calculer les paiements par trimestre (pour le statut) et par mois (pour le tableau)
        trimestres = {
            'T1': {'paye': 0, 'non_paye': 0, 'mois': [1, 2, 3]},
            'T2': {'paye': 0, 'non_paye': 0, 'mois': [4, 5, 6]},
            'T3': {'paye': 0, 'non_paye': 0, 'mois': [7, 8, 9]},
            'T4': {'paye': 0, 'non_paye': 0, 'mois': [10, 11, 12]},
        }
        mois_stats = {
            mois_num: {'paye': 0, 'non_paye': 0, 'dates': []}
            for mois_num in range(1, 13)
        }
        paiements_calendrier = []

        pe_montant_paye = Decimal('0.00')
        pe_montant_planifie = Decimal('0.00')

        for paiement in paiements_pe:
            date_facture = paiement.date_facture
            if not date_facture:
                continue

            # Stats année entière (trimestres + mois)
            if date_facture.year == annee:
                mois = date_facture.month
                quantite = int(paiement.quantite) if paiement.quantite else 1
                est_paye = bool(paiement.numeroDiameX)

                if est_paye:
                    mois_stats[mois]['paye'] += quantite
                else:
                    mois_stats[mois]['non_paye'] += quantite

                for trimestre, data in trimestres.items():
                    if mois in data['mois']:
                        if est_paye:
                            data['paye'] += quantite
                        else:
                            data['non_paye'] += quantite

                        if avec_dates or calendrier:
                            commune_nom_pe = 'N/D'
                            if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany and pe.parcelle.village.fokontany.commune:
                                commune_nom_pe = pe.parcelle.village.fokontany.commune.nom_commune

                            planning_employe = getattr(getattr(paiement, 'planning', None), 'employe', None)
                            paiement_employe_nom = getattr(planning_employe, 'nom_affichage', '') or ''
                            date_payload = {
                                'date': date_facture,
                                'paye': est_paye,
                                'employe': employe_nom if regroupement_impression == 'employe' and employe_nom else paiement_employe_nom,
                                'quantite': quantite,
                                'idxls': pe.idxls or '-',
                                'point_eau_idxls': pe.idxls or '-',
                                'point_eau_nom': pe.nomabonne or '-',
                                'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else '-',
                                'commune': commune_nom_pe
                            }
                            if avec_dates:
                                mois_stats[mois]['dates'].append(date_facture)
                            if calendrier:
                                paiements_calendrier.append(date_payload)
                        break

            # Stats globales YTD (Planifié et Payé jusqu'à limit_date)
            if date_facture.year == annee and date_facture <= limit_date:
                if paiement.montant:
                    pe_montant_planifie += paiement.montant
                    if paiement.numeroDiameX:
                        pe_montant_paye += paiement.montant

        # Calculer les totaux pour ce point d'eau
        qte_payee = sum(t['paye'] for t in trimestres.values())
        qte_non_payee = sum(t['non_paye'] for t in trimestres.values())
        qte_totale = qte_payee + qte_non_payee

        # Contrôle tranches: logique alignée avec le dashboard principal
        tranches_reference = 4
        tranches_ecart = qte_totale - tranches_reference
        if tranches_ecart == 0:
            tranches_controle_badge = 'success'
            tranches_controle_action = 'Conforme'
            tranches_controle_detail = 'Somme des tranches = 4'
        elif tranches_ecart < 0:
            tranches_controle_badge = 'warning'
            tranches_controle_action = f'Ajouter {abs(tranches_ecart)}'
            tranches_controle_detail = f'{abs(tranches_ecart)} tranche(s) manquante(s)'
        else:
            tranches_controle_badge = 'error'
            tranches_controle_action = f'Supprimer {tranches_ecart} ou expliquer'
            tranches_controle_detail = f'{tranches_ecart} tranche(s) en trop'

        # Déterminer le statut
        est_coupe = pe.datearretbranchement is not None

        if est_coupe:
            statut = 'coupe'
            statut_label = 'Coupé'
            nb_coupe += 1
        elif qte_totale == 0:
            statut = 'non_paye'
            statut_label = 'Non payé'
            nb_non_paye += 1
        elif qte_non_payee == 0 and qte_payee > 0:
            statut = 'tout_paye'
            statut_label = 'Tout payé'
            nb_tout_paye += 1
        else:
            statut = 'partiellement_paye'
            statut_label = 'Partiellement payé'
            nb_partiellement_paye += 1

        # Cumuler les statistiques globales YTD
        montant_prevu_total += net
        montant_paye_total += pe_montant_paye
        montant_planifie_total += pe_montant_planifie
        decote_totale_globale += decote_pe

        points_eau_list.append({
            'id': pe.id,
            'code': pe.code_point_eau or '-',
            'idxls': pe.idxls or '-',
            'nom': pe.nomabonne or '-',
            'type': pe.type_point_eau.nom_type if pe.type_point_eau else '-',
            'village': pe.parcelle.village.nom_village if pe.parcelle and pe.parcelle.village else '-',
            'commune': pe.parcelle.village.fokontany.commune.nom_commune if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany and pe.parcelle.village.fokontany.commune else '-',
            'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else '-',
            'ouvrage_type': pe.ouvrage.type_ouvrage.nom_type_ouvrage if pe.ouvrage and pe.ouvrage.type_ouvrage else '-',
            'ouvrage_saisonnier': pe.ouvrage.saisonnier if pe.ouvrage else False,
            'tarif': float(tarif) / 1000,
            'montant_prevu': float(net) / 1000,
            'montant_paye': float(pe_montant_paye) / 1000,
            'montant_planifie': float(pe_montant_planifie) / 1000,
            'mois_data': [
                {
                    'numero': mois_num,
                    'label': mois_labels[mois_num - 1],
                    'paye': mois_stats[mois_num]['paye'],
                    'non_paye': mois_stats[mois_num]['non_paye'],
                    'dates': mois_stats[mois_num]['dates'],
                }
                for mois_num in range(1, 13)
            ],
            'trimestres': trimestres,
            'paiements_calendrier': paiements_calendrier,
            'qte_payee': qte_payee,
            'qte_totale': qte_totale,
            'tranches_reference': tranches_reference,
            'tranches_annuelles': qte_totale,
            'tranches_ecart': tranches_ecart,
            'tranches_controle_badge': tranches_controle_badge,
            'tranches_controle_action': tranches_controle_action,
            'tranches_controle_detail': tranches_controle_detail,
            'statut': statut,
            'statut_label': statut_label,
            'est_coupe': est_coupe,
            'est_tout_paye': (statut == 'tout_paye'),
        })

    # Calculer les taux de recouvrement
    taux_recouvrement_prevu = int((montant_paye_total / montant_prevu_total * 100) if montant_prevu_total > 0 else 0)
    taux_recouvrement_planifie = int((montant_paye_total / montant_planifie_total * 100) if montant_planifie_total > 0 else 0)

    # Organiser par commune puis par ouvrage
    points_par_commune = defaultdict(lambda: defaultdict(list))

    for pe_data in points_eau_list:
        commune = pe_data['commune']
        ouvrage = pe_data['ouvrage']
        points_par_commune[commune][ouvrage].append(pe_data)

    # Convertir en liste triée pour le template
    communes_organisees = []
    import re
    
    def get_pe_sort_key(pe_data):
        idxls = str(pe_data.get('idxls', '')).strip()
        try:
            match = re.search(r'\d+', idxls)
            num = int(match.group()) if match else 999999
        except (ValueError, TypeError, AttributeError):
            num = 999999
        return (num, idxls)

    for commune in sorted(points_par_commune.keys()):
        ouvrages_data = []
        for ouvrage in sorted(points_par_commune[commune].keys()):
            # Trier les points d'eau par IDXls numérique
            points_tries = sorted(points_par_commune[commune][ouvrage], key=get_pe_sort_key)
            is_saisonnier = points_tries[0]['ouvrage_saisonnier'] if points_tries else False
            
            # Calculer stats pour cet ouvrage
            o_nb_pe = len(points_tries)
            o_nb_coupe = sum(1 for p in points_tries if p['est_coupe'])
            o_nb_tout_paye = sum(1 for p in points_tries if p['statut'] in ['tout_paye', 'en_trop'])
            o_prevu = sum(p['montant_prevu'] for p in points_tries)
            o_paye = sum(p['montant_paye'] for p in points_tries)
            o_taux = int((o_paye / o_prevu * 100) if o_prevu > 0 else 0)

            ouvrages_data.append({
                'nom': ouvrage,
                'saisonnier': is_saisonnier,
                'points_eau': points_tries,
                'type_ouvrage': points_tries[0]['ouvrage_type'] if points_tries else '-',
                'nb_pe': o_nb_pe,
                'nb_coupe': o_nb_coupe,
                'nb_tout_paye': o_nb_tout_paye,
                'taux': o_taux
            })
        # Calculer stats pour cette commune
        c_nb_ouvrages = len(ouvrages_data)
        c_nb_pe = sum(o['nb_pe'] for o in ouvrages_data)
        c_nb_coupe = sum(o['nb_coupe'] for o in ouvrages_data)
        c_nb_tout_paye = sum(o['nb_tout_paye'] for o in ouvrages_data)
        
        # Aggregate amounts from points_eau to get exact recovery rate
        c_prevu = sum(p['montant_prevu'] for o in ouvrages_data for p in o['points_eau'])
        c_paye = sum(p['montant_paye'] for o in ouvrages_data for p in o['points_eau'])
        c_taux = int((c_paye / c_prevu * 100) if c_prevu > 0 else 0)

        communes_organisees.append({
            'nom': commune,
            'ouvrages': ouvrages_data,
            'nb_ouvrages': c_nb_ouvrages,
            'nb_pe': c_nb_pe,
            'nb_coupe': c_nb_coupe,
            'nb_tout_paye': c_nb_tout_paye,
            'taux': c_taux
        })

    # Normaliser les dates pour l'affichage mensuel
    for commune in communes_organisees:
        for ouvrage in commune["ouvrages"]:
            for pe in ouvrage["points_eau"]:
                for mois in pe.get("mois_data", []):
                    mois["dates"] = [
                        normalize_date(d)
                        for d in mois.get("dates", [])
                        if normalize_date(d) is not None
                    ]

    # L'en-tête doit refléter les communes réellement présentes après tous les
    # filtres, notamment le périmètre de l'employé sélectionné.
    communes_noms = [commune['nom'] for commune in communes_organisees]

    region_nom = ''
    if region_filter and region_filter != 'all':
        region_obj = Region.objects.filter(id=region_filter).only('nom_region').first()
        if region_obj:
            region_nom = region_obj.nom_region

    district_nom = ''
    if district_filter and district_filter != 'all':
        district_obj = District.objects.filter(id=district_filter).only('nom_district').first()
        if district_obj:
            district_nom = district_obj.nom_district

    ouvrage_nom = ''
    if ouvrage_id:
        try:
            ouvrage_nom = Ouvrage.objects.get(id=ouvrage_id).nom_ouvrage
        except Ouvrage.DoesNotExist:
            pass

    # Liste des jours fériés à Madagascar pour l'année donnée
    import datetime as dt
    jours_feries = [
        dt.date(annee, 1, 1),   # Nouvel an
        dt.date(annee, 3, 29),  # Journée des martyrs
        dt.date(annee, 5, 1),   # Fête du travail
        dt.date(annee, 5, 25),  # Journée de l'Afrique
        dt.date(annee, 6, 26),  # Fête de l'indépendance
        dt.date(annee, 8, 15),  # Assomption
        dt.date(annee, 11, 1),  # Toussaint
        dt.date(annee, 12, 25), # Noël
    ]
    if annee == 2026:
        jours_feries.append(dt.date(2026, 5, 27))  # Aid-el-filtr

    # Calculer le nombre total d'ouvrages uniques
    nb_ouvrages = sum(len(c['ouvrages']) for c in communes_organisees)

    context = {
        'communes_organisees': communes_organisees,
        'annee': annee,
        'communes_noms': ', '.join(communes_noms) if communes_noms else 'Toutes',
        'region_nom': region_nom,
        'district_nom': district_nom,
        'ouvrage_nom': ouvrage_nom,
        'nb_points_eau': len(points_eau_list),
        'nb_ouvrages': nb_ouvrages,
        'nb_tout_paye': nb_tout_paye,
        'nb_partiellement_paye': nb_partiellement_paye,
        'nb_non_paye': nb_non_paye,
        'nb_coupe': nb_coupe,
        'montant_prevu_total': float(montant_prevu_total) / 1000,
        'montant_planifie_total': float(montant_planifie_total) / 1000,
        'montant_paye_total': float(montant_paye_total) / 1000,
        'decote_totale_globale': float(decote_totale_globale) / 1000,
        'taux_recouvrement_prevu': taux_recouvrement_prevu,
        'taux_recouvrement_planifie': taux_recouvrement_planifie,
        'date_impression': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'avec_dates': avec_dates,
        'impayes_echus': impayes_echus,
        'regions': regions,
        'districts': districts,
        'districts_all': districts_all,
        'communes': communes,
        'communes_all': communes_all,
        'region_filter': region_filter,
        'district_filter': district_filter,
        'commune_filter': commune_id,
        'ouvrage_id': ouvrage_id,
        'employe_filter': employe_filter,
        'employe_nom': employe_nom,
        'employes_responsables': employes_responsables,
        'recap_mois': recap_mois,
        'recap_mois_nom': mois_noms_complets[recap_mois - 1] if recap_mois else '',
        'regroupement_impression': regroupement_impression,
        'recap_groupes': recap_groupes,
        'recap_total_lignes': recap_total_lignes,
        'recap_total_quantite': recap_total_quantite,
        'recap_total_montant': recap_total_montant,
        'mois_colonnes': [{'numero': idx + 1, 'label': label} for idx, label in enumerate(mois_labels)],
        'jours_feries': jours_feries,
    }

    # Choisir le template selon la version demandée
    if calendrier:
        # Préparer les données pour la vue calendrier (12 mois)
        calendrier_mois = []
        mois_noms = [
            'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        ]

        for mois_num in range(1, 13):
            # Obtenir le calendrier du mois (semaines)
            cal = calendar.monthcalendar(annee, mois_num)

            # Dictionnaire des paiements par jour {jour: [paiements]}
            paiements_par_jour = defaultdict(list)

            # Collecter tous les paiements de ce mois
            for pe_data in points_eau_list:
                for date_info in pe_data.get('paiements_calendrier', []):
                    date_paiement = date_info.get('date')
                    if not date_paiement:
                        continue

                    if date_paiement.month == mois_num:
                        jour = date_paiement.day
                        paiements_par_jour[jour].append({
                            'idxls': date_info.get('point_eau_idxls', pe_data['code']),
                            'nom': date_info.get('point_eau_nom', pe_data['nom']),
                            'ouvrage': date_info.get('ouvrage', pe_data.get('ouvrage', '-')),
                            'employe': date_info.get('employe', ''),
                            'quantite': date_info.get('quantite', 1),
                            'paye': date_info.get('paye', False),
                            'commune': date_info.get('commune', 'N/D')
                        })

            calendrier_mois.append({
                'numero': mois_num,
                'nom': mois_noms[mois_num - 1],
                'semaines': cal,  # Liste de semaines (chaque semaine = liste de 7 jours, 0 = jour vide)
                'paiements': dict(paiements_par_jour)
            })

        context['calendrier_mois'] = calendrier_mois
        return render(request, 'core/impression_paiements_calendrier.html', context)
    else:
        return render(request, 'core/impression_paiements_forfaitaires.html', context)


@login_required
def impression_gestion_volumetrique(request):
    """
    Vue d'impression pour le suivi matriciel volumétrique avec regroupement par parcelle
    """
    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    communes_param = request.GET.get('communes', '')  # Multi-sélection (liste séparée par virgules)
    commune_id = request.GET.get('commune', '')  # Simple sélection (fallback)
    ouvrage_id = request.GET.get('ouvrage', '')
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    semestre = request.GET.get('semestre', 'all')
    if semestre not in {'1', '2'}:
        semestre = 'all'
    non_pointes_totalement = request.GET.get('non_pointes_totalement', '') == '1'

    if semestre == '1':
        mois_liste = list(range(1, 7))
        periode_libelle = '1er semestre (janvier à juin)'
    elif semestre == '2':
        mois_liste = list(range(7, 13))
        periode_libelle = '2e semestre (juillet à décembre)'
    else:
        mois_liste = list(range(1, 13))
        periode_libelle = 'Année complète'

    tous_mois_noms = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']
    mois_noms = [tous_mois_noms[mois - 1] for mois in mois_liste]

    # Split mois passés / mois en cours (blocs KPI + colonnes de synthèse),
    # restreint à la période affichée (semestre éventuel).
    from django.utils import timezone as _dj_tz
    from apps.accounting.volume_recovery import (
        build_recouvrement_par_ouvrage_mois,
        build_score_totals_from_releves,
        build_volume_kpis,
        split_mois,
    )
    _today_mg = _dj_tz.localdate()
    annee_int = int(annee_filter)
    _mp, _mc = split_mois(annee_int, _today_mg)
    mois_liste_set = set(mois_liste)
    mois_passes_set = _mp & mois_liste_set
    mois_en_cours_num = _mc if (_mc in mois_liste_set) else None
    mois_courant_set = {mois_en_cours_num} if mois_en_cours_num else set()

    def _split_counts(mois_dict, numeros):
        tot = sum(m['total'] for k, m in mois_dict.items() if k in numeros)
        pay = sum(m['payes'] for k, m in mois_dict.items() if k in numeros)
        imp = sum(m['impayes'] for k, m in mois_dict.items() if k in numeros)
        return tot, pay, imp, (int(round(pay / tot * 100)) if tot else 0)

    # Récupérer les points d'eau avec modalité volumétrique
    ouvrages_ids = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['au_volume', 'mixte']
    ).values_list('ouvrage_id', flat=True).distinct()

    points_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_ids
    ).select_related(
        'ouvrage',
        'parcelle',
        'parcelle__village__fokontany__commune',
        'type_point_eau'
    )

    # Filtrer par commune (multi-sélection ou simple)
    a_un_perimetre_commune = bool(communes_param) or bool(commune_id and commune_id != 'all')
    if communes_param:
        communes_ids = communes_param.split(',')
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune_id__in=communes_ids
        )
    elif commune_id and commune_id != 'all':
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune_id=commune_id
        )

    # Filtrer par ouvrage. L'impression accepte un perimetre = une/des commune(s)
    # (tous leurs ouvrages) OU un ouvrage precis. Ce n'est que sans aucun
    # perimetre qu'on n'affiche rien.
    if ouvrage_id and ouvrage_id != 'all':
        points_eau_qs = points_eau_qs.filter(ouvrage_id=ouvrage_id)
    elif not a_un_perimetre_commune:
        points_eau_qs = PointEau.objects.none()

    # Récupérer les relevés de l'année
    # CRITICAL: Ne garder que les relevés avec montant > 0 (factures réelles)
    # ET exclure les relevés avec "coupé" dans la remarque (pas de facture à recouvrer)
    releves = Releve.objects.filter(
        point_eau__in=points_eau_qs
    ).exclude(
        Q(montant__isnull=True) | Q(montant=0) | Q(remarque__icontains='coupé')
    ).select_related('point_eau__ouvrage', 'point_eau__type_point_eau').order_by('datereleve')

    # Même règle métier que le Dashboard Paiements Volume : ne pas recouvrer
    # les factures dont le mois facturé chevauche une période de coupure.
    from apps.accounting.views import _build_coupure_periods_by_point, _is_releve_during_coupure
    point_eau_ids = [str(point_id) for point_id in points_eau_qs.values_list('id', flat=True)]
    periodes_coupure = _build_coupure_periods_by_point(point_eau_ids)
    releves = [
        releve for releve in releves
        if not _is_releve_during_coupure(
            releve,
            periodes_coupure,
            check_facturation_month=True,
        )
    ]

    # Organiser les données par point d'eau et mois
    donnees_matricielles = {}
    for pe in points_eau_qs:
        donnees_matricielles[str(pe.id)] = {
            'point_eau': pe,
            'mois': {mois: {'paye': False, 'montant': 0, 'releve_id': None} for mois in mois_liste}
        }

    # Remplir les données des relevés
    for releve in releves:
        if not releve.datereleve:
            continue

        date_obj = releve.datereleve

        # CRITICAL: La facture est pour le mois SUIVANT le relevé
        # Un relevé de mars → facture d'avril
        from dateutil.relativedelta import relativedelta
        date_facture = date_obj + relativedelta(months=1)

        # Filtrer par année (année de la facture, pas du relevé)
        if date_facture.year != int(annee_filter):
            continue

        pe_id = str(releve.point_eau.id)
        mois = date_facture.month

        if mois not in mois_liste:
            continue

        if pe_id in donnees_matricielles:
            # Vérifier si payé (numeroDiameX renseigné)
            est_paye = bool(releve.numeroDiameX and str(releve.numeroDiameX).strip())

            donnees_matricielles[pe_id]['mois'][mois] = {
                'paye': est_paye,
                'montant': float(releve.montant) if releve.montant else 0,
                'releve_id': str(releve.id),
                'date_releve': date_obj.strftime('%d/%m/%Y')
            }

    # Préparer les données pour le template
    points_eau_data = []
    stats_globales = {
        'total_factures': 0,
        'factures_payees': 0,
        'factures_impayees': 0,
        'montant_impaye': 0,
        'points_eau_coupes': 0,
        'points_eau_tout_paye': 0
    }

    for pe_id, data in donnees_matricielles.items():
        pe = data['point_eau']
        mois_data = data['mois']

        # Calculer stats par ligne
        nb_releves = sum(1 for m in mois_data.values() if m['releve_id'] and m['montant'] > 0)
        nb_payes = sum(1 for m in mois_data.values() if m['paye'] and m['montant'] > 0)
        nb_impayes = nb_releves - nb_payes
        montant_impaye = sum(
            m['montant'] for m in mois_data.values()
            if m['releve_id'] and m['montant'] > 0 and not m['paye']
        )
        taux = int(round(nb_payes / nb_releves * 100)) if nb_releves > 0 else 0

        # Vérifier si point d'eau coupé (datearretbranchement renseigné)
        est_coupe = pe.is_cut

        # Vérifier si toutes les factures sont payées
        tout_paye = nb_releves > 0 and nb_impayes == 0

        # Impayés par période (pour "point d'eau soldé")
        nb_impayes_passes = sum(
            1 for k, m in mois_data.items()
            if k in mois_passes_set and m['releve_id'] and m['montant'] > 0 and not m['paye']
        )
        nb_impayes_courant = sum(
            1 for k, m in mois_data.items()
            if k in mois_courant_set and m['releve_id'] and m['montant'] > 0 and not m['paye']
        )

        # Ne garder que les points d'eau avec au moins une facture
        if nb_releves > 0 and (not non_pointes_totalement or nb_impayes > 0):
            points_eau_data.append({
                'point_eau': pe,
                'mois': mois_data,
                'nb_releves': nb_releves,
                'nb_payes': nb_payes,
                'nb_impayes': nb_impayes,
                'taux': taux,
                'est_coupe': est_coupe,
                'tout_paye': tout_paye,
                'settled_past': nb_impayes_passes == 0,
                'settled_current': nb_impayes_courant == 0,
            })

            # Mettre à jour les stats globales
            stats_globales['total_factures'] += nb_releves
            stats_globales['factures_payees'] += nb_payes
            stats_globales['factures_impayees'] += nb_impayes
            stats_globales['montant_impaye'] += montant_impaye
            if est_coupe:
                stats_globales['points_eau_coupes'] += 1
            if tout_paye:
                stats_globales['points_eau_tout_paye'] += 1

    # Calculer le taux de paiement global
    if stats_globales['total_factures'] > 0:
        stats_globales['taux_paiement'] = round(
            (stats_globales['factures_payees'] / stats_globales['total_factures']) * 100
        )
    else:
        stats_globales['taux_paiement'] = 0

    # Regrouper par parcelle
    donnees_par_parcelle = defaultdict(list)

    for data in points_eau_data:
        pe = data['point_eau']
        parcelle_key = str(pe.parcelle.id) if pe.parcelle else 'sans_parcelle'
        parcelle_nom = pe.parcelle.reference_parcelle if pe.parcelle else 'Sans parcelle'

        if parcelle_key not in [p['parcelle_id'] for p in donnees_par_parcelle.values() for item in [p]]:
            donnees_par_parcelle[parcelle_key] = {
                'parcelle_id': parcelle_key,
                'parcelle_nom': parcelle_nom,
                'points_eau': []
            }

        donnees_par_parcelle[parcelle_key]['points_eau'].append(data)

    # Trier les points d'eau dans chaque parcelle
    def get_sort_priority(data):
        type_nom = data['point_eau'].type_point_eau.nom_type.upper() if data['point_eau'].type_point_eau else 'ZZZ'
        if 'KIOSQUE' in type_nom:
            type_priority = 0
        elif 'BI' in type_nom or 'BORNE' in type_nom:
            type_priority = 1
        elif 'BP' in type_nom or 'BRANCHEMENT' in type_nom:
            type_priority = 2
        else:
            type_priority = 3

        idxls = data['point_eau'].idxls
        if idxls:
            try:
                idxls_sort = int(idxls)
            except (ValueError, TypeError):
                idxls_sort = 999999 + abs(hash(str(idxls))) % 100000
        else:
            idxls_sort = 999999

        return (type_priority, idxls_sort)

    for parcelle_data in donnees_par_parcelle.values():
        parcelle_data['points_eau'].sort(key=get_sort_priority)

    # Convertir en liste triée par nom de parcelle
    parcelles_organisees = sorted(donnees_par_parcelle.values(), key=lambda x: x['parcelle_nom'])

    # ========== SECTION CALCUL DEPUIS COMPTABILITÉ - Tableau par ouvrage et type ==========
    donnees_par_ouvrage_type = {}
    mois_liste_calc = mois_liste
    points_eau_retenus_ids = {
        str(data['point_eau'].id) for data in points_eau_data
    }

    # Initialiser la structure pour chaque combinaison ouvrage+type depuis les points d'eau filtrés
    for pe in points_eau_qs:
        if str(pe.id) not in points_eau_retenus_ids:
            continue
        if not pe.ouvrage or not pe.type_point_eau:
            continue

        key = (str(pe.ouvrage.id), str(pe.type_point_eau.id))

        if key not in donnees_par_ouvrage_type:
            donnees_par_ouvrage_type[key] = {
                'ouvrage': pe.ouvrage,
                'type_point_eau': pe.type_point_eau,
                'nb_points_eau': 0,
                'points_eau_ids': set(),
                'nb_coupes': 0,
                'mois': {mois: {'total': 0, 'payes': 0, 'impayes': 0} for mois in mois_liste_calc}
            }

        donnees_par_ouvrage_type[key]['points_eau_ids'].add(str(pe.id))

        # Incrémenter le compteur si le point d'eau est coupé
        if pe.is_cut:
            donnees_par_ouvrage_type[key]['nb_coupes'] += 1

    # Remplir les données des relevés
    for releve in releves:
        if not releve.datereleve or not releve.point_eau or not releve.point_eau.ouvrage or not releve.point_eau.type_point_eau:
            continue

        date_obj = releve.datereleve

        # CRITICAL: La facture est pour le mois SUIVANT le relevé
        from dateutil.relativedelta import relativedelta
        date_facture = date_obj + relativedelta(months=1)

        # Filtrer par année (année de la facture)
        if date_facture.year != int(annee_filter):
            continue

        pe = releve.point_eau
        if str(pe.id) not in points_eau_retenus_ids:
            continue
        key = (str(pe.ouvrage.id), str(pe.type_point_eau.id))
        mois = date_facture.month

        if mois not in mois_liste_calc:
            continue

        if key in donnees_par_ouvrage_type:
            donnees_par_ouvrage_type[key]['mois'][mois]['total'] += 1

            # Vérifier si payé (numeroDiameX renseigné)
            est_paye = bool(releve.numeroDiameX and str(releve.numeroDiameX).strip())

            if est_paye:
                donnees_par_ouvrage_type[key]['mois'][mois]['payes'] += 1
            else:
                donnees_par_ouvrage_type[key]['mois'][mois]['impayes'] += 1

    # Calculer le nombre de points d'eau par ligne
    for key, data in donnees_par_ouvrage_type.items():
        data['nb_points_eau'] = len(data['points_eau_ids'])

    # Préparer les données pour le template
    tableau_data = []
    for key, data in donnees_par_ouvrage_type.items():
        # Ne garder que les lignes avec au moins un relevé
        total_releves = sum(m['total'] for m in data['mois'].values())
        if total_releves == 0:
            continue

        # Calculer les stats par ligne
        total_payes = sum(m['payes'] for m in data['mois'].values())
        total_impayes = sum(m['impayes'] for m in data['mois'].values())
        taux = int(round(total_payes / total_releves * 100)) if total_releves > 0 else 0

        # Déterminer le statut global (pour couleur)
        if total_impayes == 0 and total_payes > 0:
            statut_global = 'tout_paye'
        elif total_payes == 0:
            statut_global = 'non_paye'
        else:
            statut_global = 'partiel'

        rp_tot, rp_pay, rp_imp, rp_taux = _split_counts(data['mois'], mois_passes_set)
        rc_tot, rc_pay, rc_imp, rc_taux = _split_counts(data['mois'], mois_courant_set)
        tableau_data.append({
            'ouvrage': data['ouvrage'],
            'type_point_eau': data['type_point_eau'],
            'nb_points_eau': data['nb_points_eau'],
            'nb_coupes': data['nb_coupes'],
            'mois': data['mois'],
            'total_releves': total_releves,
            'total_payes': total_payes,
            'total_impayes': total_impayes,
            'taux': taux,
            'statut_global': statut_global,
            'total_releves_passes': rp_tot, 'total_payes_passes': rp_pay,
            'total_impayes_passes': rp_imp, 'taux_passes': rp_taux,
            'total_releves_courant': rc_tot, 'total_payes_courant': rc_pay,
            'total_impayes_courant': rc_imp, 'taux_courant': rc_taux,
            'settled_past': rp_imp == 0,
            'settled_current': rc_imp == 0,
        })

    # Trier par ouvrage puis par type
    tableau_data.sort(key=lambda x: (x['ouvrage'].nom_ouvrage, x['type_point_eau'].nom_type))

    # Calculer les sous-totaux par ouvrage
    sous_totaux_par_ouvrage = {}
    for data in tableau_data:
        ouvrage_id_str = str(data['ouvrage'].id)

        if ouvrage_id_str not in sous_totaux_par_ouvrage:
            sous_totaux_par_ouvrage[ouvrage_id_str] = {
                'ouvrage': data['ouvrage'],
                'nb_points_eau': 0,
                'mois': {mois: {'total': 0, 'payes': 0, 'impayes': 0} for mois in mois_liste_calc},
                'total_releves': 0,
                'total_payes': 0,
                'total_impayes': 0,
                'taux': 0
            }

        # Accumuler les totaux
        sous_totaux_par_ouvrage[ouvrage_id_str]['nb_points_eau'] += data['nb_points_eau']
        sous_totaux_par_ouvrage[ouvrage_id_str]['total_releves'] += data['total_releves']
        sous_totaux_par_ouvrage[ouvrage_id_str]['total_payes'] += data['total_payes']
        sous_totaux_par_ouvrage[ouvrage_id_str]['total_impayes'] += data['total_impayes']

        # Accumuler par mois
        for mois in mois_liste_calc:
            sous_totaux_par_ouvrage[ouvrage_id_str]['mois'][mois]['total'] += data['mois'][mois]['total']
            sous_totaux_par_ouvrage[ouvrage_id_str]['mois'][mois]['payes'] += data['mois'][mois]['payes']
            sous_totaux_par_ouvrage[ouvrage_id_str]['mois'][mois]['impayes'] += data['mois'][mois]['impayes']

    # Calculer les taux pour chaque sous-total (+ dédoublement passés / en cours)
    for ouvrage_id_str, st in sous_totaux_par_ouvrage.items():
        if st['total_releves'] > 0:
            st['taux'] = int(round(st['total_payes'] / st['total_releves'] * 100))
        sp_tot, sp_pay, sp_imp, sp_taux = _split_counts(st['mois'], mois_passes_set)
        sc_tot, sc_pay, sc_imp, sc_taux = _split_counts(st['mois'], mois_courant_set)
        st.update({
            'total_releves_passes': sp_tot, 'total_payes_passes': sp_pay,
            'total_impayes_passes': sp_imp, 'taux_passes': sp_taux,
            'total_releves_courant': sc_tot, 'total_payes_courant': sc_pay,
            'total_impayes_courant': sc_imp, 'taux_courant': sc_taux,
        })

    # --- Blocs KPI + colonnes mensuelles (harmonisation avec les autres pages) ---
    facture_counts_par_mois = {mois: {'total': 0, 'payes': 0, 'impayes': 0} for mois in mois_liste}
    for row in tableau_data:
        for mois in mois_liste:
            cell = row['mois'][mois]
            facture_counts_par_mois[mois]['total'] += cell['total']
            facture_counts_par_mois[mois]['payes'] += cell['payes']
            facture_counts_par_mois[mois]['impayes'] += cell['impayes']

    _ouvrages_scope_ids = set(points_eau_qs.values_list('ouvrage_id', flat=True).distinct())
    recouvrement_par_ouvrage_mois = build_recouvrement_par_ouvrage_mois(
        list(releves), _ouvrages_scope_ids, annee_int, periodes_coupure, None,
    )
    score_totals_by_point = build_score_totals_from_releves(
        list(releves), annee_int, periodes_coupure, _today_mg,
    )
    # Coupés depuis moins d'un an (règle partagée : abandonnés et sans date à part)
    from apps.billing.points_eau_statut import q_coupe
    points_eau_coupes_count = points_eau_qs.filter(q_coupe()).count()
    kpis = build_volume_kpis(
        recouvrement_par_ouvrage_mois=recouvrement_par_ouvrage_mois,
        facture_counts_par_mois=facture_counts_par_mois,
        score_totals_by_point=score_totals_by_point,
        points_eau_coupes_count=points_eau_coupes_count,
        annee_int=annee_int,
        today=_today_mg,
    )

    mois_colonnes_visibles = []
    for _m in mois_liste:
        # Mois soldé = aucune ligne n'a d'impayé ce mois-là (mois vide inclus) :
        # le rapport imprimé montre tous les mois de la période, les toggles font
        # le focus sur ceux qui restent à traiter.
        _settled = all(r['mois'][_m]['impayes'] == 0 for r in tableau_data)
        mois_colonnes_visibles.append({
            'number': _m, 'label': tous_mois_noms[_m - 1],
            'is_current': _m == mois_en_cours_num,
            'settled': _settled,
        })

    # Ajouter un indicateur de changement d'ouvrage et les sous-totaux
    ouvrage_precedent = None
    for i, data in enumerate(tableau_data):
        ouvrage_id_str = str(data['ouvrage'].id)
        data['nouveau_groupe_ouvrage'] = (ouvrage_precedent is None or ouvrage_id_str != ouvrage_precedent)

        # Ajouter le sous-total pour cet ouvrage
        if data['nouveau_groupe_ouvrage']:
            data['sous_total_ouvrage'] = sous_totaux_par_ouvrage[ouvrage_id_str]

        ouvrage_precedent = ouvrage_id_str
    # ========== FIN SECTION CALCUL DEPUIS COMPTABILITÉ ==========

    # Récupérer les noms pour l'affichage
    communes_noms = []
    if communes_param:
        communes_ids = communes_param.split(',')
        communes_obj = Commune.objects.filter(id__in=communes_ids).values_list('nom_commune', flat=True)
        communes_noms = list(communes_obj)
    elif commune_id and commune_id != 'all':
        try:
            communes_noms = [Commune.objects.get(id=commune_id).nom_commune]
        except Commune.DoesNotExist:
            pass

    commune_nom = ', '.join(communes_noms) if communes_noms else ''

    ouvrage_nom = ''
    if ouvrage_id and ouvrage_id != 'all':
        try:
            ouvrage_nom = Ouvrage.objects.get(id=ouvrage_id).nom_ouvrage
        except Ouvrage.DoesNotExist:
            pass

    context = {
        'parcelles_organisees': parcelles_organisees,
        'mois_liste': mois_liste,
        'annee': annee_filter,
        'commune_nom': commune_nom,
        'ouvrage_nom': ouvrage_nom,
        'stats': stats_globales,
        'total_points_eau': len(points_eau_data),
        'date_impression': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'periode_libelle': periode_libelle,
        'non_pointes_totalement': non_pointes_totalement,
        # Variables pour le tableau "Calcul depuis Comptabilité"
        'tableau_data': tableau_data,
        'sous_totaux_par_ouvrage': sous_totaux_par_ouvrage,
        'mois_noms': mois_noms,
        # Harmonisation avec les autres pages volumétriques
        'kpis': kpis,
        'mois_colonnes_visibles': mois_colonnes_visibles,
        'mois_en_cours_num': mois_en_cours_num,
    }

    return render(request, 'core/impression_gestion_volumetrique.html', context)
