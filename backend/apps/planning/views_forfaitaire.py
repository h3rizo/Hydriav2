from django.shortcuts import render
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.paginator import Paginator
from datetime import datetime, timedelta, date
from decimal import Decimal
from apps.billing.models import PointEau, PaiementForfaitaire, CoupureEau, ModaliteGestion
from apps.geography.models import Commune, District, Region
from apps.organization.models import Ouvrage
from apps.organization.scoping import get_user_organisation
from apps.accounting.dashboard_employee_filter import (
    build_employee_geo_filter_options,
    calculate_water_point_score,
    get_water_point_score_gap_ids,
    is_closed_payment_month,
    resolve_dashboard_employee_filter,
    resolve_score_scope,
)
import pytz

def gestion_forfaitaire(request):
    """Page de gestion des paiements forfaitaires

    Utilise uniquement PaiementForfaitaire et CoupureEau (pas de dépendance à PlanningDetail)
    """

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    annee_int = int(annee_filter) if annee_filter else annee_courante

    region_id = request.GET.get('region', '')
    district_id = request.GET.get('district', '')
    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    employe_id = request.GET.get('employe', '')
    point_eau_id = request.GET.get('point_eau', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    type_evenement_filter = request.GET.get('type_evenement', '')  # 'paiement', 'coupure', 'remise'
    statut_filter = request.GET.get('statut', '')  # 'paye', 'non_paye'
    quantite_filter = request.GET.get('quantite', '')
    score_ecart_filter = str(request.GET.get('score_ecart', '') or '').strip().lower()
    show_only_score_gap = score_ecart_filter in {'1', 'true', 'on', 'yes'}

    # CRITICAL: Récupérer les ouvrages avec modalité forfaitaire ou mixte uniquement
    ouvrages_forfaitaires_ids = set(ModaliteGestion.objects.filter(
        date_fin__isnull=True,  # Modalité active
        modalitepaiement__in=['forfaitaire', 'mixte']
    ).values_list('ouvrage_id', flat=True).distinct())
    ouvrages_filter_scope = set(ouvrages_forfaitaires_ids)
    employes_responsables, ouvrages_forfaitaires_ids = resolve_dashboard_employee_filter(
        ouvrages_forfaitaires_ids,
        employe_id,
    )
    if employe_id and not any(
        str(option.get('id', '')) == str(employe_id)
        for option in employes_responsables
    ):
        employe_id = ''

    # Récupérer les paiements forfaitaires
    paiements_qs = PaiementForfaitaire.objects.filter(
        point_eau__ouvrage_id__in=ouvrages_forfaitaires_ids
    ).select_related(
        'point_eau',
        'point_eau__type_point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune'
    )

    # Récupérer les coupures
    coupures_qs = CoupureEau.objects.filter(
        point_eau__ouvrage_id__in=ouvrages_forfaitaires_ids
    ).select_related(
        'point_eau',
        'point_eau__type_point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune'
    )

    # Appliquer les filtres géographiques
    if region_id:
        paiements_qs = paiements_qs.filter(point_eau__parcelle__village__fokontany__commune__district__region_id=region_id)
        coupures_qs = coupures_qs.filter(point_eau__parcelle__village__fokontany__commune__district__region_id=region_id)
    if district_id:
        paiements_qs = paiements_qs.filter(point_eau__parcelle__village__fokontany__commune__district_id=district_id)
        coupures_qs = coupures_qs.filter(point_eau__parcelle__village__fokontany__commune__district_id=district_id)
    if commune_id:
        paiements_qs = paiements_qs.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
        coupures_qs = coupures_qs.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
    if ouvrage_id:
        paiements_qs = paiements_qs.filter(point_eau__ouvrage_id=ouvrage_id)
        coupures_qs = coupures_qs.filter(point_eau__ouvrage_id=ouvrage_id)
    if point_eau_id:
        paiements_qs = paiements_qs.filter(point_eau_id=point_eau_id)
        coupures_qs = coupures_qs.filter(point_eau_id=point_eau_id)

    # Filtres par date
    if date_debut:
        paiements_qs = paiements_qs.filter(date_facture__gte=date_debut)
        coupures_qs = coupures_qs.filter(date_evenement__gte=date_debut)
    if date_fin:
        paiements_qs = paiements_qs.filter(date_facture__lte=date_fin)
        coupures_qs = coupures_qs.filter(date_evenement__lte=date_fin)

    # Filtre par statut de paiement
    if statut_filter == 'paye':
        paiements_qs = paiements_qs.filter(paye=True)
    elif statut_filter == 'non_paye':
        paiements_qs = paiements_qs.filter(paye=False)

    # Filtre par quantité
    if quantite_filter:
        try:
            quantite_value = int(quantite_filter)
            paiements_qs = paiements_qs.filter(quantite=quantite_value)
        except (ValueError, TypeError):
            pass

    # Le tableau ne montre que l'annee selectionnee. Appliquer ce filtre en
    # base evite de charger puis rejeter tout l'historique en Python.
    paiements_qs = paiements_qs.filter(date_facture__year=annee_int)
    coupures_qs = coupures_qs.filter(date_evenement__year=annee_int)

    # Filtre par type d'événement
    if type_evenement_filter:
        if type_evenement_filter == 'coupure':
            coupures_qs = coupures_qs.filter(type_evenement='coupure')
        elif type_evenement_filter == 'remise':
            coupures_qs = coupures_qs.filter(type_evenement='remise')

    # Listes pour les dropdowns
    regions, districts, communes, ouvrages = build_employee_geo_filter_options(
        ouvrages_filter_scope,
        employes_responsables,
    )

    employee_ids_by_ouvrage = {}
    for option in employes_responsables:
        for option_ouvrage_id in option.get('ouvrage_ids', []):
            employee_ids_by_ouvrage.setdefault(str(option_ouvrage_id), []).append(str(option['id']))

    points_eau_list = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=ouvrages_filter_scope
    ).select_related(
        'type_point_eau', 'ouvrage',
        'parcelle__village__fokontany__commune__district__region',
    ).only(
        'id', 'code_point_eau', 'nomabonne', 'idxls', 'ouvrage_id',
        'type_point_eau_id', 'parcelle_id',
        'ouvrage__id', 'ouvrage__nom_ouvrage',
        'type_point_eau__id', 'type_point_eau__nom_type',
        'parcelle__id', 'parcelle__village_id',
        'parcelle__village__id', 'parcelle__village__fokontany_id',
        'parcelle__village__fokontany__id',
        'parcelle__village__fokontany__commune_id',
        'parcelle__village__fokontany__commune__id',
        'parcelle__village__fokontany__commune__district_id',
        'parcelle__village__fokontany__commune__district__id',
        'parcelle__village__fokontany__commune__district__region_id',
        'parcelle__village__fokontany__commune__district__region__id',
    )

    points_eau_formatted = []
    for pe in points_eau_list:
        pe.ouvrage_id_str = str(pe.ouvrage.id) if pe.ouvrage else ''
        commune = pe.parcelle.village.fokontany.commune if pe.parcelle_id else None
        pe.filter_commune_id = str(commune.id) if commune else ''
        pe.filter_district_id = str(commune.district_id) if commune else ''
        pe.filter_region_id = str(commune.district.region_id) if commune else ''
        pe.filter_employe_ids = ','.join(employee_ids_by_ouvrage.get(str(pe.ouvrage_id), []))
        pe.display_name = pe.code_point_eau or pe.nomabonne or pe.idxls or f'Point eau {pe.id}'
        points_eau_formatted.append(pe)

    # --- LOGIQUE YTD (Date Limite) ---
    today = datetime.now().date()
    debut_annee = datetime(annee_int, 1, 1).date()
    fin_annee = datetime(annee_int, 12, 31).date()
    
    if annee_int < today.year:
        limit_date = fin_annee
    else:
        limit_date = min(today, fin_annee)

    if limit_date < debut_annee:
        limit_date = debut_annee

    # --- HELPER FINANCIER ---
    def calculate_details_financiers(pe, annee, limit_date):
        tarif = Decimal(str(pe.tarifforfaitaire)) if pe.tarifforfaitaire else Decimal('0.00')
        if tarif == 0:
            return Decimal('0.00'), Decimal('0.00'), Decimal('0.00')

        debut_annee_calc = datetime(annee, 1, 1).date()
        
        if limit_date < debut_annee_calc:
            nb_mois_ecoules = 0
        else:
            delta_jours = (limit_date - debut_annee_calc).days + 1
            nb_mois_ecoules = int(round(delta_jours / 30.4))
            
        montant_brut = (tarif / 3) * nb_mois_ecoules

        point_events = coupures_by_point.get(pe.id, [])
        evenements_avant_annee = [evt for evt in point_events if evt.date_evenement < debut_annee_calc]
        or_debut = evenements_avant_annee[-1] if evenements_avant_annee else None
        est_coupe = (or_debut and or_debut.type_evenement == 'coupure')
        date_debut_coupure = debut_annee_calc if est_coupe else None

        evenements = [
            evt for evt in point_events
            if evt.date_evenement.year == annee and evt.date_evenement <= limit_date
        ]
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

    def get_paiement_date(paiement):
        if hasattr(paiement, 'planning') and paiement.planning and hasattr(paiement.planning, 'date') and paiement.planning.date:
            date_val = paiement.planning.date
        else:
            date_val = paiement.date_facture
            
        if not date_val: return None
        if isinstance(date_val, (datetime, date)):
            if isinstance(date_val, datetime) and date_val.tzinfo:
                return date_val.astimezone(tz_madagascar).date()
            if isinstance(date_val, datetime):
                return date_val.date()
            return date_val
        return date_val

    # --- CALCUL STATS GLOBALES (Indépendant de la pagination/liste d'évènements filtrée par type) ---
    points_eau_stats_qs = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=ouvrages_forfaitaires_ids
    ).only('id', 'tarifforfaitaire', 'ouvrage_id')
    if commune_id:
        points_eau_stats_qs = points_eau_stats_qs.filter(parcelle__village__fokontany__commune_id=commune_id)
    if ouvrage_id:
        points_eau_stats_qs = points_eau_stats_qs.filter(ouvrage_id=ouvrage_id)
    if point_eau_id:
        points_eau_stats_qs = points_eau_stats_qs.filter(id=point_eau_id)

    points_eau_stats = list(points_eau_stats_qs)
    point_stats_ids = [pe.id for pe in points_eau_stats]

    coupures_by_point = {point_id: [] for point_id in point_stats_ids}
    for evt in CoupureEau.objects.filter(point_eau_id__in=point_stats_ids).only(
        'id', 'point_eau_id', 'date_evenement', 'type_evenement'
    ).order_by('point_eau_id', 'date_evenement', 'created_at'):
        coupures_by_point.setdefault(evt.point_eau_id, []).append(evt)

    paiements_by_point = {point_id: [] for point_id in point_stats_ids}
    paiements_stats_qs = PaiementForfaitaire.objects.filter(
        point_eau_id__in=point_stats_ids
    ).filter(
        Q(date_facture__year=annee_int) | Q(planning__date__date__year=annee_int)
    ).select_related('planning').only(
        'id', 'point_eau_id', 'planning_id', 'date_facture', 'montant',
        'numeroDiameX', 'baseDiameX', 'planning__date'
    )
    for paiement in paiements_stats_qs:
        paiements_by_point.setdefault(paiement.point_eau_id, []).append(paiement)

    score_reference_month = timezone.localdate().replace(day=1)
    score_totals_by_point = {}
    for point_id, paiements_point in paiements_by_point.items():
        for paiement in paiements_point:
            paiement_date = paiement.date_facture
            if not paiement_date or not is_closed_payment_month(paiement_date, score_reference_month):
                continue
            if date_debut and paiement_date < datetime.strptime(date_debut, '%Y-%m-%d').date():
                continue
            if date_fin and paiement_date > datetime.strptime(date_fin, '%Y-%m-%d').date():
                continue
            montant = Decimal(str(paiement.montant or 0))
            totals = score_totals_by_point.setdefault(
                str(point_id),
                {'expected': Decimal('0'), 'paid': Decimal('0')},
            )
            totals['expected'] += montant
            if paiement.est_paye:
                totals['paid'] += montant

    employee_points_score = calculate_water_point_score(
        score_totals_by_point.keys(),
        score_totals_by_point,
    )
    score_gap_point_ids = get_water_point_score_gap_ids(
        score_totals_by_point.keys(),
        score_totals_by_point,
    )
    organisation_user = get_user_organisation(request.user)
    employee_points_score.update({
        'visible': True,
        **resolve_score_scope(
            employee_options=employes_responsables,
            employee_id=employe_id,
            ouvrage_id=ouvrage_id,
            commune_id=commune_id,
            default_organisation_name=getattr(organisation_user, 'nom_organisation', '') or '',
        ),
    })

    montant_prevu_total = Decimal('0.00')
    decote_totale_globale = Decimal('0.00')
    montant_planifie_total = Decimal('0.00')
    montant_paye_total = Decimal('0.00')
    nb_ouvrages_stats = len({pe.ouvrage_id for pe in points_eau_stats})

    for pe in points_eau_stats:
        m_brut, decote_pe, m_net = calculate_details_financiers(pe, annee_int, limit_date)
        montant_prevu_total += m_net
        decote_totale_globale += decote_pe
        
        for p in paiements_by_point.get(pe.id, []):
            d_loc = get_paiement_date(p)
            if d_loc and d_loc.year == annee_int and d_loc <= limit_date:
                if p.montant:
                    montant_planifie_total += p.montant
                    if p.numeroDiameX:
                        montant_paye_total += p.montant

    events_list = []

    # Ajouter les paiements
    for paiement in paiements_qs:
        event_date = paiement.date_facture
        if event_date.year != annee_int:
            continue

        events_list.append({
            'id': str(paiement.id),
            'type': 'paiement',
            'type_label': 'Paiement forfaitaire',
            'date': event_date,
            'point_eau': paiement.point_eau,
            'quantite': paiement.quantite,
            'montant': paiement.montant,
            'paye': paiement.paye,
            'numeroDiameX': paiement.numeroDiameX or '',
            'prix_unitaire': paiement.prix_unitaire,
        })

    # Ajouter les coupures/remises
    for coupure in coupures_qs:
        event_date = coupure.date_evenement
        if event_date.year != annee_int:
            continue

        events_list.append({
            'id': str(coupure.id),
            'type': coupure.type_evenement,
            'type_label': 'Coupure d\'eau' if coupure.type_evenement == 'coupure' else 'Remise en eau',
            'date': event_date,
            'point_eau': coupure.point_eau,
            'quantite': None,
            'montant': None,
            'paye': None,
            'numeroDiameX': '',
            'raison': coupure.raison,
            'notes': coupure.notes,
        })

    # Trier par date (du plus récent au plus ancien)
    if show_only_score_gap:
        events_list = [
            event for event in events_list
            if str(event['point_eau'].id) in score_gap_point_ids
        ]

    events_list.sort(key=lambda x: x['date'], reverse=True)

    # Calculer les statistiques pour l'affichage (K Ar)
    montant_prevu_k = montant_prevu_total / Decimal('1000')
    montant_planifie_k = montant_planifie_total / Decimal('1000')
    montant_paye_k = montant_paye_total / Decimal('1000')
    decote_totale_k = decote_totale_globale / Decimal('1000')
    
    taux_recouvrement = int((montant_paye_total / montant_prevu_total * 100) if montant_prevu_total > 0 else 0)
    
    # Garder les comptes d'évènements pour le contexte
    nb_paiements = sum(1 for e in events_list if e['type'] == 'paiement')
    nb_paiements_payes = sum(1 for e in events_list if e['type'] == 'paiement' and e['paye'])
    nb_coupures = sum(1 for e in events_list if e['type'] == 'coupure')
    nb_remises = sum(1 for e in events_list if e['type'] == 'remise')

    # Pagination
    paginator = Paginator(events_list, 50)  # 50 événements par page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'annee_filter': annee_filter,
        'region_filter': region_id,
        'district_filter': district_id,
        'commune_filter': commune_id,
        'ouvrage_filter': ouvrage_id,
        'employe_filter': employe_id,
        'point_eau_filter': point_eau_id,
        'type_evenement_filter': type_evenement_filter,
        'statut_filter': statut_filter,
        'quantite_filter': quantite_filter,
        'date_debut': date_debut,
        'date_fin': date_fin,

        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'employes_responsables': employes_responsables,
        'employee_points_score': employee_points_score,
        'show_only_score_gap': show_only_score_gap,
        'points_eau': points_eau_formatted,

        'events': page_obj.object_list,
        'page_obj': page_obj,
        'total_events': len(events_list),

        'nb_ouvrages': nb_ouvrages_stats,
        'nb_paiements': nb_paiements,
        'nb_paiements_payes': nb_paiements_payes,
        'nb_coupures': nb_coupures,
        'nb_remises': nb_remises,
        'montant_prevu_k': montant_prevu_k,
        'montant_prevu': montant_prevu_total,
        'montant_planifie_k': montant_planifie_k,
        'montant_planifie': montant_planifie_total,
        'montant_paye_k': montant_paye_k,
        'montant_paye': montant_paye_total,
        'decote_totale_k': decote_totale_k,
        'decote_totale': decote_totale_globale,
        'taux_recouvrement': taux_recouvrement,
    }

    return render(request, 'planning/gestion_forfaitaire.html', context)


