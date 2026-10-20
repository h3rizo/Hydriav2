from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import json
from apps.planning.models import Planning, PlanningDetail
from apps.billing.models import PointEau, Releve
from apps.geography.models import Commune
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_user_accessible_gestionnaire_ids,
)
import pytz


def _get_user_gestionnaire_ids(user):
    return get_user_accessible_gestionnaire_ids(user)


def gestion_volumetrique(request):
    """Page de gestion des paiements au volume (relevés)"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))

    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    point_eau_id = request.GET.get('point_eau', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    statut_filter = request.GET.get('statut', '')  # en_attente, paye, impaye
    avec_numero_diamex = request.GET.get('avec_numero_diamex', '')  # 'true' ou 'false'

    # CRITICAL: Récupérer les ouvrages avec modalité au volume ou mixte uniquement
    from apps.billing.models import ModaliteGestion
    gestionnaire_ids = _get_user_gestionnaire_ids(request.user)
    modalites_qs = ModaliteGestion.objects.filter(
        date_fin__isnull=True,  # Modalite active
        modalitepaiement__in=['au_volume', 'mixte']
    )
    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            modalites_qs = modalites_qs.filter(gestionnaire_id__in=gestionnaire_ids)
        else:
            modalites_qs = modalites_qs.none()
    ouvrages_volumetriques_ids = set(
        modalites_qs.values_list('ouvrage_id', flat=True).distinct()
    )
    ouvrages_volumetriques_ids = apply_user_responsable_ouvrage_scope(
        ouvrages_volumetriques_ids,
        request.user,
        allow_same_base_support_roles=True,
    )

    # Filtrer les relevés des ouvrages au volume/mixte
    releves = Releve.objects.filter(
        point_eau__ouvrage_id__in=ouvrages_volumetriques_ids
    ).select_related(
        'point_eau',
        'point_eau__type_point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune'
    )

    # Appliquer les filtres
    if commune_id:
        releves = releves.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
    if ouvrage_id:
        releves = releves.filter(point_eau__ouvrage_id=ouvrage_id)
    if point_eau_id:
        releves = releves.filter(point_eau_id=point_eau_id)
    if date_debut:
        releves = releves.filter(datereleve__gte=date_debut)
    if date_fin:
        releves = releves.filter(datereleve__lte=date_fin)
    if statut_filter:
        releves = releves.filter(statut=statut_filter)

    # Filtre par présence de numeroDiameX (payé en comptabilité)
    if avec_numero_diamex == 'true':
        releves = releves.exclude(numeroDiameX__isnull=True).exclude(numeroDiameX='')
    elif avec_numero_diamex == 'false':
        releves = releves.filter(Q(numeroDiameX__isnull=True) | Q(numeroDiameX=''))

    # CRITICAL: Filtrer pour ne garder que les relevés avec montant > 0 (factures réelles)
    # ET exclure les relevés avec "coupé" dans la remarque (pas de facture à recouvrer)
    releves = releves.exclude(Q(montant__isnull=True) | Q(montant=0) | Q(remarque__icontains='coupé'))

    # Listes pour les dropdowns - FILTRER par modalité au volume/mixte
    communes = Commune.objects.filter(
        id__in=PointEau.objects.filter(
            ouvrage_id__in=ouvrages_volumetriques_ids
        ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()
    ).order_by('nom_commune')

    from apps.organization.models import Ouvrage
    ouvrages = Ouvrage.objects.filter(
        id__in=ouvrages_volumetriques_ids
    ).order_by('nom_ouvrage')

    # Ajouter les IDs des communes pour chaque ouvrage (pour filtrage en cascade)
    ouvrages_list = []
    for ouvrage in ouvrages:
        communes_ids = PointEau.objects.filter(
            ouvrage=ouvrage,
            parcelle__village__fokontany__commune__isnull=False
        ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()

        ouvrage.communes_ids = ','.join([str(c_id) for c_id in communes_ids])
        ouvrages_list.append(ouvrage)

    # Liste des points d'eau pour le dropdown
    points_eau_list = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_volumetriques_ids
    ).select_related('type_point_eau', 'ouvrage')
    if ouvrage_id:
        points_eau_list = points_eau_list.filter(ouvrage_id=ouvrage_id)

    points_eau_formatted = []
    for pe in points_eau_list:
        pe.ouvrage_id_str = str(pe.ouvrage.id) if pe.ouvrage else ''
        pe.display_name = pe.code_point_eau or pe.nomabonne or f'Point eau {pe.id}'
        points_eau_formatted.append(pe)

    # Filtrer par année (conversion timezone)
    today = timezone.now().date()
    releves_list = list(releves.order_by('-datereleve'))
    annee_int = int(annee_filter) if annee_filter else annee_courante

    from apps.accounting.views import _build_coupure_periods_by_point
    from apps.accounting.volume_recovery import (
        build_recouvrement_par_ouvrage_mois,
        build_score_totals_from_releves,
        build_volume_kpis,
        split_mois,
    )
    mois_passes_set, mois_en_cours_num = split_mois(annee_int, today)
    mois_courant_set = {mois_en_cours_num} if mois_en_cours_num else set()

    def _split_counts(mois_dict, numeros):
        tot = sum(m['total'] for k, m in mois_dict.items() if k in numeros)
        pay = sum(m['payes'] for k, m in mois_dict.items() if k in numeros)
        imp = sum(m['impayes'] for k, m in mois_dict.items() if k in numeros)
        return tot, pay, imp, (int(round(pay / tot * 100)) if tot else 0)

    releves_list_filtered = []
    for releve in releves_list:
        if releve.datereleve:
            # Le champ datereleve est déjà une date (pas datetime)
            date_obj = releve.datereleve

            # CRITICAL: La facture est pour le mois SUIVANT le relevé
            # Un relevé de mars → facture d'avril
            # Un relevé de décembre 2024 → facture de janvier 2025
            from dateutil.relativedelta import relativedelta
            date_facture = date_obj + relativedelta(months=1)

            # Filtrer par année (année de la facture, pas du relevé)
            if date_facture.year != annee_int:
                continue

            # Calculer l'indicateur de date
            date_diff = (date_obj - today).days

            if date_diff < 0:  # Date passée
                if date_diff >= -7:
                    releve.date_indicator = 'passe_imminent'
                    releve.date_indicator_label = 'Relevé ancien'
                    releve.date_indicator_badge = 'error'
                    releve.date_indicator_icon = 'exclamation-circle'
                elif date_diff >= -30:
                    releve.date_indicator = 'passe'
                    releve.date_indicator_label = 'Ce mois'
                    releve.date_indicator_badge = 'ghost'
                    releve.date_indicator_icon = 'history'
                else:
                    releve.date_indicator = 'passe_ancien'
                    releve.date_indicator_label = 'Ancien'
                    releve.date_indicator_badge = 'neutral'
                    releve.date_indicator_icon = 'archive'
            elif date_diff == 0:
                releve.date_indicator = 'aujourd_hui'
                releve.date_indicator_label = "Aujourd'hui"
                releve.date_indicator_badge = 'warning'
                releve.date_indicator_icon = 'clock'
            else:  # Futur
                releve.date_indicator = 'futur'
                releve.date_indicator_label = 'Futur'
                releve.date_indicator_badge = 'info'
                releve.date_indicator_icon = 'calendar'

            # Ajouter des informations supplémentaires
            releve.commune_nom = releve.point_eau.parcelle.village.fokontany.commune.nom_commune if (
                releve.point_eau and
                releve.point_eau.parcelle and
                releve.point_eau.parcelle.village and
                releve.point_eau.parcelle.village.fokontany and
                releve.point_eau.parcelle.village.fokontany.commune
            ) else 'N/A'

            releve.ouvrage_nom = releve.point_eau.ouvrage.nom_ouvrage if (releve.point_eau and releve.point_eau.ouvrage) else 'N/A'
            releve.point_eau_nom = releve.point_eau.nomabonne or releve.point_eau.code_point_eau or f'PE-{releve.point_eau.id}' if releve.point_eau else 'N/A'

            # Vérifier si le point d'eau est coupé
            releve.est_coupe = releve.point_eau.is_cut if releve.point_eau else False

            # Déterminer le statut réel basé sur numeroDiameX
            releve.statut_reel = 'paye' if releve.est_paye else releve.statut

            # Ajouter la date de facture calculée (pour affichage si nécessaire)
            releve.date_facture = date_facture

            releves_list_filtered.append(releve)

    # Calculer les statistiques
    # IMPORTANT: Utiliser UNIQUEMENT est_paye (basé sur numeroDiameX) pour déterminer le statut de paiement
    # Le champ 'statut' n'est pas toujours synchronisé avec numeroDiameX
    total_releves = len(releves_list_filtered)
    montant_total = sum([float(r.montant) if r.montant else 0 for r in releves_list_filtered])
    montant_paye = sum([float(r.montant) if r.montant and r.est_paye else 0 for r in releves_list_filtered])
    montant_impaye = sum([float(r.montant) if r.montant and not r.est_paye else 0 for r in releves_list_filtered])
    montant_attente = 0  # Pas utilisé, tout est soit payé soit impayé

    volume_total = sum([float(r.volume_facture) if r.volume_facture else 0 for r in releves_list_filtered])
    nb_paye = sum([1 for r in releves_list_filtered if r.est_paye])
    nb_impaye = sum([1 for r in releves_list_filtered if not r.est_paye])
    nb_attente = 0  # Pas utilisé, tout est soit payé soit impayé

    taux_recouvrement = (montant_paye / montant_total * 100) if montant_total > 0 else 0

    # Convertir en milliers d'Ar
    montant_total_k = montant_total / 1000
    montant_paye_k = montant_paye / 1000
    montant_attente_k = montant_attente / 1000
    montant_impaye_k = montant_impaye / 1000

    # SECTION CALCUL DEPUIS COMPTABILITÉ - Tableau par ouvrage et type
    # Organiser les données par ouvrage et type de point d'eau
    donnees_par_ouvrage_type = {}
    mois_liste = list(range(1, 13))  # Janvier à Décembre

    # Initialiser la structure
    points_eau_qs_all = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_volumetriques_ids
    ).select_related('ouvrage', 'type_point_eau')

    # Filtrer points d'eau selon les critères
    if commune_id:
        points_eau_qs_all = points_eau_qs_all.filter(
            parcelle__village__fokontany__commune_id=commune_id
        )
    if ouvrage_id:
        points_eau_qs_all = points_eau_qs_all.filter(ouvrage_id=ouvrage_id)

    for pe in points_eau_qs_all:
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
                'mois': {mois: {'total': 0, 'payes': 0, 'impayes': 0} for mois in mois_liste}
            }

        donnees_par_ouvrage_type[key]['points_eau_ids'].add(str(pe.id))

        if pe.is_cut:
            donnees_par_ouvrage_type[key]['nb_coupes'] += 1

    # Remplir les données des relevés
    for releve in releves_list:
        if not releve.datereleve or not releve.point_eau or not releve.point_eau.ouvrage or not releve.point_eau.type_point_eau:
            continue

        date_obj = releve.datereleve

        # CRITICAL: La facture est pour le mois SUIVANT le relevé
        date_facture = date_obj + relativedelta(months=1)

        # Filtrer par année (année de la facture)
        if date_facture.year != annee_int:
            continue

        pe = releve.point_eau
        key = (str(pe.ouvrage.id), str(pe.type_point_eau.id))
        mois = date_facture.month

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
        total_releves_ligne = sum(m['total'] for m in data['mois'].values())
        if total_releves_ligne == 0:
            continue

        # Calculer les stats par ligne
        total_payes_ligne = sum(m['payes'] for m in data['mois'].values())
        total_impayes_ligne = sum(m['impayes'] for m in data['mois'].values())
        taux_ligne = int(round(total_payes_ligne / total_releves_ligne * 100)) if total_releves_ligne > 0 else 0

        # Déterminer le statut global
        if total_impayes_ligne == 0 and total_payes_ligne > 0:
            statut_global = 'tout_paye'
        elif total_payes_ligne == 0:
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
            'total_releves': total_releves_ligne,
            'total_payes': total_payes_ligne,
            'total_impayes': total_impayes_ligne,
            'taux': taux_ligne,
            'statut_global': statut_global,
            'total_releves_passes': rp_tot, 'total_payes_passes': rp_pay,
            'total_impayes_passes': rp_imp, 'taux_passes': rp_taux,
            'total_releves_courant': rc_tot, 'total_payes_courant': rc_pay,
            'total_impayes_courant': rc_imp, 'taux_courant': rc_taux,
            'settled_past': rp_imp == 0,
            'settled_current': rc_imp == 0,
        })

    mois_colonnes_globales = [
        {'number': 1, 'label': 'Jan'},
        {'number': 2, 'label': 'Fév'},
        {'number': 3, 'label': 'Mar'},
        {'number': 4, 'label': 'Avr'},
        {'number': 5, 'label': 'Mai'},
        {'number': 6, 'label': 'Jun'},
        {'number': 7, 'label': 'Jul'},
        {'number': 8, 'label': 'Aoû'},
        {'number': 9, 'label': 'Sep'},
        {'number': 10, 'label': 'Oct'},
        {'number': 11, 'label': 'Nov'},
        {'number': 12, 'label': 'Déc'},
    ]
    visible_mois_liste = [
        month['number']
        for month in mois_colonnes_globales
        if any(
            data['mois'][month['number']]['total'] > 0
            or data['mois'][month['number']]['payes'] > 0
            or data['mois'][month['number']]['impayes'] > 0
            for data in tableau_data
        )
    ]
    visible_mois_colonnes_globales = [
        month
        for month in mois_colonnes_globales
        if month['number'] in visible_mois_liste
    ]

    # Trier par ouvrage puis par type
    tableau_data.sort(key=lambda x: (x['ouvrage'].nom_ouvrage, x['type_point_eau'].nom_type))

    # Calculer les sous-totaux par ouvrage
    sous_totaux_par_ouvrage = {}
    for data in tableau_data:
        ouvrage_id_key = str(data['ouvrage'].id)

        if ouvrage_id_key not in sous_totaux_par_ouvrage:
            sous_totaux_par_ouvrage[ouvrage_id_key] = {
                'ouvrage': data['ouvrage'],
                'nb_points_eau': 0,
                'mois': {mois: {'total': 0, 'payes': 0, 'impayes': 0} for mois in mois_liste},
                'total_releves': 0,
                'total_payes': 0,
                'total_impayes': 0,
                'taux': 0
            }

        # Accumuler les totaux
        sous_totaux_par_ouvrage[ouvrage_id_key]['nb_points_eau'] += data['nb_points_eau']
        sous_totaux_par_ouvrage[ouvrage_id_key]['total_releves'] += data['total_releves']
        sous_totaux_par_ouvrage[ouvrage_id_key]['total_payes'] += data['total_payes']
        sous_totaux_par_ouvrage[ouvrage_id_key]['total_impayes'] += data['total_impayes']

        # Accumuler par mois
        for mois in mois_liste:
            sous_totaux_par_ouvrage[ouvrage_id_key]['mois'][mois]['total'] += data['mois'][mois]['total']
            sous_totaux_par_ouvrage[ouvrage_id_key]['mois'][mois]['payes'] += data['mois'][mois]['payes']
            sous_totaux_par_ouvrage[ouvrage_id_key]['mois'][mois]['impayes'] += data['mois'][mois]['impayes']

    # Calculer les taux pour chaque sous-total (+ dédoublement passés / en cours)
    for ouvrage_id_key, st in sous_totaux_par_ouvrage.items():
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

    # --- Blocs KPI (Général / Mois passés / Mois en cours) + colonnes mensuelles ---
    facture_counts_par_mois = {mois: {'total': 0, 'payes': 0, 'impayes': 0} for mois in mois_liste}
    for data in tableau_data:
        for mois in mois_liste:
            cell = data['mois'][mois]
            facture_counts_par_mois[mois]['total'] += cell['total']
            facture_counts_par_mois[mois]['payes'] += cell['payes']
            facture_counts_par_mois[mois]['impayes'] += cell['impayes']

    point_eau_ids_scope = [str(i) for i in points_eau_qs_all.values_list('id', flat=True)]
    periodes_coupure = _build_coupure_periods_by_point(point_eau_ids_scope)
    ouvrages_scope_ids = set(points_eau_qs_all.values_list('ouvrage_id', flat=True).distinct())
    recouvrement_par_ouvrage_mois = build_recouvrement_par_ouvrage_mois(
        releves_list, ouvrages_scope_ids, annee_int, periodes_coupure, gestionnaire_ids,
    )
    score_totals_by_point = build_score_totals_from_releves(
        releves_list, annee_int, periodes_coupure, today,
    )
    # Coupés depuis moins d'un an (règle partagée : abandonnés et sans date à part)
    from apps.billing.points_eau_statut import q_coupe
    points_eau_coupes_count = points_eau_qs_all.filter(q_coupe()).count()
    kpis = build_volume_kpis(
        recouvrement_par_ouvrage_mois=recouvrement_par_ouvrage_mois,
        facture_counts_par_mois=facture_counts_par_mois,
        score_totals_by_point=score_totals_by_point,
        points_eau_coupes_count=points_eau_coupes_count,
        annee_int=annee_int,
        today=today,
    )

    mois_colonnes_visibles = []
    for month in visible_mois_colonnes_globales:
        n = month['number']
        counts = facture_counts_par_mois.get(n, {})
        col_taux = (
            int(round(counts.get('payes', 0) / counts['total'] * 100))
            if counts.get('total') else None
        )
        mois_colonnes_visibles.append({
            'number': n, 'label': month['label'],
            'is_current': n == mois_en_cours_num,
            'settled': col_taux == 100,
        })

    # Ajouter un indicateur de changement d'ouvrage et les sous-totaux
    ouvrage_precedent = None
    for i, data in enumerate(tableau_data):
        ouvrage_id_key = str(data['ouvrage'].id)
        data['nouveau_groupe_ouvrage'] = (ouvrage_precedent is None or ouvrage_id_key != ouvrage_precedent)

        # Ajouter le sous-total pour cet ouvrage
        if data['nouveau_groupe_ouvrage']:
            data['sous_total_ouvrage'] = sous_totaux_par_ouvrage[ouvrage_id_key]

        ouvrage_precedent = ouvrage_id_key

    context = {
        'releves': releves_list_filtered[:500],  # Limite 500 résultats affichés
        'total_releves': total_releves,
        'montant_total_k': montant_total_k,
        'montant_paye_k': montant_paye_k,
        'montant_attente_k': montant_attente_k,
        'montant_impaye_k': montant_impaye_k,
        'volume_total': volume_total,
        'nb_paye': nb_paye,
        'nb_attente': nb_attente,
        'nb_impaye': nb_impaye,
        'taux_recouvrement': round(taux_recouvrement, 1),

        # Filtres
        'communes': communes,
        'ouvrages': ouvrages_list,
        'points_eau': points_eau_formatted,
        'annee_filter': annee_filter,
        'commune_id': commune_id,
        'ouvrage_id': ouvrage_id,
        'point_eau_id': point_eau_id,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'statut_filter': statut_filter,
        'avec_numero_diamex': avec_numero_diamex,

        # Tableau calcul depuis comptabilité
        'tableau_data': tableau_data,
        'mois_liste': visible_mois_liste,
        'mois_noms': [month['label'] for month in visible_mois_colonnes_globales],
        'mois_colonnes_visibles': mois_colonnes_visibles,
        'mois_en_cours_num': mois_en_cours_num,
        'kpis': kpis,
    }

    return render(request, 'planning/gestion_volumetrique.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_releve_diamex(request, releve_id):
    """API pour mettre à jour les numéros DiameX et le montant d'un relevé"""
    try:
        releve_qs = Releve.objects.all()
        gestionnaire_ids = _get_user_gestionnaire_ids(request.user)
        if gestionnaire_ids is not None:
            if not gestionnaire_ids:
                return JsonResponse({
                    'success': False,
                    'error': 'Acces refuse'
                }, status=403)
            releve_qs = releve_qs.filter(
                point_eau__ouvrage__modalites_gestion__date_fin__isnull=True,
                point_eau__ouvrage__modalites_gestion__gestionnaire_id__in=gestionnaire_ids
            ).distinct()

        allowed_ouvrage_ids = apply_user_responsable_ouvrage_scope(
            None,
            request.user,
            allow_same_base_support_roles=True,
        )
        if allowed_ouvrage_ids is not None:
            releve_qs = releve_qs.filter(point_eau__ouvrage_id__in=allowed_ouvrage_ids)

        releve = get_object_or_404(releve_qs, id=releve_id)

        data = json.loads(request.body) if request.body else {}
        numero_diamex = data.get('numeroDiameX', '').strip()
        base_diamex = data.get('baseDiameX', '').strip()
        montant = data.get('montant', '').strip()

        # Mise à jour des champs
        releve.numeroDiameX = numero_diamex if numero_diamex else None
        releve.baseDiameX = base_diamex if base_diamex else None

        # Mise à jour du montant
        if montant:
            try:
                releve.montant = Decimal(montant)
            except (ValueError, TypeError):
                releve.montant = None
        else:
            releve.montant = None

        releve.save()

        return JsonResponse({
            'success': True,
            'message': 'Données mises à jour avec succès',
            'releve': {
                'id': str(releve.id),
                'numeroDiameX': releve.numeroDiameX or '',
                'baseDiameX': releve.baseDiameX or '',
                'montant': str(releve.montant) if releve.montant else '',
                'est_paye': releve.est_paye
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

