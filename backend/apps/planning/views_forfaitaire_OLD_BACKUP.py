from django.shortcuts import render
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
from apps.billing.models import PointEau, PaiementForfaitaire, CoupureEau, ModaliteGestion
from apps.geography.models import Commune
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

    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    point_eau_id = request.GET.get('point_eau', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    type_evenement_filter = request.GET.get('type_evenement', '')  # 'paiement', 'coupure', 'remise'
    statut_filter = request.GET.get('statut', '')  # 'paye', 'non_paye'
    quantite_filter = request.GET.get('quantite', '')

    # CRITICAL: Récupérer les ouvrages avec modalité forfaitaire ou mixte uniquement
    ouvrages_forfaitaires_ids = ModaliteGestion.objects.filter(
        date_fin__isnull=True,  # Modalité active
        modalitepaiement__in=['forfaitaire', 'mixte']
    ).values_list('ouvrage_id', flat=True).distinct()

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

    # Appliquer les filtres géographiques sur paiements
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

    # Filtre par type d'événement
    if type_evenement_filter:
        if type_evenement_filter == 'coupure':
            coupures_qs = coupures_qs.filter(type_evenement='coupure')
        elif type_evenement_filter == 'remise':
            coupures_qs = coupures_qs.filter(type_evenement='remise')

    # Filtrer les points d'eau avec tarif forfaitaire non null
    # ET ouvrage avec modalité forfaitaire/mixte
    points_eau = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=ouvrages_forfaitaires_ids  # FILTRE MODALITÉ
    )
    if commune_id:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune_id=commune_id)
    if ouvrage_id:
        points_eau = points_eau.filter(ouvrage_id=ouvrage_id)

    # Listes pour les dropdowns
    communes = Commune.objects.filter(
        id__in=PointEau.objects.filter(
            tarifforfaitaire__isnull=False,
            ouvrage_id__in=ouvrages_forfaitaires_ids
        ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()
    ).order_by('nom_commune')

    from apps.organization.models import Ouvrage
    ouvrages = Ouvrage.objects.filter(
        id__in=ouvrages_forfaitaires_ids
    ).order_by('nom_ouvrage')

    ouvrages_list = []
    for ouvrage in ouvrages:
        communes_ids = PointEau.objects.filter(
            ouvrage=ouvrage,
            tarifforfaitaire__isnull=False,
            parcelle__village__fokontany__commune__isnull=False
        ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()
        ouvrage.communes_ids = ','.join([str(c_id) for c_id in communes_ids])
        ouvrages_list.append(ouvrage)

    points_eau_list = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=ouvrages_forfaitaires_ids
    ).select_related('type_point_eau', 'ouvrage')
    if ouvrage_id:
        points_eau_list = points_eau_list.filter(ouvrage_id=ouvrage_id)

    points_eau_formatted = []
    for pe in points_eau_list:
        pe.ouvrage_id_str = str(pe.ouvrage.id) if pe.ouvrage else ''
        pe.display_name = pe.code_point_eau or pe.nomabonne or pe.idxls or f'Point eau {pe.id}'
        points_eau_formatted.append(pe)

    # Créer une liste unifiée d'événements (paiements + coupures/remises)
    today = timezone.now().date()
    events_list = []

    # Ajouter les paiements
    for paiement in paiements_qs:
        event_date = paiement.date_facture
        if event_date.year != annee_int:
            continue

        date_diff = (event_date - today).days

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
            'date_diff': date_diff,
            'prix_unitaire': paiement.prix_unitaire,
        })

    # Ajouter les coupures/remises
    for coupure in coupures_qs:
        event_date = coupure.date_evenement
        if event_date.year != annee_int:
            continue

        date_diff = (event_date - today).days

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
            'date_diff': date_diff,
            'raison': coupure.raison,
            'remarque': coupure.remarque,
        })

    # Trier par date (du plus récent au plus ancien)
    events_list.sort(key=lambda x: x['date'], reverse=True)

    # Ajouter les indicateurs de date à chaque événement
    for event in events_list:
        date_diff = event['date_diff']

        if date_diff < 0:  # Date passée
            if date_diff >= -7:
                event['date_indicator'] = 'passe_imminent'
                event['date_indicator_label'] = 'Passé imminent'
                event['date_indicator_badge'] = 'error'
                event['date_indicator_icon'] = 'exclamation-circle'
            else:
                event['date_indicator'] = 'passe'
                event['date_indicator_label'] = 'Passé'
                event['date_indicator_badge'] = 'ghost'
                event['date_indicator_icon'] = 'history'
        elif date_diff == 0:
            event['date_indicator'] = 'aujourd_hui'
            event['date_indicator_label'] = "Aujourd'hui"
            event['date_indicator_badge'] = 'warning'
            event['date_indicator_icon'] = 'clock'
        else:  # Date future
            if date_diff <= 7:
                event['date_indicator'] = 'imminent'
                event['date_indicator_label'] = 'Imminent'
                event['date_indicator_badge'] = 'info'
                event['date_indicator_icon'] = 'exclamation'
            else:
                event['date_indicator'] = 'futur'
                event['date_indicator_label'] = 'Futur'
                event['date_indicator_badge'] = 'ghost'
                event['date_indicator_icon'] = 'calendar'
                if date_diff <= 7:  # Moins de 7 jours dans le futur
                    detail.date_indicator = 'futur_imminent'
                    detail.date_indicator_label = 'Futur imminent'
                    detail.date_indicator_badge = 'info'
                    detail.date_indicator_icon = 'calendar-day'
                else:
                    detail.date_indicator = 'futur'
                    detail.date_indicator_label = 'Futur'
                    detail.date_indicator_badge = 'success'
                    detail.date_indicator_icon = 'calendar-plus'

            details_list_filtered.append(detail)
        else:
            detail.date_indicator = 'inconnu'
            detail.date_indicator_label = 'Inconnu'
            detail.date_indicator_badge = 'ghost'
            detail.date_indicator_icon = 'question'
            # Ne pas filtrer par année si pas de date
            details_list_filtered.append(detail)

    # Remplacer la liste par la version filtrée par année
    details_list = details_list_filtered

    # Filtrer par indicateurs si spécifiés (plusieurs checkboxes possibles)
    if indicateurs_filter:
        details_list = [d for d in details_list if d.date_indicator in indicateurs_filter]

    # Ajouter les informations de tarif et modalité pour chaque détail
    from apps.billing.models import ModaliteGestion
    for detail in details_list:
        if detail.point_eau:
            # Tarif forfaitaire du point d'eau
            detail.tarif_forfaitaire = detail.point_eau.tarifforfaitaire

            # Modalité de paiement active (date_fin null) de l'ouvrage du point d'eau
            if detail.point_eau.ouvrage:
                modalite_active = ModaliteGestion.objects.filter(
                    ouvrage=detail.point_eau.ouvrage,
                    date_fin__isnull=True
                ).first()

                detail.modalite_paiement = modalite_active.get_modalitepaiement_display() if modalite_active and modalite_active.modalitepaiement else 'N/A'
                detail.modalite_paiement_value = modalite_active.modalitepaiement if modalite_active else None
            else:
                detail.modalite_paiement = 'N/A'
                detail.modalite_paiement_value = None
        else:
            detail.tarif_forfaitaire = None
            detail.modalite_paiement = 'N/A'
            detail.modalite_paiement_value = None

    # Filtrer par tarif (avec/sans tarif)
    if tarif_filter == 'with':
        details_list = [d for d in details_list if d.tarif_forfaitaire is not None]
    elif tarif_filter == 'without':
        details_list = [d for d in details_list if d.tarif_forfaitaire is None]

    # Filtrer par modalité de paiement
    if modalite_filter:
        details_list = [d for d in details_list if d.modalite_paiement_value == modalite_filter]

    # Recalculer les statistiques sur les détails filtrés
    # Paiements forfaitaires uniquement
    details_paiement_filtres = [d for d in details_list if d.designation.nom == 'Paiement forfaitaire']
    nb_paiements_planifies = len(details_paiement_filtres)
    montant_planifie = sum([Decimal(str(d.montant)) for d in details_paiement_filtres if d.montant]) or Decimal('0.00')

    # Paiements payés (avec numeroDiameX non null)
    # CRITICAL: Utiliser quantité × tarif comme le dashboard (pas le montant du détail)
    details_payes_filtres = [d for d in details_paiement_filtres if d.numeroDiameX]
    nb_paiements_payes = len(details_payes_filtres)

    # Calculer le montant payé comme le dashboard : quantité × tarif du point d'eau
    montant_paye = Decimal('0.00')
    for d in details_payes_filtres:
        if d.point_eau and d.point_eau.tarifforfaitaire:
            quantite = Decimal(str(d.quantity)) if d.quantity else Decimal('1')
            tarif = Decimal(str(d.point_eau.tarifforfaitaire))
            montant_paye += quantite * tarif

    # Coupures et remises planifiées
    nb_coupures_planifiees = len([d for d in details_list if d.designation.nom == "Coupure d'eau"])
    nb_remises_planifiees = len([d for d in details_list if d.designation.nom == "Remise en eau"])

    # Points d'eau uniques dans les détails filtrés
    points_eau_ids_filtres = set([d.point_eau.id for d in details_list if d.point_eau])
    nb_points_eau_filtres = len(points_eau_ids_filtres)

    # CRITICAL: Montant prévu calculé sur TOUS les points d'eau des filtres géographiques
    # (pas seulement ceux avec des paiements dans l'année)
    # Pour synchroniser avec le dashboard
    points_eau_pour_prevu = points_eau  # Utiliser le queryset initial filtré par commune/ouvrage
    if commune_id:
        points_eau_pour_prevu = points_eau_pour_prevu.filter(parcelle__village__fokontany__commune_id=commune_id)
    if ouvrage_id:
        points_eau_pour_prevu = points_eau_pour_prevu.filter(ouvrage_id=ouvrage_id)

    montant_prevu_filtre = sum([Decimal(str(pe.tarifforfaitaire)) * 4 for pe in points_eau_pour_prevu if pe.tarifforfaitaire]) or Decimal('0.00')

    # Points d'eau filtrés pour les stats de coupure (basés sur les détails)
    points_eau_filtres = PointEau.objects.filter(id__in=points_eau_ids_filtres, tarifforfaitaire__isnull=False)

    # Points d'eau coupés parmi les filtrés
    nb_coupes_filtres = points_eau_filtres.filter(datearretbranchement__isnull=False).count()

    # CALCUL DES STATISTIQUES DE COUPURE/REMISE PAR POINT D'EAU
    # Calculer pour chaque point d'eau: nombre de coupures, durée totale, coupure en cours
    coupure_stats_by_pe = {}
    # Liste de toutes les durées individuelles de coupure pour calculer la médiane
    toutes_durees_coupures = []

    for point_eau_id in points_eau_ids_filtres:
        # Récupérer toutes les coupures et remises pour ce point d'eau
        coupures = [d for d in details_list if d.point_eau and d.point_eau.id == point_eau_id and d.designation.nom in ["Coupure d'eau", "Carnet facture coupure"]]
        remises = [d for d in details_list if d.point_eau and d.point_eau.id == point_eau_id and d.designation.nom == "Remise en eau"]

        # Trier par date
        coupures_sorted = sorted(coupures, key=lambda x: x.planning.date if x.planning and x.planning.date else timezone.now())
        remises_sorted = sorted(remises, key=lambda x: x.planning.date if x.planning and x.planning.date else timezone.now())

        nb_coupures = len(coupures_sorted)
        nb_remises = len(remises_sorted)
        duree_totale_jours = 0
        coupure_en_cours = False
        date_derniere_coupure = None
        duree_coupure_en_cours = 0

        # Calculer les durées entre chaque coupure et remise
        for i, coupure in enumerate(coupures_sorted):
            if coupure.planning and coupure.planning.date:
                date_coupure = coupure.planning.date.astimezone(tz_madagascar).date() if coupure.planning.date.tzinfo else tz_madagascar.localize(coupure.planning.date).date()

                # Chercher la remise correspondante (la suivante chronologiquement)
                remise_correspondante = None
                for remise in remises_sorted:
                    if remise.planning and remise.planning.date:
                        date_remise = remise.planning.date.astimezone(tz_madagascar).date() if remise.planning.date.tzinfo else tz_madagascar.localize(remise.planning.date).date()
                        if date_remise > date_coupure:
                            remise_correspondante = remise
                            break

                if remise_correspondante and remise_correspondante.planning.date:
                    # Coupure avec remise : calculer la durée
                    date_remise = remise_correspondante.planning.date.astimezone(tz_madagascar).date() if remise_correspondante.planning.date.tzinfo else tz_madagascar.localize(remise_correspondante.planning.date).date()
                    duree = (date_remise - date_coupure).days
                    duree_totale_jours += duree
                    toutes_durees_coupures.append(duree)  # Ajouter pour médiane
                else:
                    # Coupure sans remise : en cours
                    coupure_en_cours = True
                    date_derniere_coupure = date_coupure
                    duree_coupure_en_cours = (timezone.now().date() - date_coupure).days
                    duree_totale_jours += duree_coupure_en_cours
                    toutes_durees_coupures.append(duree_coupure_en_cours)  # Ajouter pour médiane

        coupure_stats_by_pe[point_eau_id] = {
            'nb_coupures': nb_coupures,
            'nb_remises': nb_remises,
            'duree_totale_jours': duree_totale_jours,
            'coupure_en_cours': coupure_en_cours,
            'date_derniere_coupure': date_derniere_coupure,
            'duree_coupure_en_cours': duree_coupure_en_cours
        }

    # Statistiques globales de coupure
    total_coupures = sum([stats['nb_coupures'] for stats in coupure_stats_by_pe.values()])
    total_remises = sum([stats['nb_remises'] for stats in coupure_stats_by_pe.values()])
    nb_points_eau_coupes_en_cours = sum([1 for stats in coupure_stats_by_pe.values() if stats['coupure_en_cours']])
    duree_moyenne_coupure = round(sum([stats['duree_totale_jours'] for stats in coupure_stats_by_pe.values()]) / total_coupures) if total_coupures > 0 else 0

    # Calculer la médiane de la durée de coupure
    duree_mediane_coupure = 0
    if toutes_durees_coupures:
        toutes_durees_coupures_sorted = sorted(toutes_durees_coupures)
        n = len(toutes_durees_coupures_sorted)
        if n % 2 == 0:
            # Nombre pair : moyenne des deux valeurs du milieu
            duree_mediane_coupure = round((toutes_durees_coupures_sorted[n//2 - 1] + toutes_durees_coupures_sorted[n//2]) / 2)
        else:
            # Nombre impair : valeur du milieu
            duree_mediane_coupure = toutes_durees_coupures_sorted[n//2]

    # Taux de recouvrement
    taux_recouvrement = 0
    if montant_prevu_filtre > 0:
        taux_recouvrement = int(round((float(montant_paye) / float(montant_prevu_filtre)) * 100))

    # Convertir en milliers
    montant_prevu_k = round(float(montant_prevu_filtre) / 1000)
    montant_planifie_k = round(float(montant_planifie) / 1000)
    montant_paye_k = round(float(montant_paye) / 1000)

    # CALCUL DES STATISTIQUES PAR POINT D'EAU (comme le dashboard)
    # Pour synchroniser avec /dashboard/paiements-forfaitaires/
    nb_tout_paye_pe = 0
    nb_partiellement_paye_pe = 0
    nb_non_paye_pe = 0
    nb_coupe_pe = 0

    # Utiliser l'année filtrée pour le calcul des trimestres
    annee_calcul = annee_int

    # CRITICAL: Utiliser TOUS les points d'eau (pas seulement ceux avec détails)
    for pe in points_eau_pour_prevu:
        tarif = Decimal(str(pe.tarifforfaitaire)) if pe.tarifforfaitaire else Decimal('0.00')
        if tarif == 0:
            continue

        # Récupérer les paiements pour cette année
        paiements_annee = PlanningDetail.objects.filter(
            point_eau=pe,
            designation__nom='Paiement forfaitaire'
        ).select_related('planning')

        # Calculer les paiements par trimestre avec conversion timezone
        trimestres_payes = {1: False, 2: False, 3: False, 4: False}

        for paiement in paiements_annee:
            if paiement.planning and paiement.planning.date and paiement.numeroDiameX:
                date_aware = paiement.planning.date
                if date_aware.tzinfo:
                    date_madagascar = date_aware.astimezone(tz_madagascar)
                else:
                    date_madagascar = tz_madagascar.localize(date_aware)

                date_obj = date_madagascar.date()

                # Vérifier l'année filtrée
                if date_obj.year == annee_calcul:
                    # Déterminer le trimestre (1-4)
                    mois = date_obj.month
                    if 1 <= mois <= 3:
                        trimestres_payes[1] = True
                    elif 4 <= mois <= 6:
                        trimestres_payes[2] = True
                    elif 7 <= mois <= 9:
                        trimestres_payes[3] = True
                    elif 10 <= mois <= 12:
                        trimestres_payes[4] = True

        # Compter combien de trimestres sont payés
        nb_trimestres_payes = sum(trimestres_payes.values())

        # Vérifier si le point d'eau est coupé
        est_coupe = pe.datearretbranchement is not None

        # Catégoriser le point d'eau
        if est_coupe:
            nb_coupe_pe += 1
        elif nb_trimestres_payes == 4:
            nb_tout_paye_pe += 1
        elif nb_trimestres_payes > 0:
            nb_partiellement_paye_pe += 1
        else:
            nb_non_paye_pe += 1

    # Récupérer seulement les 3 désignations pertinentes pour le filtre
    from apps.planning.models import Designation
    designations = Designation.objects.filter(
        nom__in=['Paiement forfaitaire', "Coupure d'eau", 'Remise en eau']
    ).order_by('nom')

    # Pagination
    from django.core.paginator import Paginator
    total_lignes = len(details_list)
    page_number = request.GET.get('page', 1)
    paginator = Paginator(details_list, 50)  # 50 lignes par page
    page_obj = paginator.get_page(page_number)

    # Récupérer les modalités de paiement disponibles
    from apps.billing.models import ModaliteGestion
    modalites_choices = ModaliteGestion.MODALITE_PAIEMENT_CHOICES

    # Générer la liste des années disponibles (de 2020 à année courante + 1)
    annees_disponibles = list(range(2020, annee_courante + 2))

    context = {
        'details': page_obj.object_list,
        'page_obj': page_obj,
        'total_lignes': total_lignes,
        'nb_points_eau': nb_points_eau_filtres,  # Utiliser les points d'eau filtrés
        'montant_prevu': montant_prevu_filtre,
        'montant_prevu_k': montant_prevu_k,
        'nb_paiements_planifies': nb_paiements_planifies,
        'montant_planifie': montant_planifie,
        'montant_planifie_k': montant_planifie_k,
        'nb_paiements_payes': nb_paiements_payes,
        'montant_paye': montant_paye,
        'montant_paye_k': montant_paye_k,
        'taux_recouvrement': taux_recouvrement,
        'nb_coupes': nb_coupes_filtres,  # Utiliser les coupures filtrées
        'nb_coupures_planifiees': nb_coupures_planifiees,
        'nb_remises_planifiees': nb_remises_planifiees,
        # Statistiques de coupure
        'total_coupures': total_coupures,
        'total_remises': total_remises,
        'nb_points_eau_coupes_en_cours': nb_points_eau_coupes_en_cours,
        'duree_moyenne_coupure': duree_moyenne_coupure,
        'duree_mediane_coupure': duree_mediane_coupure,
        'coupure_stats_by_pe': coupure_stats_by_pe,
        # Statistiques par point d'eau (comme dashboard)
        'nb_tout_paye_pe': nb_tout_paye_pe,
        'nb_partiellement_paye_pe': nb_partiellement_paye_pe,
        'nb_non_paye_pe': nb_non_paye_pe,
        'nb_coupe_pe': nb_coupe_pe,
        'communes': communes,
        'ouvrages': ouvrages_list,
        'points_eau': points_eau_formatted,
        'designations': designations,
        'annees_disponibles': annees_disponibles,
        'annee_filter': annee_filter,
        'commune_filter': commune_id,
        'ouvrage_filter': ouvrage_id,
        'point_eau_filter': point_eau_id,
        'indicateurs_filter': indicateurs_filter,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'commune_non_assignee': commune_non_assignee,
        'designation_filter': designation_id,
        'statut_filter': statut_filter,
        'tarif_filter': tarif_filter,
        'modalite_filter': modalite_filter,
        'modalites_choices': modalites_choices,
        'quantite_filter': quantite_filter,
    }

    return render(request, 'planning/gestion_forfaitaire.html', context)


def detail_forfaitaire_modal(request):
    """API pour récupérer les détails d'un compteur spécifique"""
    type_detail = request.GET.get('type')  # prevu, planifie, paye
    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    if type_detail == 'prevu':
        # Détail par point d'eau avec tarif prévu
        points_eau = PointEau.objects.filter(tarifforfaitaire__isnull=False).select_related(
            'ouvrage',
            'parcelle__village__fokontany__commune'
        )
        if commune_id:
            points_eau = points_eau.filter(parcelle__village__fokontany__commune_id=commune_id)
        if ouvrage_id:
            points_eau = points_eau.filter(ouvrage_id=ouvrage_id)

        data = []
        for pe in points_eau:
            # Calculer planifié et payé pour ce point d'eau
            details_pe = PlanningDetail.objects.filter(
                point_eau=pe,
                designation__nom='Paiement forfaitaire'
            )
            # Appliquer les filtres de date
            if date_debut:
                details_pe = details_pe.filter(planning__date__gte=date_debut)
            if date_fin:
                details_pe = details_pe.filter(planning__date__lte=date_fin)

            montant_planifie = details_pe.aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
            montant_paye = details_pe.filter(numeroDiameX__isnull=False).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')

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
        details = PlanningDetail.objects.filter(
            designation__nom='Paiement forfaitaire'
        ).select_related(
            'planning',
            'point_eau',
            'point_eau__ouvrage',
            'point_eau__parcelle__village__fokontany__commune'
        )
        if commune_id:
            details = details.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
        if ouvrage_id:
            details = details.filter(planning__ouvrage_id=ouvrage_id)
        if date_debut:
            details = details.filter(planning__date__gte=date_debut)
        if date_fin:
            details = details.filter(planning__date__lte=date_fin)

        # Convertir les dates en timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        data = []
        for detail in details:
            # Convertir la date
            date_str = 'N/A'
            if detail.planning and detail.planning.date:
                date_aware = detail.planning.date if detail.planning.date.tzinfo else timezone.make_aware(detail.planning.date)
                date_madagascar = date_aware.astimezone(tz_madagascar)
                date_str = date_madagascar.strftime('%d/%m/%Y')

            data.append({
                'date': date_str,
                'point_eau': detail.point_eau.nomabonne if detail.point_eau else 'N/A',
                'ouvrage': detail.point_eau.ouvrage.nom_ouvrage if detail.point_eau and detail.point_eau.ouvrage else 'N/A',
                'montant': float(detail.montant),
                'paye': detail.numeroDiameX is not None,
            })

        return JsonResponse({'success': True, 'data': data})

    elif type_detail == 'paye':
        # Détail des paiements payés
        details = PlanningDetail.objects.filter(
            designation__nom='Paiement forfaitaire',
            numeroDiameX__isnull=False
        ).select_related(
            'planning',
            'point_eau',
            'point_eau__ouvrage',
            'point_eau__parcelle__village__fokontany__commune'
        )
        if commune_id:
            details = details.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
        if ouvrage_id:
            details = details.filter(planning__ouvrage_id=ouvrage_id)
        if date_debut:
            details = details.filter(planning__date__gte=date_debut)
        if date_fin:
            details = details.filter(planning__date__lte=date_fin)

        # Convertir les dates en timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        data = []
        for detail in details:
            # Convertir la date
            date_str = 'N/A'
            if detail.planning and detail.planning.date:
                date_aware = detail.planning.date if detail.planning.date.tzinfo else timezone.make_aware(detail.planning.date)
                date_madagascar = date_aware.astimezone(tz_madagascar)
                date_str = date_madagascar.strftime('%d/%m/%Y')

            data.append({
                'date': date_str,
                'point_eau': detail.point_eau.nomabonne if detail.point_eau else 'N/A',
                'ouvrage': detail.point_eau.ouvrage.nom_ouvrage if detail.point_eau and detail.point_eau.ouvrage else 'N/A',
                'montant': float(detail.montant),
                'numero_diamex': detail.numeroDiameX,
            })

        return JsonResponse({'success': True, 'data': data})

    elif type_detail == 'coupes':
        # Détail des points d'eau coupés (avec tarifforfaitaire non null)
        points_eau = PointEau.objects.filter(
            tarifforfaitaire__isnull=False,
            datearretbranchement__isnull=False
        ).select_related(
            'ouvrage',
            'parcelle__village__fokontany__commune'
        )
        if commune_id:
            points_eau = points_eau.filter(parcelle__village__fokontany__commune_id=commune_id)
        if ouvrage_id:
            points_eau = points_eau.filter(ouvrage_id=ouvrage_id)
        if date_debut:
            points_eau = points_eau.filter(datearretbranchement__gte=date_debut)
        if date_fin:
            points_eau = points_eau.filter(datearretbranchement__lte=date_fin)

        data = [{
            'point_eau': pe.nomabonne,
            'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
            'commune': pe.parcelle.village.fokontany.commune.nom_commune if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany and pe.parcelle.village.fokontany.commune else 'N/A',
            'date_arret': pe.datearretbranchement.strftime('%d/%m/%Y') if pe.datearretbranchement else 'N/A',
        } for pe in points_eau]

        return JsonResponse({'success': True, 'data': data})

    return JsonResponse({'error': 'Type de détail invalide'}, status=400)


@csrf_exempt
def update_detail_point_eau(request):
    """API pour mettre à jour le point d'eau d'un détail"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            detail_id = data.get('detail_id')
            point_eau_id = data.get('point_eau_id')

            detail = PlanningDetail.objects.get(id=detail_id)
            detail.point_eau_id = point_eau_id
            detail.save()

            return JsonResponse({'success': True})
        except PlanningDetail.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Détail non trouvé'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)


@csrf_exempt
def delete_detail_forfaitaire(request):
    """API pour supprimer un détail de planning forfaitaire"""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            detail_id = data.get('detail_id')

            detail = PlanningDetail.objects.get(id=detail_id)
            detail.delete()

            return JsonResponse({'success': True})
        except PlanningDetail.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Détail non trouvé'}, status=404)
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
    """API pour récupérer tous les points d'eau"""
    # Charger TOUS les points d'eau (pas de limite) pour éviter de perdre des données
    # Performance: ~3000 points = acceptable en JSON
    points_eau = PointEau.objects.select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune'
    ).order_by('nomabonne')  # Supprimer la limite [:1000]

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
    """API pour récupérer les données d'un PlanningDetail"""
    try:
        detail = PlanningDetail.objects.get(id=detail_id)

        data = {
            'quantity': float(detail.quantity) if detail.quantity else 0,
            'pu': float(detail.pu) if detail.pu else 0,
        }

        return JsonResponse({'success': True, 'data': data})
    except PlanningDetail.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Détail non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
def update_quantity_prix(request):
    """API pour mettre à jour la quantité et le prix unitaire d'un PlanningDetail"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            detail_id = data.get('detail_id')
            quantity = data.get('quantity')
            prix = data.get('prix')

            if not detail_id or quantity is None or prix is None:
                return JsonResponse({'success': False, 'error': 'Paramètres manquants'}, status=400)

            # Valider les valeurs
            try:
                quantity = float(quantity)
                prix = float(prix)
                if quantity < 0 or prix < 0:
                    return JsonResponse({'success': False, 'error': 'Les valeurs ne peuvent pas être négatives'}, status=400)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Valeurs invalides'}, status=400)

            # Mettre à jour le PlanningDetail
            detail = PlanningDetail.objects.get(id=detail_id)
            detail.quantity = quantity
            detail.pu = Decimal(str(prix))
            # Recalculer le montant (quantity * pu)
            detail.montant = Decimal(str(quantity)) * Decimal(str(prix))
            detail.save()

            return JsonResponse({
                'success': True,
                'message': 'Quantité et prix mis à jour avec succès',
                'quantity': quantity,
                'pu': prix,
                'montant': float(detail.montant)
            })
        except PlanningDetail.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Détail non trouvé'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