def detail_forfaitaire_modal(request):
    """API pour récupérer les détails des paiements forfaitaires"""
    type_detail = request.GET.get('type')  # prevu, planifie, paye, coupes
    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les ouvrages avec modalité forfaitaire ou mixte
    ouvrages_forfaitaires_ids = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['forfaitaire', 'mixte']
    ).values_list('ouvrage_id', flat=True).distinct()

    if type_detail == 'prevu':
        # Détail par point d'eau avec tarif prévu
        points_eau = PointEau.objects.filter(
            tarifforfaitaire__isnull=False,
            ouvrage_id__in=ouvrages_forfaitaires_ids
        ).select_related(
            'ouvrage',
            'parcelle__village__fokontany__commune'
        )
        if commune_id:
            points_eau = points_eau.filter(parcelle__village__fokontany__commune_id=commune_id)
        if ouvrage_id:
            points_eau = points_eau.filter(ouvrage_id=ouvrage_id)

        data = []
        for pe in points_eau:
            # Calculer planifié et payé depuis PaiementForfaitaire
            paiements_pe = PaiementForfaitaire.objects.filter(point_eau=pe)

            # Appliquer les filtres de date
            if date_debut:
                paiements_pe = paiements_pe.filter(date_facture__gte=date_debut)
            if date_fin:
                paiements_pe = paiements_pe.filter(date_facture__lte=date_fin)

            montant_planifie = paiements_pe.aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
            montant_paye = paiements_pe.filter(numeroDiameX__isnull=False).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')

            data.append({
                'point_eau': pe.nomabonne,
                'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
                'commune': pe.parcelle.village.fokontany.commune.nom_commune if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany and pe.parcelle.village.fokontany.commune else 'N/A',
                'prevu': float(pe.tarifforfaitaire * 4 if pe.tarifforfaitaire else 0),
                'planifie': float(montant_planifie),
                'paye': float(montant_paye),
            })

        return JsonResponse({'success': True, 'data': data})

    elif type_detail == 'planifie':
        # Détail des paiements planifiés
        paiements = PaiementForfaitaire.objects.filter(
            point_eau__ouvrage_id__in=ouvrages_forfaitaires_ids
        ).select_related(
            'point_eau',
            'point_eau__ouvrage',
            'point_eau__parcelle__village__fokontany__commune'
        )
        if commune_id:
            paiements = paiements.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
        if ouvrage_id:
            paiements = paiements.filter(point_eau__ouvrage_id=ouvrage_id)
        if date_debut:
            paiements = paiements.filter(date_facture__gte=date_debut)
        if date_fin:
            paiements = paiements.filter(date_facture__lte=date_fin)

        data = []
        for paiement in paiements:
            # Convertir la date
            date_str = 'N/A'
            if paiement.date_facture:
                date_aware = paiement.date_facture if paiement.date_facture.tzinfo else timezone.make_aware(paiement.date_facture)
                date_madagascar = date_aware.astimezone(tz_madagascar)
                date_str = date_madagascar.strftime('%d/%m/%Y')

            data.append({
                'date': date_str,
                'point_eau': paiement.point_eau.nomabonne if paiement.point_eau else 'N/A',
                'ouvrage': paiement.point_eau.ouvrage.nom_ouvrage if paiement.point_eau and paiement.point_eau.ouvrage else 'N/A',
                'montant': float(paiement.montant),
                'paye': paiement.numeroDiameX is not None,
            })

        return JsonResponse({'success': True, 'data': data})

    elif type_detail == 'paye':
        # Détail des paiements payés
        paiements = PaiementForfaitaire.objects.filter(
            numeroDiameX__isnull=False,
            point_eau__ouvrage_id__in=ouvrages_forfaitaires_ids
        ).select_related(
            'point_eau',
            'point_eau__ouvrage',
            'point_eau__parcelle__village__fokontany__commune'
        )
        if commune_id:
            paiements = paiements.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
        if ouvrage_id:
            paiements = paiements.filter(point_eau__ouvrage_id=ouvrage_id)
        if date_debut:
            paiements = paiements.filter(date_facture__gte=date_debut)
        if date_fin:
            paiements = paiements.filter(date_facture__lte=date_fin)

        data = []
        for paiement in paiements:
            # Convertir la date
            date_str = 'N/A'
            if paiement.date_facture:
                date_aware = paiement.date_facture if paiement.date_facture.tzinfo else timezone.make_aware(paiement.date_facture)
                date_madagascar = date_aware.astimezone(tz_madagascar)
                date_str = date_madagascar.strftime('%d/%m/%Y')

            data.append({
                'date': date_str,
                'point_eau': paiement.point_eau.nomabonne if paiement.point_eau else 'N/A',
                'ouvrage': paiement.point_eau.ouvrage.nom_ouvrage if paiement.point_eau and paiement.point_eau.ouvrage else 'N/A',
                'montant': float(paiement.montant),
                'numero_diamex': paiement.numeroDiameX,
            })

        return JsonResponse({'success': True, 'data': data})

    elif type_detail == 'coupes':
        # Détail des coupures d'eau
        coupures = CoupureEau.objects.filter(
            type_evenement='coupure',
            point_eau__ouvrage_id__in=ouvrages_forfaitaires_ids
        ).select_related(
            'point_eau',
            'point_eau__ouvrage',
            'point_eau__parcelle__village__fokontany__commune'
        )
        if commune_id:
            coupures = coupures.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
        if ouvrage_id:
            coupures = coupures.filter(point_eau__ouvrage_id=ouvrage_id)
        if date_debut:
            coupures = coupures.filter(date_evenement__gte=date_debut)
        if date_fin:
            coupures = coupures.filter(date_evenement__lte=date_fin)

        data = []
        for coupure in coupures:
            date_str = 'N/A'
            if coupure.date_evenement:
                date_aware = coupure.date_evenement if coupure.date_evenement.tzinfo else timezone.make_aware(coupure.date_evenement)
                date_madagascar = date_aware.astimezone(tz_madagascar)
                date_str = date_madagascar.strftime('%d/%m/%Y')

            data.append({
                'point_eau': coupure.point_eau.nomabonne if coupure.point_eau else 'N/A',
                'ouvrage': coupure.point_eau.ouvrage.nom_ouvrage if coupure.point_eau and coupure.point_eau.ouvrage else 'N/A',
                'commune': coupure.point_eau.parcelle.village.fokontany.commune.nom_commune if coupure.point_eau.parcelle and coupure.point_eau.parcelle.village and coupure.point_eau.parcelle.village.fokontany and coupure.point_eau.parcelle.village.fokontany.commune else 'N/A',
                'date_arret': date_str,
                'raison': coupure.raison or 'N/A',
            })

        return JsonResponse({'success': True, 'data': data})

    return JsonResponse({'error': 'Type de détail invalide'}, status=400)


@csrf_exempt
def update_detail_point_eau(request):
    """API pour mettre à jour le point d'eau d'un paiement forfaitaire"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            paiement_id = data.get('paiement_id')
            point_eau_id = data.get('point_eau_id')

            paiement = PaiementForfaitaire.objects.get(id=paiement_id)
            paiement.point_eau_id = point_eau_id
            paiement.save()

            return JsonResponse({'success': True})
        except PaiementForfaitaire.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Paiement non trouvé'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)


@csrf_exempt
def delete_detail_forfaitaire(request):
    """API pour supprimer un paiement forfaitaire"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            paiement_id = data.get('paiement_id')

            paiement = PaiementForfaitaire.objects.get(id=paiement_id)
            paiement.delete()

            return JsonResponse({'success': True})
        except PaiementForfaitaire.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Paiement non trouvé'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)


@csrf_exempt
def update_point_eau_tarif(request):
    """API pour mettre à jour le tarif forfaitaire d'un point d'eau"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            point_eau_id = data.get('point_eau_id')
            tarif = data.get('tarif')

            # Valider le tarif
            if tarif is not None and tarif != '':
                try:
                    tarif = float(tarif)
                    if tarif < 0:
                        return JsonResponse({'success': False, 'error': 'Le tarif ne peut pas être négatif'}, status=400)
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Tarif invalide'}, status=400)
            else:
                tarif = None

            point_eau = PointEau.objects.get(id=point_eau_id)
            point_eau.tarifforfaitaire = tarif
            point_eau.save()

            return JsonResponse({
                'success': True,
                'tarif': tarif,
                'message': f'Tarif mis à jour: {tarif if tarif else "Aucun"} Ar'
            })
        except PointEau.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Point d\'eau non trouvé'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)


def api_points_eau_forfaitaire(request):
    """API pour récupérer tous les points d'eau avec modalité forfaitaire ou mixte"""
    # Récupérer les ouvrages avec modalité forfaitaire ou mixte
    ouvrages_forfaitaires_ids = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['forfaitaire', 'mixte']
    ).values_list('ouvrage_id', flat=True).distinct()

    points_eau = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_forfaitaires_ids
    ).select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune'
    ).order_by('nomabonne')

    data = [{
        'id': str(pe.id),
        'nomabonne': pe.nomabonne,
        'code': pe.code_point_eau or '',
        'idxls': pe.idxls or '',
        'type': pe.type_point_eau.nom_type if pe.type_point_eau else 'N/A',
        'ouvrage_id': str(pe.ouvrage.id) if pe.ouvrage else None,
        'ouvrage_nom': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
        'village': pe.parcelle.village.nom_village if pe.parcelle and pe.parcelle.village else 'N/A',
        'commune': pe.parcelle.village.fokontany.commune.nom_commune if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany and pe.parcelle.village.fokontany.commune else 'N/A',
        'tarif': float(pe.tarifforfaitaire) if pe.tarifforfaitaire else 0
    } for pe in points_eau]

    return JsonResponse(data, safe=False)


def get_detail_forfaitaire(request, detail_id):
    """API pour récupérer les données d'un PaiementForfaitaire"""
    try:
        paiement = PaiementForfaitaire.objects.get(id=detail_id)

        data = {
            'quantite': float(paiement.quantite) if paiement.quantite else 0,
            'prix_unitaire': float(paiement.prix_unitaire) if paiement.prix_unitaire else 0,
            'montant': float(paiement.montant) if paiement.montant else 0,
        }

        return JsonResponse({'success': True, 'data': data})
    except PaiementForfaitaire.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Paiement non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
def update_quantity_prix(request):
    """API pour mettre à jour la quantité et le prix unitaire d'un PaiementForfaitaire"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            paiement_id = data.get('paiement_id')
            quantite = data.get('quantite')
            prix = data.get('prix')

            if not paiement_id or quantite is None or prix is None:
                return JsonResponse({'success': False, 'error': 'Paramètres manquants'}, status=400)

            # Valider les valeurs
            try:
                quantite = float(quantite)
                prix = float(prix)
                if quantite < 0 or prix < 0:
                    return JsonResponse({'success': False, 'error': 'Les valeurs ne peuvent pas être négatives'}, status=400)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Valeurs invalides'}, status=400)

            # Mettre à jour le PaiementForfaitaire
            paiement = PaiementForfaitaire.objects.get(id=paiement_id)
            paiement.quantite = quantite
            paiement.prix_unitaire = Decimal(str(prix))
            # Recalculer le montant (quantite * prix_unitaire)
            paiement.montant = Decimal(str(quantite)) * Decimal(str(prix))
            paiement.save()

            return JsonResponse({
                'success': True,
                'message': 'Quantité et prix mis à jour avec succès',
                'quantite': quantite,
                'prix_unitaire': prix,
                'montant': float(paiement.montant)
            })
        except PaiementForfaitaire.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Paiement non trouvé'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
