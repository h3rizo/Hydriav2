"""
Vue pour le dashboard des paiements forfaitaires

Ce module implémente le tableau de bord d'analyse des paiements forfaitaires (compte 748411)
avec calcul des montants à collecter en tenant compte des décotes pour coupures d'eau.
"""

from django.shortcuts import render
from apps.billing.tarifs_forfaitaires import tarif_pour_annee
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Sum, Count
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta, date
from calendar import monthrange
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import pytz
import json
import os

from apps.accounting.models import BaseDiameX, ExplicationPaiementForfaitaire
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
from apps.accounting.pointage_auto import build_auto_pointage_forfaitaire_suggestions
from apps.billing.models import PointEau, CoupureEau, PaiementForfaitaire, ModaliteGestion
from apps.employees.permissions import can_manage_forfaitaire_factures, can_reschedule_forfaitaire_factures
from apps.employees.models import Employe, EmployeBaseDiameX
from apps.messaging.forfaitaire_sync import close_forfaitaire_conversation, ensure_forfaitaire_conversation
from apps.organization.models import Ouvrage, Organisation
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    filter_current_modalites,
    get_user_accessible_gestionnaire_ids,
    get_user_organisation,
)
from apps.geography.models import District, Commune, Region
from apps.accounting.dashboard_employee_filter import (
    build_employee_geo_filter_options,
    calculate_water_point_score,
    get_water_point_score_gap_ids,
    is_closed_payment_month,
    resolve_dashboard_employee_filter,
    resolve_score_scope,
)

DETAIL_DEFAULT_PAGE_SIZE = 25
DETAIL_MAX_PAGE_SIZE = 200
FORFAITAIRE_MODALITES_PAIEMENT = ('forfaitaire', 'mixte')


def _trimestres_exigibles(annee):
    """
    Nombre de trimestres exigibles selon la date du jour.
    """
    today = timezone.localdate()
    if annee < today.year:
        return 4
    if annee > today.year:
        return 0
    return ((today.month - 1) // 3) + 1


def _quarter_of_date(date_value):
    return ((date_value.month - 1) // 3) + 1


def _get_quarter_bounds(annee, trimestre):
    try:
        trimestre_int = int(trimestre)
    except (TypeError, ValueError):
        return None, None

    if trimestre_int < 1 or trimestre_int > 4:
        return None, None

    end_month = trimestre_int * 3
    return date(annee, 1, 1), date(annee, end_month, 1) + relativedelta(months=1, days=-1)


def _get_semester_bounds(annee, semestre):
    semestre_normalise = str(semestre or '').strip().upper()
    if semestre_normalise == 'S1':
        return date(annee, 1, 1), date(annee, 6, 30)
    if semestre_normalise == 'S2':
        return date(annee, 7, 1), date(annee, 12, 31)
    return None, None


def _get_due_period_bounds(period_start, period_end):
    if not period_start or not period_end:
        return None, None
    today = timezone.localdate()
    if period_start > today:
        return period_start, period_start
    return period_start, min(period_end, today)


def _recurring_quarter_start_date(annee, date_debut):
    """
    1er jour du trimestre calendaire recurrent pour une annee donnee.

    Le renouvellement d'une modalite de gestion a toujours lieu sur le meme
    mois calendaire chaque annee (celui de `date_debut`), le decalage introduit
    par un debut en cours d'annee (ex: septembre) se reproduit donc chaque
    annee suivante et n'est pas limite a l'annee de debut.
    """
    if not date_debut:
        return date(annee, 1, 1)
    quarter = _quarter_of_date(date_debut)
    start_month = (quarter - 1) * 3 + 1
    return date(annee, start_month, 1)


def _count_applicable_quarters_in_period(annee, date_debut_modalite, period_start, period_end, *, exigible=True):
    if not period_start or not period_end:
        return 0

    today = timezone.localdate()
    if exigible:
        if period_start > today:
            return 0
        period_end = min(period_end, today)

    if date_debut_modalite:
        if period_end < date_debut_modalite:
            return 0
        if annee < date_debut_modalite.year:
            return 0
        recurring_start = _recurring_quarter_start_date(annee, date_debut_modalite)
        period_start = max(period_start, recurring_start)
        if period_start > period_end:
            return 0

    first_quarter = _quarter_of_date(period_start)
    last_quarter = _quarter_of_date(period_end)
    return max(0, last_quarter - first_quarter + 1)


def _get_selected_trimestres_exigibles_depuis_date_debut(annee, date_debut, trimestre):
    if not trimestre:
        return _trimestres_exigibles_depuis_date_debut(annee, date_debut)

    try:
        trimestre_int = int(trimestre)
    except (TypeError, ValueError):
        return _trimestres_exigibles_depuis_date_debut(annee, date_debut)

    today = timezone.localdate()
    max_quarter_in_year = 4 if annee < today.year else (_quarter_of_date(today) if annee == today.year else 0)
    if trimestre_int > max_quarter_in_year:
        return 0

    if date_debut and annee < date_debut.year:
        return 0

    # Le trimestre de depart se reproduit chaque annee (le renouvellement a
    # toujours lieu sur le meme mois calendaire), pas seulement l'annee de debut.
    start_quarter = _quarter_of_date(date_debut) if date_debut else 1

    if trimestre_int < start_quarter:
        return 0

    return max(0, trimestre_int - start_quarter + 1)


def _get_selected_trimestres_planifies_depuis_date_debut(annee, date_debut, trimestre):
    if not trimestre:
        return _trimestres_planifies_depuis_date_debut(annee, date_debut)

    try:
        trimestre_int = int(trimestre)
    except (TypeError, ValueError):
        return _trimestres_planifies_depuis_date_debut(annee, date_debut)

    if date_debut and annee < date_debut.year:
        return 0

    # Le trimestre de depart se reproduit chaque annee (le renouvellement a
    # toujours lieu sur le meme mois calendaire), pas seulement l'annee de debut.
    start_quarter = _quarter_of_date(date_debut) if date_debut else 1

    if trimestre_int < start_quarter:
        return 0

    return max(0, trimestre_int - start_quarter + 1)


def _trimestres_exigibles_depuis_date_debut(annee, date_debut):
    """
    Calcule le nombre de trimestres exigibles pour une année donnée en tenant
    compte de la date de début de modalité de gestion.

    Le renouvellement a toujours lieu sur le même mois calendaire chaque
    année : un début en septembre (T3) donne 2 trimestres pour l'année de
    début ET pour chaque année suivante (les 2 tranches restantes étant
    payées d'avance et couvrant le premier semestre de l'année suivante).

    Exemple:
    - début 18/12/2024 -> 2024: 1 trimestre (T4), 2025 et années suivantes:
      toujours 1 trimestre (T4) par année.
    """
    if not date_debut:
        return _trimestres_exigibles(annee)

    today = timezone.localdate()

    if annee > today.year:
        return 0
    if annee < date_debut.year:
        return 0

    # Limite haute dans l'année demandée (4 pour année passée, trimestre courant pour année courante)
    max_quarter_in_year = 4 if annee < today.year else _quarter_of_date(today)

    start_quarter = _quarter_of_date(date_debut)

    if start_quarter > max_quarter_in_year:
        return 0

    return max_quarter_in_year - start_quarter + 1


def _trimestres_planifies_depuis_date_debut(annee, date_debut):
    """
    Nombre de trimestres qui devraient etre planifies sur l'annee complete,
    independamment de la date courante.

    Ce nombre reste constant chaque annee a partir de l'annee de debut car le
    renouvellement se reproduit toujours sur le meme mois calendaire (voir
    _trimestres_exigibles_depuis_date_debut).
    """
    if not date_debut:
        return 4
    if annee < date_debut.year:
        return 0

    start_quarter = _quarter_of_date(date_debut)
    return max(0, 4 - start_quarter + 1)


def _get_year_bounds(annee):
    return date(annee, 1, 1), date(annee, 12, 31)


def _as_local_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _latest_cut_events_by_point(points_eau, reference_date):
    """Dernier evenement Coupure/Remise connu au plus tard a la date donnee."""
    point_ids = [point.id for point in points_eau]
    latest_by_point = {}
    if not point_ids:
        return latest_by_point

    events = CoupureEau.objects.filter(
        point_eau_id__in=point_ids,
        date_evenement__lte=reference_date,
    ).order_by('point_eau_id', '-date_evenement', '-created_at')
    for event in events:
        latest_by_point.setdefault(str(event.point_eau_id), event)
    return latest_by_point


def _resolve_point_cut_state(point_eau, latest_event=None, reference_date=None):
    """Etat coupe a une date, avec l'historique comme source prioritaire."""
    if latest_event is not None:
        if latest_event.type_evenement == 'coupure':
            return True, _as_local_date(latest_event.date_evenement)
        return False, None

    legacy_cut_date = _as_local_date(
        getattr(point_eau, 'datearretbranchement', None)
    )
    if legacy_cut_date and (
        reference_date is None or legacy_cut_date <= reference_date
    ):
        return True, legacy_cut_date
    return False, None


def _get_collecte_forfaitaire_fiche_poste():
    from apps.employees.models_evaluation import FichePoste

    fiche_poste = FichePoste.objects.select_related('type_activites').filter(
        tache__iexact='Collecte des paiements forfaitaires'
    ).first()
    if fiche_poste:
        return fiche_poste

    return FichePoste.objects.select_related('type_activites').filter(
        tache__icontains='paiements forfaitaires'
    ).order_by('tache').first()


def _find_or_create_matching_forfaitaire_planning(point_eau, date_facture, employe=None):
    from apps.planning.models import Planning

    if not point_eau or not getattr(point_eau, 'ouvrage_id', None) or not date_facture:
        return None

    fiche_poste = _get_collecte_forfaitaire_fiche_poste()
    if not fiche_poste:
        return None

    existing_qs = Planning.objects.filter(
        date__date=date_facture,
        ouvrage_id=point_eau.ouvrage_id,
        fiche_poste=fiche_poste,
    ).order_by('created_at', 'date')

    planning = None
    if employe:
        planning = existing_qs.filter(employe=employe).first()
    if planning is None:
        planning = existing_qs.first()
    if planning is not None:
        return planning

    planning_dt = datetime.combine(date_facture, datetime.min.time())
    if timezone.is_naive(planning_dt) and timezone.is_aware(timezone.now()):
        planning_dt = timezone.make_aware(planning_dt, timezone.get_current_timezone())

    return Planning.objects.create(
        date=planning_dt,
        remarque=(
            "Collecte des paiements forfaitaires "
            f"(PE: {point_eau.code_point_eau or point_eau.id})"
        ),
        estvalide=False,
        statut='en_cours',
        employe=employe,
        ouvrage=point_eau.ouvrage,
        fiche_poste=fiche_poste,
        type_activite=fiche_poste.type_activites,
    )


def _get_paid_cut_alert(point_eau, paid_date, latest_event=None, reference_date=None):
    is_cut, date_arret = _resolve_point_cut_state(
        point_eau,
        latest_event=latest_event,
        reference_date=reference_date,
    )
    if not is_cut or not date_arret or not paid_date:
        return None
    if paid_date < date_arret:
        return None
    return {
        'date_arret': date_arret,
        'date_paiement': paid_date,
    }


def _get_stale_forfaitaire_cutoff_date():
    return timezone.localdate() - timedelta(days=365)


def _cleanup_stale_cut_forfait_points(ouvrage_ids=None):
    qs = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        datearretbranchement__isnull=False,
        datearretbranchement__date__lte=_get_stale_forfaitaire_cutoff_date()
    )
    if ouvrage_ids is not None:
        qs = qs.filter(ouvrage_id__in=ouvrage_ids)
    return qs.update(tarifforfaitaire=None, pourcentage_tarif=None)


# Photos stockées en base64 (jusqu'à plusieurs dizaines de Mo par ligne), jamais utilisées par
# ce module : à exclure de tout chargement, sinon jusqu'à 1,2 Go de RAM par appel d'API
# (select_related('point_eau') les recopiait pour chaque paiement).
DEFER_PHOTOS_PAIEMENT = ('point_eau__photos',)
DEFER_PHOTOS_PAIEMENT_PLANNING = ('point_eau__photos', 'planning__photo')


def _forfait_points_queryset():
    return PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        tarifforfaitaire__gt=0
    ).exclude(
        datearretbranchement__isnull=False,
        datearretbranchement__date__lte=_get_stale_forfaitaire_cutoff_date()
    ).defer('photos')


def _get_dashboard_reference_date(annee):
    """
    Date de référence du dashboard.
    - année passée: fin d'année
    - année en cours: aujourd'hui
    - année future: début d'année
    """
    today = timezone.localdate()
    if annee < today.year:
        return date(annee, 12, 31)
    if annee > today.year:
        return date(annee, 1, 1)
    return today


def _filter_modalites_dashboard_scope(qs, annee):
    """
    Ne conserve que les modalités actives à la date de référence du dashboard.
    """
    reference_date = _get_dashboard_reference_date(annee)
    return qs.filter(
        Q(date_debut__isnull=True) | Q(date_debut__lte=reference_date)
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
    )


def _get_ouvrages_ids_by_organisation_for_annee(gestionnaire_ids, annee, modalites_paiement=None):
    """
    IDs d'ouvrages gérés avec une modalité encore active à la date
    de référence du dashboard.
    """
    if gestionnaire_ids is None:
        modalites_qs = ModaliteGestion.objects.all()
    elif not gestionnaire_ids:
        return set()

    else:
        modalites_qs = ModaliteGestion.objects.filter(gestionnaire_id__in=gestionnaire_ids)

    modalites_qs = _filter_modalites_dashboard_scope(modalites_qs, annee)
    if modalites_paiement:
        modalites_qs = modalites_qs.filter(modalitepaiement__in=modalites_paiement)

    return set(
        modalites_qs
        .values_list('ouvrage_id', flat=True)
        .distinct()
    )


def _get_modalite_active_map(ouvrage_ids, annee=None, gestionnaire_ids=None, modalites_paiement=None):
    """
    Map ouvrage_id -> ModaliteGestion pertinente.
    - Si annee est fournie: modalite active à la date de référence du dashboard.
    - Sinon: modalite active aujourd'hui.
    """
    qs = ModaliteGestion.objects.filter(
        ouvrage_id__in=ouvrage_ids
    )

    if gestionnaire_ids is not None:
        if not gestionnaire_ids:
            return {}
        qs = qs.filter(gestionnaire_id__in=gestionnaire_ids)

    if annee is not None:
        qs = _filter_modalites_dashboard_scope(qs, annee)
    else:
        qs = filter_current_modalites(qs)

    if modalites_paiement:
        qs = qs.filter(modalitepaiement__in=modalites_paiement)

    qs = qs.order_by('ouvrage_id', 'date_debut')

    modalite_map = {}
    for modalite in qs:
        modalite_map.setdefault(modalite.ouvrage_id, modalite)
    return modalite_map


def _resolve_gestionnaire_scope(accessible_gestionnaire_ids, requested_organisation_id):
    """
    Construit le scope gestionnaire final à partir des droits utilisateur et
    du filtre organisation demandé.
    """
    requested_id = (requested_organisation_id or '').strip()
    if requested_id == 'all':
        requested_id = ''

    # Superuser: pas de restriction, sauf si une organisation est explicitement choisie
    if accessible_gestionnaire_ids is None:
        if requested_id:
            return [requested_id], requested_id
        return None, ''

    accessible_ids = [str(org_id) for org_id in accessible_gestionnaire_ids]
    if not requested_id:
        return accessible_ids, ''

    if requested_id in accessible_ids:
        return [requested_id], requested_id

    # Filtre invalide/hors scope: on revient au scope autorisé par défaut
    return accessible_ids, ''


def _get_organisations_filtre_queryset(accessible_gestionnaire_ids):
    qs = Organisation.objects.filter(
        type_organisation=Organisation.TYPE_GESTIONNAIRE
    ).order_by('nom_organisation')

    if accessible_gestionnaire_ids is None:
        return qs

    accessible_ids = [str(org_id) for org_id in accessible_gestionnaire_ids]
    if not accessible_ids:
        return Organisation.objects.none()

    return qs.filter(id__in=accessible_ids)


def _get_scoped_forfaitaire_ouvrage_ids(user, annee=None, gestionnaire_ids=None, apply_responsable_scope=True):
    if annee is None:
        annee = timezone.localdate().year

    if gestionnaire_ids is None:
        accessible_gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
        gestionnaire_ids, _ = _resolve_gestionnaire_scope(
            accessible_gestionnaire_ids,
            '',
        )

    ouvrage_ids = _get_ouvrages_ids_by_organisation_for_annee(
        gestionnaire_ids,
        annee,
        modalites_paiement=FORFAITAIRE_MODALITES_PAIEMENT,
    )
    if not apply_responsable_scope:
        return ouvrage_ids
    return apply_user_responsable_ouvrage_scope(
        ouvrage_ids,
        user,
        allow_same_base_support_roles=True,
    )


def _get_forfaitaire_geo_querysets(ouvrage_ids):
    points_eau_scope = PointEau.objects.filter(ouvrage_id__in=ouvrage_ids)

    region_ids = points_eau_scope.values_list(
        'parcelle__village__fokontany__commune__district__region_id',
        flat=True,
    ).distinct()
    district_ids = points_eau_scope.values_list(
        'parcelle__village__fokontany__commune__district_id',
        flat=True,
    ).distinct()
    commune_ids = points_eau_scope.values_list(
        'parcelle__village__fokontany__commune_id',
        flat=True,
    ).distinct()

    regions = Region.objects.filter(id__in=region_ids).order_by('nom_region')
    districts_all = District.objects.filter(id__in=district_ids).order_by('nom_district')
    communes_all = Commune.objects.filter(id__in=commune_ids).select_related(
        'district__region'
    ).order_by('nom_commune')
    return regions, districts_all, communes_all


def _apply_forfaitaire_point_eau_geo_filters(points_qs, filter_region='', filter_district='', filter_commune=''):
    if filter_commune:
        points_qs = points_qs.filter(
            parcelle__village__fokontany__commune_id=filter_commune
        )
    elif filter_district:
        points_qs = points_qs.filter(
            parcelle__village__fokontany__commune__district_id=filter_district
        )
    elif filter_region:
        points_qs = points_qs.filter(
            parcelle__village__fokontany__commune__district__region_id=filter_region
        )
    return points_qs


def _resolve_detail_page_size(raw_value, export_full=False):
    if export_full or str(raw_value or '').strip().lower() == 'all':
        return None

    try:
        page_size = int(raw_value)
    except (TypeError, ValueError):
        page_size = DETAIL_DEFAULT_PAGE_SIZE

    return max(10, min(page_size, DETAIL_MAX_PAGE_SIZE))


def _paginate_page_numbers(page_obj, radius=2):
    if not page_obj:
        return []

    start = max(1, page_obj.number - radius)
    end = min(page_obj.paginator.num_pages, page_obj.number + radius)
    return list(range(start, end + 1))

@login_required
def dashboard_paiements_forfaitaire(request):
    """
    Dashboard d'analyse des paiements forfaitaires

    Fonctionnalités :
    - Filtrage par année, district, commune, ouvrage
    - Calcul des montants à collecter avec décotes pour coupures
    - Taux de recouvrement par ouvrage
    - Graphiques mensuels
    - Détails par point d'eau
    """

    # ========== FILTRES ==========
    filter_annee = request.GET.get('annee', str(datetime.now().year))
    filter_region = request.GET.get('region', '')
    filter_district = request.GET.get('district', '')
    filter_commune = request.GET.get('commune', '')
    filter_ouvrage = request.GET.get('ouvrage', '')
    filter_employe = request.GET.get('employe', '')
    filter_organisation = request.GET.get('organisation', '')
    filter_taux = request.GET.get('taux', '')
    filter_taux_forfaitaire = request.GET.get('taux_forfaitaire', '')
    filter_trimestre = request.GET.get('trimestre', '')
    filter_semestre = request.GET.get('semestre', '').strip().upper()
    filter_non_pointe = request.GET.get('non_pointe', '')
    filter_explication = request.GET.get('explication', '')
    filter_echu = request.GET.get('echu', '')
    filter_statut_echu = request.GET.get('statut_echu', '')
    score_ecart_filter = str(request.GET.get('score_ecart', '') or '').strip().lower()
    show_only_score_gap = score_ecart_filter in {'1', 'true', 'on', 'yes'}
    if filter_statut_echu not in {'non_paye_mois_passes', 'non_paye_mois_en_cours'}:
        filter_statut_echu = ''
    detail_page = request.GET.get('detail_page', '1')
    export_full = request.GET.get('export_full') == '1'
    detail_page_size = _resolve_detail_page_size(
        request.GET.get('detail_page_size', ''),
        export_full=export_full,
    )

    try:
        annee = int(filter_annee)
    except:
        annee = datetime.now().year

    trimestre_debut, trimestre_fin = _get_quarter_bounds(annee, filter_trimestre)
    if filter_trimestre and not trimestre_debut:
        filter_trimestre = ''
    semestre_debut, semestre_fin = _get_semester_bounds(annee, filter_semestre)
    if filter_semestre and not semestre_debut:
        filter_semestre = ''
    if semestre_debut and semestre_fin:
        filter_trimestre = ''
        trimestre_debut = trimestre_fin = None
    semestre_exigible_debut, semestre_exigible_fin = _get_due_period_bounds(
        semestre_debut,
        semestre_fin,
    )

    # Récupérer le scope gestionnaire de l'utilisateur
    organisation_user = get_user_organisation(request.user)
    accessible_gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    gestionnaire_ids, filter_organisation = _resolve_gestionnaire_scope(
        accessible_gestionnaire_ids,
        filter_organisation
    )
    organisations = _get_organisations_filtre_queryset(accessible_gestionnaire_ids)

    # ========== RÉCUPÉRATION DES DONNÉES DIAMEX (compte 748411) ==========
    transactions_qs = BaseDiameX.objects.filter(
        compte_code='748411',  # Paiement forfaitaire uniquement
        date_m__year=annee
    )
    if trimestre_debut and trimestre_fin:
        transactions_qs = transactions_qs.filter(date_m__gte=trimestre_debut, date_m__lte=trimestre_fin)
    elif semestre_debut and semestre_fin:
        transactions_qs = transactions_qs.filter(date_m__gte=semestre_debut, date_m__lte=semestre_fin)

    # Filtrer sur les modalités encore actives à la date de référence.
    ouvrages_org = _get_scoped_forfaitaire_ouvrage_ids(
        request.user,
        annee=annee,
        gestionnaire_ids=gestionnaire_ids,
    )
    ouvrages_org_filter_scope = set(ouvrages_org)
    employes_responsables, ouvrages_org = resolve_dashboard_employee_filter(
        ouvrages_org,
        filter_employe,
    )
    if filter_employe and not any(
        str(option.get('id', '')) == str(filter_employe)
        for option in employes_responsables
    ):
        filter_employe = ''

    # On ne peut pas filtrer directement, on filtrera apres extraction
    transactions_list = list(transactions_qs)

    # ========== EXTRACTION DES OUVRAGES DEPUIS LES DESCRIPTIONS ==========
    transactions_avec_ouvrage = []
    # Transactions dont l'ouvrage n'a pas pu etre identifie depuis le libelle
    # (faute de frappe operateur, orthographe differente, etc.) : elles ne sont
    # comptees nulle part ailleurs, il faut donc les signaler explicitement.
    transactions_non_appariees = []
    from apps.accounting.resolution_memoire import resolution_memoire

    with resolution_memoire():
     for trans in transactions_list:
        extraction = extraire_ouvrage_et_mois_generique(trans.description or '', '748411')
        mois_extraction = extraction.get('mois')
        if filter_semestre:
            mois_reference = mois_extraction or (trans.date_m.month if trans.date_m else None)
            if not mois_reference or not (semestre_debut.month <= mois_reference <= semestre_fin.month):
                continue
        elif filter_trimestre:
            if mois_extraction:
                if _quarter_of_date(date(annee, mois_extraction, 1)) != int(filter_trimestre):
                    continue
            elif trans.date_m and _quarter_of_date(trans.date_m) != int(filter_trimestre):
                continue

        if extraction['ouvrage_obj']:
            # Filtrer par organisation si définie
            if extraction['ouvrage_obj'].id not in ouvrages_org:
                continue

            transactions_avec_ouvrage.append({
                'transaction': trans,
                'ouvrage': extraction['ouvrage_obj'],
                'montant': Decimal(str(trans.montant_in)) if trans.montant_in else Decimal('0'),
                'mois': mois_extraction,
            })
        else:
            transactions_non_appariees.append({
                'id_access': trans.id_access,
                'prog': trans.prog or '',
                'date_rec': trans.date_rec,
                'montant': float(trans.montant_in or 0),
                'description': trans.description or '',
                'raison': "Ouvrage introuvable (vérifier l'orthographe dans le libellé)",
            })

    transactions_non_appariees.sort(key=lambda item: item['date_rec'] or date.min, reverse=True)
    montant_total_non_appariees = sum(
        (Decimal(str(item['montant'])) for item in transactions_non_appariees),
        Decimal('0')
    )

    pointed_couples_global = {
        (str(numero or '').strip(), str(base or '').strip())
        for numero, base in PaiementForfaitaire.objects.filter(
            point_eau__ouvrage_id__in=ouvrages_org
        ).exclude(
            numeroDiameX__isnull=True
        ).exclude(
            baseDiameX__isnull=True
        ).values_list('numeroDiameX', 'baseDiameX')
        if str(numero or '').strip() and str(base or '').strip()
    }
    transactions_stats_by_ouvrage = defaultdict(lambda: {
        'montant_collecte': Decimal('0'),
        'montant_collecte_non_pointe': Decimal('0'),
        'nb_lignes_diamex_non_pointe': 0,
    })
    ouvrages_non_pointes_ids = set()
    for tx in transactions_avec_ouvrage:
        ouvrage_obj = tx['ouvrage']
        ouvrage_id = ouvrage_obj.id
        montant_trans = Decimal(str(tx['montant'] or 0))
        tx_stats = transactions_stats_by_ouvrage[ouvrage_id]
        tx_stats['montant_collecte'] += montant_trans

        numero_diamex = str(getattr(tx['transaction'], 'id_access', '') or '').strip()
        base_diamex = str(getattr(tx['transaction'], 'prog', '') or '').strip()
        is_pointed = bool(numero_diamex and base_diamex and (numero_diamex, base_diamex) in pointed_couples_global)
        if not is_pointed:
            tx_stats['montant_collecte_non_pointe'] += montant_trans
            tx_stats['nb_lignes_diamex_non_pointe'] += 1
            ouvrages_non_pointes_ids.add(ouvrage_id)

    # ========== CALCUL DES MONTANTS PREVUS/REALISES PAR OUVRAGE ==========
    # Le "paiement forfaitaire" est rattaché à l'année/mois de date_facture.
    paiements_forfaitaires_planifies_qs = PaiementForfaitaire.objects.filter(
        date_facture__year=annee
    ).select_related(
        'point_eau',
        'point_eau__ouvrage'
    )
    paiements_forfaitaires_planifies_qs = paiements_forfaitaires_planifies_qs.filter(
        point_eau__ouvrage_id__in=ouvrages_org
    )
    if trimestre_debut and trimestre_fin:
        paiements_forfaitaires_planifies_qs = paiements_forfaitaires_planifies_qs.filter(
            date_facture__gte=trimestre_debut,
            date_facture__lte=trimestre_fin,
        )
    elif semestre_debut and semestre_fin:
        paiements_forfaitaires_planifies_qs = paiements_forfaitaires_planifies_qs.filter(
            date_facture__gte=semestre_debut,
            date_facture__lte=semestre_fin,
        )

    nb_tranches_planifiees_par_point_eau = defaultdict(int)
    # Seul l'identifiant du point est utile : pas d'objets complets (ni jointures, ni photos)
    for point_eau_id in paiements_forfaitaires_planifies_qs.order_by().values_list('point_eau_id', flat=True):
        if point_eau_id:
            nb_tranches_planifiees_par_point_eau[point_eau_id] += 1

    paiements_forfaitaires_qs = PaiementForfaitaire.objects.filter(
        date_facture__year=annee,
        date_facture__lte=timezone.localdate()
    ).select_related(
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune__district__region'
    ).defer(*DEFER_PHOTOS_PAIEMENT)

    paiements_forfaitaires_qs = paiements_forfaitaires_qs.filter(
        point_eau__ouvrage_id__in=ouvrages_org
    )
    if trimestre_debut and trimestre_fin:
        paiements_forfaitaires_qs = paiements_forfaitaires_qs.filter(
            date_facture__gte=trimestre_debut,
            date_facture__lte=trimestre_fin,
        )
    elif semestre_debut and semestre_fin:
        paiements_forfaitaires_qs = paiements_forfaitaires_qs.filter(
            date_facture__gte=semestre_debut,
            date_facture__lte=semestre_fin,
        )

    paiements_par_ouvrage = defaultdict(list)
    paiements_par_point_eau = defaultdict(list)
    montant_prevu_par_ouvrage = defaultdict(lambda: Decimal('0'))
    montant_prevu_mensuel_par_ouvrage = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
    latest_paid_forfait_by_point_eau = {}
    ouvrages_avec_facture_echue = set()
    today = timezone.localdate()

    for paiement in paiements_forfaitaires_qs:
        ouvrage_pf = paiement.point_eau.ouvrage if paiement.point_eau else None
        if not ouvrage_pf:
            continue
        montant = Decimal(str(paiement.montant or 0))
        paiements_par_ouvrage[ouvrage_pf.id].append(paiement)
        if paiement.point_eau_id:
            paiements_par_point_eau[paiement.point_eau_id].append(paiement)
        montant_prevu_par_ouvrage[ouvrage_pf.id] += montant
        if paiement.date_facture:
            montant_prevu_mensuel_par_ouvrage[ouvrage_pf.id][paiement.date_facture.month] += montant

        paid_date = paiement.effective_payment_date
        if paiement.point_eau_id and paiement.est_paye and paid_date:
            current_latest_paid = latest_paid_forfait_by_point_eau.get(paiement.point_eau_id)
            if current_latest_paid is None or paid_date > current_latest_paid:
                latest_paid_forfait_by_point_eau[paiement.point_eau_id] = paid_date

        # Facture échue (prépayé): impayée et date_facture atteinte.
        est_paye = paiement.est_paye
        if (not est_paye) and paiement.date_facture and paiement.date_facture <= today:
            ouvrages_avec_facture_echue.add(ouvrage_pf.id)

    total_lignes_diamex_non_pointe_global = 0

    # Récupérer tous les ouvrages concernés:
    # - réalisé DiameX
    # - paiement forfaitaire facturé
    # - points d'eau forfaitaires (même sans facture/écriture DiameX)
    ouvrages_ids = set([t['ouvrage'].id for t in transactions_avec_ouvrage]) | set(montant_prevu_par_ouvrage.keys())

    _cleanup_stale_cut_forfait_points(ouvrage_ids=ouvrages_org)
    points_eau_forfait_qs = _forfait_points_queryset()
    points_eau_forfait_qs = points_eau_forfait_qs.filter(ouvrage_id__in=ouvrages_org)
    ouvrages_ids |= set(points_eau_forfait_qs.values_list('ouvrage_id', flat=True).distinct())
    ouvrages_ids &= ouvrages_org

    # Appliquer les filtres géographiques
    ouvrages_qs = Ouvrage.objects.filter(id__in=ouvrages_ids)

    if filter_ouvrage:
        ouvrages_qs = ouvrages_qs.filter(id=filter_ouvrage)

    if filter_commune:
        # Via PointEau → Parcelle → Village → Fokontany → Commune
        points_eau_commune = PointEau.objects.filter(
            parcelle__village__fokontany__commune_id=filter_commune
        ).values_list('ouvrage_id', flat=True).distinct()
        ouvrages_qs = ouvrages_qs.filter(id__in=points_eau_commune)

    if filter_district:
        # Via PointEau → Parcelle → Village → Fokontany → Commune → District
        points_eau_district = PointEau.objects.filter(
            parcelle__village__fokontany__commune__district_id=filter_district
        ).values_list('ouvrage_id', flat=True).distinct()
        ouvrages_qs = ouvrages_qs.filter(id__in=points_eau_district)
        
    if filter_region:
        # Via PointEau → Parcelle → Village → Fokontany → Commune → District → Region
        points_eau_region = PointEau.objects.filter(
            parcelle__village__fokontany__commune__district__region_id=filter_region
        ).values_list('ouvrage_id', flat=True).distinct()
        ouvrages_qs = ouvrages_qs.filter(id__in=points_eau_region)

    score_ouvrage_ids = set(ouvrages_qs.values_list('id', flat=True))

    if filter_non_pointe == '1':
        ouvrages_qs = ouvrages_qs.filter(id__in=ouvrages_non_pointes_ids)

    ouvrages_filtre = list(ouvrages_qs)

    # ========== CALCUL PAR OUVRAGE ==========
    modalite_active_map = _get_modalite_active_map(
        [o.id for o in ouvrages_filtre],
        annee=annee,
        gestionnaire_ids=gestionnaire_ids,
        modalites_paiement=FORFAITAIRE_MODALITES_PAIEMENT
    )

    recouvrement_par_ouvrage = {}
    points_eau_par_ouvrage_id = {}

    for ouvrage in ouvrages_filtre:
        ouvrage_id = str(ouvrage.id)
        modalite_active = modalite_active_map.get(ouvrage.id)
        trimestres_exigibles = _trimestres_exigibles_depuis_date_debut(
            annee,
            getattr(modalite_active, 'date_debut', None)
        )
        if semestre_debut and semestre_fin:
            trimestres_exigibles = _count_applicable_quarters_in_period(
                annee,
                getattr(modalite_active, 'date_debut', None),
                semestre_debut,
                semestre_fin,
                exigible=True,
            )

        # Récupérer les points d'eau de cet ouvrage
        points_eau = list(_apply_forfaitaire_point_eau_geo_filters(
            _forfait_points_queryset().filter(ouvrage_id=ouvrage.id),
            filter_region=filter_region,
            filter_district=filter_district,
            filter_commune=filter_commune,
        ).select_related('ouvrage', 'parcelle__village__fokontany__commune__district'))
        points_eau_par_ouvrage_id[ouvrage.id] = points_eau
        reference_date = _get_dashboard_reference_date(annee)
        latest_cut_events = _latest_cut_events_by_point(points_eau, reference_date)

        # Montant prévu = tarif trimestriel x trimestres exigibles à date.
        montant_brut_total = Decimal('0')
        total_points_eau = 0
        points_eau_coupes = 0
        points_eau_paid_cut_alerts = []

        for pe in points_eau:
            total_points_eau += 1
            tarif = tarif_pour_annee(pe, annee)
            montant_brut_total += tarif * Decimal(str(trimestres_exigibles))

            # Vérifier si ce point d'eau a des coupures
            latest_cut_event = latest_cut_events.get(str(pe.id))
            is_cut, _cut_date = _resolve_point_cut_state(
                pe,
                latest_event=latest_cut_event,
                reference_date=reference_date,
            )
            if is_cut:
                points_eau_coupes += 1

            paid_cut_alert = _get_paid_cut_alert(
                pe,
                latest_paid_forfait_by_point_eau.get(pe.id),
                latest_event=latest_cut_event,
                reference_date=reference_date,
            )
            if paid_cut_alert:
                points_eau_paid_cut_alerts.append({
                    'point_eau_id': str(pe.id),
                    'point_eau_nom': pe.nomabonne or pe.code_point_eau or '-',
                    'date_arret': paid_cut_alert['date_arret'].strftime('%d/%m/%Y'),
                    'date_paiement': paid_cut_alert['date_paiement'].strftime('%d/%m/%Y'),
                })

        # Le prévu vient déjà de la table de facturation forfaitaire.
        decote_totale = calculer_decote_coupures(
            points_eau,
            annee,
            periode_debut=semestre_exigible_debut,
            periode_fin=semestre_exigible_fin,
        )
        montant_a_collecter = montant_brut_total - decote_totale
        if montant_a_collecter < 0:
            montant_a_collecter = Decimal('0')

        montant_paiement_forfaitaire = montant_prevu_par_ouvrage.get(ouvrage.id, Decimal('0'))
        montant_forfaitaire_non_pointe = Decimal('0')
        nb_lignes_forfaitaires_non_pointe = 0
        # Suivi rapide : factures encaissées par la caissière (pointées ou non).
        # Calculé sur les factures (PaiementForfaitaire) et non sur les écritures DiameX,
        # donc sans double comptage quand la compta a déjà saisi mais pas encore pointé.
        montant_encaisse = Decimal('0')
        montant_encaisse_non_pointe = Decimal('0')
        nb_encaisse_non_pointe = 0
        for paiement in paiements_par_ouvrage.get(ouvrage.id, []):
            numero_diamex = str(getattr(paiement, 'numeroDiameX', '') or '').strip()
            base_diamex = str(getattr(paiement, 'baseDiameX', '') or '').strip()
            is_pointed_forfaitaire = bool(numero_diamex and base_diamex)
            if not is_pointed_forfaitaire:
                montant_forfaitaire_non_pointe += Decimal(str(paiement.montant or 0))
                nb_lignes_forfaitaires_non_pointe += 1
            if paiement.est_encaisse:
                montant_encaisse += Decimal(str(paiement.montant or 0))
                if paiement.est_encaisse_non_pointe:
                    montant_encaisse_non_pointe += Decimal(str(paiement.montant or 0))
                    nb_encaisse_non_pointe += 1

        # Montant collecté depuis DiameX
        tx_stats = transactions_stats_by_ouvrage.get(ouvrage.id, {})
        montant_collecte = tx_stats.get('montant_collecte', Decimal('0'))
        montant_collecte_non_pointe = tx_stats.get('montant_collecte_non_pointe', Decimal('0'))
        nb_lignes_diamex_non_pointe = tx_stats.get('nb_lignes_diamex_non_pointe', 0)

        # Taux = Paye / Montant a collecter (apres decote).
        has_taux = montant_a_collecter > 0
        taux = int((montant_collecte / montant_a_collecter) * 100) if has_taux else 0

        # Taux alternatif = Paye / Paiement forfaitaire facture.
        has_taux_paye_sur_forfaitaire = montant_paiement_forfaitaire > 0
        taux_paye_sur_forfaitaire = int((montant_collecte / montant_paiement_forfaitaire) * 100) if has_taux_paye_sur_forfaitaire else 0

        if filter_taux == 'gt100':
            if (not has_taux) or taux <= 100:
                continue
        if filter_taux == '100':
            if (not has_taux) or taux != 100:
                continue
        if filter_taux == 'lt100':
            if (not has_taux) or taux >= 100:
                continue
        if filter_taux_forfaitaire == 'gt100':
            if (not has_taux_paye_sur_forfaitaire) or taux_paye_sur_forfaitaire <= 100:
                continue
        if filter_taux_forfaitaire == '100':
            if (not has_taux_paye_sur_forfaitaire) or taux_paye_sur_forfaitaire != 100:
                continue
        if filter_taux_forfaitaire == 'lt100':
            if (not has_taux_paye_sur_forfaitaire) or taux_paye_sur_forfaitaire >= 100:
                continue

        has_facture_echue = ouvrage.id in ouvrages_avec_facture_echue
        if filter_echu == '1' and not has_facture_echue:
            continue
        if filter_non_pointe == '1' and nb_lignes_diamex_non_pointe <= 0:
            continue

        total_lignes_diamex_non_pointe_global += nb_lignes_diamex_non_pointe

        # Extraire district et commune depuis le premier point d'eau
        district_nom = None
        commune_nom = None
        if points_eau:
            premier_pe = points_eau[0]
            if premier_pe.parcelle and premier_pe.parcelle.village:
                village = premier_pe.parcelle.village
                if village.fokontany and village.fokontany.commune:
                    commune = village.fokontany.commune
                    commune_nom = commune.nom_commune
                    if commune.district:
                        district_nom = commune.district.nom_district

        date_debut_gestion = getattr(modalite_active, 'date_debut', None)

        recouvrement_par_ouvrage[ouvrage_id] = {
            'ouvrage': ouvrage,
            'ouvrage_nom': ouvrage.nom_ouvrage,
            'ouvrage_id': ouvrage_id,
            'district_nom': district_nom or 'Sans district',
            'commune_nom': commune_nom or 'Sans commune',
            'date_debut_gestion': date_debut_gestion,
            'date_debut_gestion_annee_courante': bool(date_debut_gestion and date_debut_gestion.year == annee),
            'est_saisonnier': ouvrage.saisonnier,
            'nb_points_eau': total_points_eau,
            'nb_points_eau_coupes': points_eau_coupes,
            'nb_points_eau_payes_coupes': len(points_eau_paid_cut_alerts),
            'has_paid_cut_alert': bool(points_eau_paid_cut_alerts),
            'paid_cut_alert_points': points_eau_paid_cut_alerts,
            'montant_brut': float(montant_brut_total),
            'decote_totale': float(decote_totale),
            'montant_a_collecter': float(montant_a_collecter),
            'montant_paiement_forfaitaire': float(montant_paiement_forfaitaire),
            'montant_forfaitaire_non_pointe': float(montant_forfaitaire_non_pointe),
            'nb_lignes_forfaitaires_non_pointe': nb_lignes_forfaitaires_non_pointe,
            'montant_encaisse': float(montant_encaisse),
            'montant_encaisse_non_pointe': float(montant_encaisse_non_pointe),
            'nb_encaisse_non_pointe': nb_encaisse_non_pointe,
            'taux_encaisse': int((montant_encaisse / montant_paiement_forfaitaire) * 100) if montant_paiement_forfaitaire > 0 else 0,
            'montant_collecte': float(montant_collecte),
            'montant_collecte_non_pointe': float(montant_collecte_non_pointe),
            'nb_lignes_diamex_non_pointe': nb_lignes_diamex_non_pointe,
            'ecart': float(montant_a_collecter - montant_collecte),
            'taux': taux,
            'has_taux': has_taux,
            'taux_paye_sur_forfaitaire': taux_paye_sur_forfaitaire,
            'has_taux_paye_sur_forfaitaire': has_taux_paye_sur_forfaitaire,
            'has_facture_echue': has_facture_echue
        }

    # ========== EXPLICATIONS NARRATIVES ==========
    explications_qs = ExplicationPaiementForfaitaire.objects.filter(
        annee=annee,
        ouvrage_id__in=[o.id for o in ouvrages_filtre]
    )
    explications_map = {str(e.ouvrage_id): e for e in explications_qs}

    for item in recouvrement_par_ouvrage.values():
        exp = explications_map.get(item['ouvrage_id'])
        item['explication'] = exp.explication if exp else ''
        item['has_explication'] = bool(exp and exp.explication)

    if filter_explication in ['avec', 'sans']:
        keep_with = filter_explication == 'avec'
        recouvrement_par_ouvrage = {
            k: v for k, v in recouvrement_par_ouvrage.items()
            if (v['has_explication'] == keep_with)
        }

    # ========== STATISTIQUES GLOBALES ==========
    nb_ouvrages_total = len(recouvrement_par_ouvrage)
    nb_ouvrages_gt100 = sum(1 for d in recouvrement_par_ouvrage.values() if d.get('has_taux') and d['taux'] > 100)
    nb_ouvrages_eq100 = sum(1 for d in recouvrement_par_ouvrage.values() if d.get('has_taux') and d['taux'] == 100)
    nb_ouvrages_lt100 = sum(1 for d in recouvrement_par_ouvrage.values() if d.get('has_taux') and d['taux'] < 100)
    nb_points_eau_total = sum(d.get('nb_points_eau', 0) for d in recouvrement_par_ouvrage.values())
    nb_points_eau_coupes_total = sum(d.get('nb_points_eau_coupes', 0) for d in recouvrement_par_ouvrage.values())
    nb_points_eau_payes_echus_ge_100 = 0
    nb_points_eau_payes_echus_lt_100 = 0
    nb_points_eau_non_payes_echus = 0
    nb_points_eau_payes_echus_lt_100_mois_passes = 0
    nb_points_eau_payes_echus_lt_100_mois_en_cours = 0
    nb_points_eau_non_payes_echus_mois_passes = 0
    nb_points_eau_non_payes_echus_mois_en_cours = 0
    ouvrages_non_payes_echus_mois_passes = set()
    ouvrages_non_payes_echus_mois_en_cours = set()
    nb_ouvrages_paid_cut_alert = sum(1 for d in recouvrement_par_ouvrage.values() if d.get('has_paid_cut_alert'))
    nb_points_eau_paid_cut_alert = sum(d.get('nb_points_eau_payes_coupes', 0) for d in recouvrement_par_ouvrage.values())
    nb_points_eau_tranches_ok = 0
    nb_points_eau_tranches_lt = 0
    nb_points_eau_tranches_gt = 0

    for ouvrage in ouvrages_filtre:
        modalite_active = modalite_active_map.get(ouvrage.id)
        trimestres_planifies_attendus = _trimestres_planifies_depuis_date_debut(
            annee,
            getattr(modalite_active, 'date_debut', None)
        )
        if filter_trimestre:
            trimestres_planifies_attendus = _get_selected_trimestres_planifies_depuis_date_debut(
                annee,
                getattr(modalite_active, 'date_debut', None),
                filter_trimestre,
            )
        elif semestre_debut and semestre_fin:
            trimestres_planifies_attendus = _count_applicable_quarters_in_period(
                annee,
                getattr(modalite_active, 'date_debut', None),
                semestre_debut,
                semestre_fin,
                exigible=False,
            )
        points_eau_ids = _apply_forfaitaire_point_eau_geo_filters(
            _forfait_points_queryset().filter(ouvrage_id=ouvrage.id),
            filter_region=filter_region,
            filter_district=filter_district,
            filter_commune=filter_commune,
        ).values_list('id', flat=True)

        for point_eau_id in points_eau_ids:
            nb_planifie = nb_tranches_planifiees_par_point_eau.get(point_eau_id, 0)
            if nb_planifie == trimestres_planifies_attendus:
                nb_points_eau_tranches_ok += 1
            elif nb_planifie < trimestres_planifies_attendus:
                nb_points_eau_tranches_lt += 1
            else:
                nb_points_eau_tranches_gt += 1

    def _pct_ouvrages(count):
        if nb_ouvrages_total <= 0:
            return 0.0
        return round((count / nb_ouvrages_total) * 100, 1)

    def _pct_points_eau(count):
        if nb_points_eau_total <= 0:
            return 0.0
        return round((count / nb_points_eau_total) * 100, 1)

    total_a_collecter_global = sum([d['montant_a_collecter'] for d in recouvrement_par_ouvrage.values()])
    total_paiement_forfaitaire_global = sum([d['montant_paiement_forfaitaire'] for d in recouvrement_par_ouvrage.values()])
    total_collecte_global = sum([d['montant_collecte'] for d in recouvrement_par_ouvrage.values()])
    total_collecte_non_pointe_global = sum([d['montant_collecte_non_pointe'] for d in recouvrement_par_ouvrage.values()])
    total_encaisse_global = sum([d['montant_encaisse'] for d in recouvrement_par_ouvrage.values()])
    total_encaisse_non_pointe_global = sum([d['montant_encaisse_non_pointe'] for d in recouvrement_par_ouvrage.values()])
    nb_encaisse_non_pointe_global = sum([d['nb_encaisse_non_pointe'] for d in recouvrement_par_ouvrage.values()])
    taux_encaisse_global = int((total_encaisse_global / total_paiement_forfaitaire_global) * 100) if total_paiement_forfaitaire_global > 0 else 0
    ecart_a_collecter_global = total_a_collecter_global - total_collecte_global
    ecart_collecte_vs_forfaitaire_global = total_paiement_forfaitaire_global - total_collecte_global

    has_taux_recouvrement_global = total_a_collecter_global > 0
    if has_taux_recouvrement_global:
        taux_recouvrement_global = int((total_collecte_global / total_a_collecter_global) * 100)
    else:
        taux_recouvrement_global = 0

    has_taux_paye_sur_forfaitaire_global = total_paiement_forfaitaire_global > 0
    if has_taux_paye_sur_forfaitaire_global:
        taux_paye_sur_forfaitaire_global = int((total_collecte_global / total_paiement_forfaitaire_global) * 100)
    else:
        taux_paye_sur_forfaitaire_global = 0

    # ========== RECOUVREMENT REEL PAR PERIODE (MOIS PASSES / MOIS EN COURS) ==========
    # Meme logique que sur le tableau des factures pointees (dashboard_payments_flat) :
    # base sur les factures reellement emises (PaiementForfaitaire) et le montant
    # reellement collecte (DiameX, via le mois de facturation extrait du libelle),
    # decoupes selon le mois de facturation vs le mois calendaire courant.
    debut_mois_courant_forfait = today.replace(day=1)
    ouvrages_ids_filtres_forfait = {data['ouvrage'].id for data in recouvrement_par_ouvrage.values()}

    montant_prevu_mois_passes_forfait = Decimal('0')
    montant_prevu_mois_en_cours_forfait = Decimal('0')
    # Encaissé par la caissière, ventilé avec la même règle (date_facture) que le prévu
    encaisse_periode_forfait = {
        'passes': {'total': Decimal('0'), 'non_pointe': Decimal('0'), 'nb_non_pointe': 0},
        'en_cours': {'total': Decimal('0'), 'non_pointe': Decimal('0'), 'nb_non_pointe': 0},
    }
    encaisse_details_forfait = []  # lignes pour les modales des tuiles Encaissé / Écart
    for ouvrage_id_int in ouvrages_ids_filtres_forfait:
        for paiement in paiements_par_ouvrage.get(ouvrage_id_int, []):
            if not paiement.date_facture:
                continue
            montant_paiement_periode = Decimal(str(paiement.montant or 0))
            cle_periode = 'passes' if paiement.date_facture < debut_mois_courant_forfait else 'en_cours'
            if cle_periode == 'passes':
                montant_prevu_mois_passes_forfait += montant_paiement_periode
            else:
                montant_prevu_mois_en_cours_forfait += montant_paiement_periode
            if paiement.est_encaisse:
                point_eau_det = paiement.point_eau
                encaisse_details_forfait.append({
                    'periode': cle_periode,
                    'ouvrage': paiement.point_eau.ouvrage.nom_ouvrage if point_eau_det and point_eau_det.ouvrage else '-',
                    'point_eau': (point_eau_det.nomabonne or point_eau_det.code_point_eau or '-') if point_eau_det else '-',
                    'idxls': str(getattr(point_eau_det, 'idxls', '') or ''),
                    'reference': paiement.date_facture.strftime('%d/%m/%Y'),
                    'montant': float(montant_paiement_periode),
                    'date_encaissement': paiement.date_encaissement.strftime('%d/%m/%Y') if paiement.date_encaissement else '',
                    'pointe': paiement.est_pointe_complet,
                    'numero': str(paiement.numeroDiameX or ''),
                })
                encaisse_periode_forfait[cle_periode]['total'] += montant_paiement_periode
                if paiement.est_encaisse_non_pointe:
                    encaisse_periode_forfait[cle_periode]['non_pointe'] += montant_paiement_periode
                    encaisse_periode_forfait[cle_periode]['nb_non_pointe'] += 1

    montant_collecte_mois_passes_forfait = Decimal('0')
    montant_collecte_mois_en_cours_forfait = Decimal('0')
    if annee == today.year:
        mois_en_cours_numero_forfait = today.month
        for tx in transactions_avec_ouvrage:
            ouvrage_tx = tx.get('ouvrage')
            if not ouvrage_tx or ouvrage_tx.id not in ouvrages_ids_filtres_forfait:
                continue
            mois_tx = tx.get('mois')
            if not mois_tx:
                date_tx = tx['transaction'].date_m
                mois_tx = date_tx.month if date_tx else None
            if not mois_tx:
                continue
            montant_tx = Decimal(str(tx.get('montant') or 0))
            if mois_tx < mois_en_cours_numero_forfait:
                montant_collecte_mois_passes_forfait += montant_tx
            elif mois_tx == mois_en_cours_numero_forfait:
                montant_collecte_mois_en_cours_forfait += montant_tx
    elif annee < today.year:
        for tx in transactions_avec_ouvrage:
            ouvrage_tx = tx.get('ouvrage')
            if not ouvrage_tx or ouvrage_tx.id not in ouvrages_ids_filtres_forfait:
                continue
            montant_collecte_mois_passes_forfait += Decimal(str(tx.get('montant') or 0))
    # annee > today.year : ni mois passe ni mois en cours

    debut_annee_decote_forfait = date(annee, 1, 1)
    fin_annee_decote_forfait = date(annee, 12, 31)
    if semestre_exigible_debut:
        debut_annee_decote_forfait = max(debut_annee_decote_forfait, semestre_exigible_debut)
    if semestre_exigible_fin:
        fin_annee_decote_forfait = min(fin_annee_decote_forfait, semestre_exigible_fin)

    points_eau_tous_filtres_forfait = [
        pe
        for ouvrage_id_int in ouvrages_ids_filtres_forfait
        for pe in points_eau_par_ouvrage_id.get(ouvrage_id_int, [])
    ]

    decote_mois_passes_forfait = Decimal('0')
    decote_mois_en_cours_forfait = Decimal('0')
    if annee < today.year:
        decote_mois_passes_forfait = calculer_decote_coupures(
            points_eau_tous_filtres_forfait, annee,
            periode_debut=debut_annee_decote_forfait,
            periode_fin=fin_annee_decote_forfait,
        )
    elif annee == today.year:
        fin_mois_passes_forfait = debut_mois_courant_forfait - timedelta(days=1)
        if fin_mois_passes_forfait >= debut_annee_decote_forfait:
            decote_mois_passes_forfait = calculer_decote_coupures(
                points_eau_tous_filtres_forfait, annee,
                periode_debut=debut_annee_decote_forfait,
                periode_fin=min(fin_annee_decote_forfait, fin_mois_passes_forfait),
            )
        debut_mois_en_cours_forfait = max(debut_annee_decote_forfait, debut_mois_courant_forfait)
        fin_mois_en_cours_forfait = min(fin_annee_decote_forfait, today)
        if debut_mois_en_cours_forfait <= fin_mois_en_cours_forfait:
            decote_mois_en_cours_forfait = calculer_decote_coupures(
                points_eau_tous_filtres_forfait, annee,
                periode_debut=debut_mois_en_cours_forfait,
                periode_fin=fin_mois_en_cours_forfait,
            )

    def _totaux_recouvrement_periode_forfait(total_prevu, total_collecte, decote, encaisse=None):
        taux = int(round((float(total_collecte) / float(total_prevu)) * 100)) if total_prevu > 0 else 0
        ecart = total_prevu - total_collecte
        encaisse = encaisse or {'total': Decimal('0'), 'non_pointe': Decimal('0'), 'nb_non_pointe': 0}
        return {
            'total_encaisse': encaisse['total'],
            'total_encaisse_k': round(float(encaisse['total']) / 1000),
            'encaisse_non_pointe': encaisse['non_pointe'],
            'encaisse_non_pointe_k': round(float(encaisse['non_pointe']) / 1000),
            'nb_encaisse_non_pointe': encaisse['nb_non_pointe'],
            # Pointé = encaissé confirmé par le pointage compta ; écart = encaissé - pointé
            'total_pointe_k': round(float(encaisse['total'] - encaisse['non_pointe']) / 1000),
            'ecart_encaisse_pointe': encaisse['non_pointe'],
            'ecart_encaisse_pointe_k': round(float(encaisse['non_pointe']) / 1000),
            'taux_encaisse': int(round(float(encaisse['total']) / float(total_prevu) * 100)) if total_prevu > 0 else 0,
            'total_prevu': total_prevu,
            'total_prevu_k': round(float(total_prevu) / 1000),
            'total_collecte': total_collecte,
            'total_collecte_k': round(float(total_collecte) / 1000),
            'decote': decote,
            'decote_k': round(float(decote) / 1000),
            'ecart': ecart,
            'ecart_k': round(float(ecart) / 1000),
            'taux': taux,
            'progression': min(taux, 100),
            'has_data': (total_prevu > 0 or decote > 0),
        }

    recouvrement_mois_passes_forfait = _totaux_recouvrement_periode_forfait(
        montant_prevu_mois_passes_forfait, montant_collecte_mois_passes_forfait, decote_mois_passes_forfait,
        encaisse_periode_forfait['passes'],
    )
    recouvrement_mois_en_cours_forfait = _totaux_recouvrement_periode_forfait(
        montant_prevu_mois_en_cours_forfait, montant_collecte_mois_en_cours_forfait, decote_mois_en_cours_forfait,
        encaisse_periode_forfait['en_cours'],
    )
    afficher_recouvrement_mois_en_cours_forfait = (annee == today.year)
    noms_mois_fr_forfait_dashboard = [
        '', 'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre'
    ]
    recouvrement_mois_en_cours_forfait['libelle_mois'] = (
        noms_mois_fr_forfait_dashboard[today.month] if afficher_recouvrement_mois_en_cours_forfait else ''
    )

    # ========== DONNÉES POUR LES GRAPHIQUES ==========

    # Recouvrement par mois (pour graphique temporel)
    recouvrement_par_mois = {}

    for ouvrage_id, data in recouvrement_par_ouvrage.items():
        ouvrage = data['ouvrage']

        # Pour chaque mois de l'année
        for mois in range(1, 13):
            cle_mois = f"{ouvrage_id}_{annee}_{mois:02d}"

            # Montant mensuel prévu = somme des factures forfaitaires du mois (date_facture)
            montant_mensuel = montant_prevu_mensuel_par_ouvrage.get(ouvrage.id, {}).get(mois, Decimal('0'))

            # Montant collecté ce mois
            montant_collecte_mois = sum([
                t['montant'] for t in transactions_avec_ouvrage
                if t['ouvrage'].id == ouvrage.id and t['transaction'].date_m.month == mois
            ])

            recouvrement_par_mois[cle_mois] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': data['ouvrage_nom'],
                'annee': annee,
                'mois': mois,
                'montant_a_collecter': float(montant_mensuel),
                'montant_collecte': float(montant_collecte_mois)
            }

    # Préparer données pour Chart.js (graphique évolution annuelle)
    # Calculer pour les 3 dernières années incluant l'année actuelle
    annee_actuelle = annee
    annees = [annee_actuelle - 2, annee_actuelle - 1, annee_actuelle]
    annees_labels = [str(a) for a in annees]

    montants_prevus_annuel = []
    montants_collectes_annuel = []

    for annee_calc in annees:
        # Calculer montant prévu pour cette année
        total_prevu_annee = sum([
            data['montant_a_collecter']
            for data in recouvrement_par_ouvrage.values()
        ])

        # Calculer montant collecté pour cette année (depuis recouvrement_par_mois)
        total_collecte_annee = sum([
            data['montant_collecte']
            for data in recouvrement_par_mois.values()
            if data['annee'] == annee_calc
        ])

        montants_prevus_annuel.append(total_prevu_annee)
        montants_collectes_annuel.append(total_collecte_annee)

    debut_mois_courant = today.replace(day=1)

    def _statut_recouvrement_echu(paiements_echus_periode):
        if not paiements_echus_periode:
            return None
        total_echu_periode = sum(
            Decimal(str(paiement.montant or 0))
            for paiement in paiements_echus_periode
        )
        total_paye_periode = sum(
            Decimal(str(paiement.montant or 0))
            for paiement in paiements_echus_periode
            if paiement.est_paye
        )
        if total_paye_periode <= 0:
            return 'non_paye'
        if total_paye_periode < total_echu_periode:
            return 'paye_lt_100'
        return 'paye_ge_100'

    for point_eau_id, paiements_point in paiements_par_point_eau.items():
        point_ouvrage_id = next((
            paiement.point_eau.ouvrage_id
            for paiement in paiements_point
            if paiement.point_eau and paiement.point_eau.ouvrage_id
        ), None)
        if not point_ouvrage_id or str(point_ouvrage_id) not in recouvrement_par_ouvrage:
            continue
        paiements_echus = [
            paiement for paiement in paiements_point
            if paiement.date_facture and paiement.date_facture <= today
        ]
        if not paiements_echus:
            continue

        total_echu = sum(Decimal(str(paiement.montant or 0)) for paiement in paiements_echus)
        total_echu_paye = sum(
            Decimal(str(paiement.montant or 0))
            for paiement in paiements_echus
            if paiement.est_paye
        )

        if total_echu_paye <= 0:
            nb_points_eau_non_payes_echus += 1
        elif total_echu_paye >= total_echu:
            nb_points_eau_payes_echus_ge_100 += 1
        else:
            nb_points_eau_payes_echus_lt_100 += 1

        paiements_mois_passes = [
            paiement for paiement in paiements_echus
            if paiement.date_facture < debut_mois_courant
        ]
        paiements_mois_en_cours = [
            paiement for paiement in paiements_echus
            if paiement.date_facture >= debut_mois_courant
        ]
        statut_mois_passes = _statut_recouvrement_echu(paiements_mois_passes)
        statut_mois_en_cours = _statut_recouvrement_echu(paiements_mois_en_cours)

        if statut_mois_passes == 'non_paye':
            nb_points_eau_non_payes_echus_mois_passes += 1
            ouvrages_non_payes_echus_mois_passes.add(str(point_ouvrage_id))
        elif statut_mois_passes == 'paye_lt_100':
            nb_points_eau_payes_echus_lt_100_mois_passes += 1

        if statut_mois_en_cours == 'non_paye':
            nb_points_eau_non_payes_echus_mois_en_cours += 1
            ouvrages_non_payes_echus_mois_en_cours.add(str(point_ouvrage_id))
        elif statut_mois_en_cours == 'paye_lt_100':
            nb_points_eau_payes_echus_lt_100_mois_en_cours += 1

    if filter_statut_echu:
        ouvrages_cibles = (
            ouvrages_non_payes_echus_mois_passes
            if filter_statut_echu == 'non_paye_mois_passes'
            else ouvrages_non_payes_echus_mois_en_cours
        )
        recouvrement_par_ouvrage = {
            ouvrage_id: data
            for ouvrage_id, data in recouvrement_par_ouvrage.items()
            if ouvrage_id in ouvrages_cibles
        }

    employee_points_score = {'visible': False}
    responsible_point_ids = {
        str(point_eau_id)
        for point_eau_id in _apply_forfaitaire_point_eau_geo_filters(
            _forfait_points_queryset().filter(ouvrage_id__in=score_ouvrage_ids),
            filter_region=filter_region,
            filter_district=filter_district,
            filter_commune=filter_commune,
        ).values_list('id', flat=True)
    }
    score_reference_month = timezone.localdate().replace(day=1)
    employee_point_ids = set()
    payment_totals_by_point = defaultdict(
        lambda: {'expected': Decimal('0'), 'paid': Decimal('0')}
    )
    for point_eau_id, paiements_point in paiements_par_point_eau.items():
        normalized_point_id = str(point_eau_id)
        if normalized_point_id not in responsible_point_ids:
            continue
        for paiement in paiements_point:
            if not is_closed_payment_month(paiement.date_facture, score_reference_month):
                continue
            employee_point_ids.add(normalized_point_id)
            montant_paiement = Decimal(str(paiement.montant or 0))
            payment_totals_by_point[normalized_point_id]['expected'] += montant_paiement
            if paiement.est_paye:
                payment_totals_by_point[normalized_point_id]['paid'] += montant_paiement

    employee_points_score = calculate_water_point_score(
        employee_point_ids,
        payment_totals_by_point,
    )
    score_gap_point_ids = get_water_point_score_gap_ids(
        employee_point_ids,
        payment_totals_by_point,
    )
    score_gap_ouvrage_ids = {
        str(ouvrage_id)
        for ouvrage_id in _forfait_points_queryset().filter(
            id__in=score_gap_point_ids,
            ouvrage_id__in=score_ouvrage_ids,
        ).values_list('ouvrage_id', flat=True)
        if ouvrage_id
    }
    employee_points_score.update({
        'visible': True,
        **resolve_score_scope(
            employee_options=employes_responsables,
            employee_id=filter_employe,
            ouvrage_id=filter_ouvrage,
            commune_id=filter_commune,
            district_id=filter_district,
            region_id=filter_region,
            organisation_id=filter_organisation,
            default_organisation_name=getattr(organisation_user, 'nom_organisation', '') or '',
        ),
    })

    if show_only_score_gap:
        recouvrement_par_ouvrage = {
            ouvrage_id: data
            for ouvrage_id, data in recouvrement_par_ouvrage.items()
            if str(ouvrage_id) in score_gap_ouvrage_ids
        }

    # ========== FILTRES POUR LE TEMPLATE ==========

    # Liste des régions
    regions, districts_all, communes_all, ouvrages_pour_filtre = build_employee_geo_filter_options(
        ouvrages_org_filter_scope,
        employes_responsables,
    )

    # Listes complètes pour cascade région -> district -> commune (côté client)

    # Listes filtrées pour affichage initial
    if filter_region:
        districts = [district for district in districts_all if str(district.region_id) == str(filter_region)]
    else:
        districts = districts_all

    if filter_district:
        communes = [commune for commune in communes_all if str(commune.district_id) == str(filter_district)]
    elif filter_region:
        communes = [commune for commune in communes_all if str(commune.district.region_id) == str(filter_region)]
    else:
        communes = communes_all

    # Liste des ouvrages (filtrés par organisation)
    # Annoter chaque ouvrage avec son commune_id via PointEau → Parcelle → Village → Fokontany → Commune
    # Les ouvrages et leurs métadonnées de cascade proviennent du helper partagé.

    # ========== CONTEXTE POUR LE TEMPLATE ==========

    # Convertir les montants en milliers pour l'affichage
    total_a_collecter_k = int(total_a_collecter_global / 1000)
    total_paiement_forfaitaire_k = int(total_paiement_forfaitaire_global / 1000)
    total_collecte_k = int(total_collecte_global / 1000)
    total_collecte_non_pointe_k = int(total_collecte_non_pointe_global / 1000)
    ecart_a_collecter_k = int(ecart_a_collecter_global / 1000)
    ecart_collecte_vs_forfaitaire_k = int(ecart_collecte_vs_forfaitaire_global / 1000)

    # Trier puis paginer le detail par ouvrage
    recouvrement_par_ouvrage_list = sorted(
        recouvrement_par_ouvrage.values(),
        key=lambda item: (
            (item.get('district_nom') or '').lower(),
            (item.get('commune_nom') or '').lower(),
            (item.get('ouvrage_nom') or '').lower(),
        )
    )

    detail_total_count = len(recouvrement_par_ouvrage_list)
    detail_page_obj = None
    detail_page_numbers = []
    detail_current_count = detail_total_count
    detail_items = recouvrement_par_ouvrage_list

    if detail_page_size:
        detail_paginator = Paginator(recouvrement_par_ouvrage_list, detail_page_size)
        detail_page_obj = detail_paginator.get_page(detail_page)
        detail_page_numbers = _paginate_page_numbers(detail_page_obj)
        detail_current_count = len(detail_page_obj.object_list)
        detail_items = list(detail_page_obj.object_list)

    detail_query_params = request.GET.copy()
    for key in ['detail_page', 'export_full']:
        if key in detail_query_params:
            detail_query_params.pop(key)
    detail_pagination_query = detail_query_params.urlencode()

    # Grouper les ouvrages de la page courante par District et Commune
    recouvrement_par_district = defaultdict(lambda: defaultdict(list))

    for ouvrage_data in detail_items:
        district = ouvrage_data['district_nom']
        commune = ouvrage_data['commune_nom']
        recouvrement_par_district[district][commune].append(ouvrage_data)

    # Convertir en dictionnaire normal et trier par district puis commune
    recouvrement_par_district = dict(sorted(recouvrement_par_district.items()))

    # Calculer le nombre total d'ouvrages par district
    district_counts = {}
    for district, communes_dict in recouvrement_par_district.items():
        total_ouvrages = sum(len(ouvrages) for ouvrages in communes_dict.values())
        district_counts[district] = total_ouvrages
        recouvrement_par_district[district] = dict(sorted(communes_dict.items()))

    context = {
        'annee': annee,
        'filter_region': filter_region,
        'filter_district': filter_district,
        'filter_commune': filter_commune,
        'filter_ouvrage': filter_ouvrage,
        'filter_employe': filter_employe,
        'filter_organisation': filter_organisation,
        'filter_taux': filter_taux,
        'filter_taux_forfaitaire': filter_taux_forfaitaire,
        'filter_semestre': filter_semestre,
        'filter_non_pointe': filter_non_pointe,
        'filter_echu': filter_echu,
        'filter_statut_echu': filter_statut_echu,
        'organisations': organisations,
        'regions': regions,
        'districts': districts,
        'districts_all': districts_all,
        'communes': communes,
        'communes_all': communes_all,
        'ouvrages': ouvrages_pour_filtre,
        'employes_responsables': employes_responsables,
        'employee_points_score': employee_points_score,
        'show_only_score_gap': show_only_score_gap,
        'stats_global': {
            'total_a_collecter': total_a_collecter_global,  # Montant complet pour calculs
            'total_paiement_forfaitaire': total_paiement_forfaitaire_global,
            'total_collecte': total_collecte_global,
             'total_collecte_non_pointe': total_collecte_non_pointe_global,
             'total_encaisse': total_encaisse_global,
             'encaisse_details': encaisse_details_forfait,
             'total_encaisse_k': int(total_encaisse_global / 1000),
             'total_encaisse_non_pointe': total_encaisse_non_pointe_global,
             'total_encaisse_non_pointe_k': int(total_encaisse_non_pointe_global / 1000),
             'nb_encaisse_non_pointe': nb_encaisse_non_pointe_global,
             'taux_encaisse': taux_encaisse_global,
             'nb_lignes_diamex_non_pointe': total_lignes_diamex_non_pointe_global,
            'ecart_a_collecter': ecart_a_collecter_global,
            'ecart_collecte_vs_forfaitaire': ecart_collecte_vs_forfaitaire_global,
            'total_a_collecter_k': total_a_collecter_k,  # Montant en milliers pour affichage
            'total_paiement_forfaitaire_k': total_paiement_forfaitaire_k,
            'total_collecte_k': total_collecte_k,
            'total_collecte_non_pointe_k': total_collecte_non_pointe_k,
            'ecart_a_collecter_k': ecart_a_collecter_k,
            'ecart_collecte_vs_forfaitaire_k': ecart_collecte_vs_forfaitaire_k,
            'taux_recouvrement': taux_recouvrement_global,
            'has_taux_recouvrement': has_taux_recouvrement_global,
            'taux_paye_sur_forfaitaire': taux_paye_sur_forfaitaire_global,
            'has_taux_paye_sur_forfaitaire': has_taux_paye_sur_forfaitaire_global,
            'nb_ouvrages': nb_ouvrages_total,
             'nb_points_eau': nb_points_eau_total,
             'nb_points_eau_coupes': nb_points_eau_coupes_total,
             'nb_points_eau_payes_echus_ge_100': nb_points_eau_payes_echus_ge_100,
             'nb_points_eau_payes_echus_lt_100': nb_points_eau_payes_echus_lt_100,
             'nb_points_eau_non_payes_echus': nb_points_eau_non_payes_echus,
             'nb_points_eau_payes_echus_lt_100_mois_passes': nb_points_eau_payes_echus_lt_100_mois_passes,
             'nb_points_eau_payes_echus_lt_100_mois_en_cours': nb_points_eau_payes_echus_lt_100_mois_en_cours,
             'nb_points_eau_non_payes_echus_mois_passes': nb_points_eau_non_payes_echus_mois_passes,
             'nb_points_eau_non_payes_echus_mois_en_cours': nb_points_eau_non_payes_echus_mois_en_cours,
             'pct_points_eau_payes_echus_ge_100': _pct_points_eau(nb_points_eau_payes_echus_ge_100),
             'pct_points_eau_payes_echus_lt_100': _pct_points_eau(nb_points_eau_payes_echus_lt_100),
             'pct_points_eau_non_payes_echus': _pct_points_eau(nb_points_eau_non_payes_echus),
             'pct_points_eau_payes_echus_lt_100_mois_passes': _pct_points_eau(nb_points_eau_payes_echus_lt_100_mois_passes),
             'pct_points_eau_payes_echus_lt_100_mois_en_cours': _pct_points_eau(nb_points_eau_payes_echus_lt_100_mois_en_cours),
             'pct_points_eau_non_payes_echus_mois_passes': _pct_points_eau(nb_points_eau_non_payes_echus_mois_passes),
             'pct_points_eau_non_payes_echus_mois_en_cours': _pct_points_eau(nb_points_eau_non_payes_echus_mois_en_cours),
             'nb_ouvrages_gt100': nb_ouvrages_gt100,
             'nb_ouvrages_eq100': nb_ouvrages_eq100,
             'nb_ouvrages_lt100': nb_ouvrages_lt100,
             'nb_ouvrages_paid_cut_alert': nb_ouvrages_paid_cut_alert,
             'nb_points_eau_paid_cut_alert': nb_points_eau_paid_cut_alert,
             'nb_points_eau_tranches_ok': nb_points_eau_tranches_ok,
             'nb_points_eau_tranches_lt': nb_points_eau_tranches_lt,
             'nb_points_eau_tranches_gt': nb_points_eau_tranches_gt,
             'pct_points_eau_tranches_ok': _pct_points_eau(nb_points_eau_tranches_ok),
             'pct_points_eau_tranches_lt': _pct_points_eau(nb_points_eau_tranches_lt),
             'pct_points_eau_tranches_gt': _pct_points_eau(nb_points_eau_tranches_gt),
             'pct_ouvrages_gt100': _pct_ouvrages(nb_ouvrages_gt100),
             'pct_ouvrages_eq100': _pct_ouvrages(nb_ouvrages_eq100),
             'pct_ouvrages_lt100': _pct_ouvrages(nb_ouvrages_lt100)
         },
        'recouvrement_mois_passes': recouvrement_mois_passes_forfait,
        'recouvrement_mois_en_cours': recouvrement_mois_en_cours_forfait,
        'afficher_recouvrement_mois_en_cours': afficher_recouvrement_mois_en_cours_forfait,
        'filter_explication': filter_explication,
        'recouvrement_par_ouvrage': recouvrement_par_ouvrage_list,
        'recouvrement_par_district': recouvrement_par_district,
        'district_counts': district_counts,
        'detail_total_count': detail_total_count,
        'detail_current_count': detail_current_count,
        'detail_page_obj': detail_page_obj,
        'detail_page_numbers': detail_page_numbers,
        'detail_page_size': detail_page_size or detail_total_count,
        'detail_is_paginated': bool(detail_page_obj and detail_page_obj.paginator.num_pages > 1),
        'detail_pagination_query': detail_pagination_query,
        'recouvrement_par_mois': list(recouvrement_par_mois.values()),
        'graphique_annuel': {
            'labels': annees_labels,
            'prevus': montants_prevus_annuel,
            'collectes': montants_collectes_annuel
        },
        'transactions_non_appariees': transactions_non_appariees,
        'montant_total_non_appariees': montant_total_non_appariees,
    }

    return render(request, 'accounting/dashboard_paiements_forfaitaire.html', context)


def _build_forfaitaire_calendar_context(request, *, print_mode=False):
    commune_palette = [
        {
            'screen_style': '--commune-bg: rgba(14, 165, 233, 0.16); --commune-border: rgba(56, 189, 248, 0.42); --commune-text: rgb(224, 242, 254); --commune-subtext: rgba(224, 242, 254, 0.78); --commune-badge-bg: rgba(14, 165, 233, 0.22); --commune-badge-text: rgb(224, 242, 254);',
            'print_card_class': 'border-sky-300 bg-sky-50',
        },
        {
            'screen_style': '--commune-bg: rgba(16, 185, 129, 0.16); --commune-border: rgba(52, 211, 153, 0.42); --commune-text: rgb(209, 250, 229); --commune-subtext: rgba(209, 250, 229, 0.78); --commune-badge-bg: rgba(16, 185, 129, 0.22); --commune-badge-text: rgb(209, 250, 229);',
            'print_card_class': 'border-emerald-300 bg-emerald-50',
        },
        {
            'screen_style': '--commune-bg: rgba(245, 158, 11, 0.16); --commune-border: rgba(251, 191, 36, 0.42); --commune-text: rgb(254, 243, 199); --commune-subtext: rgba(254, 243, 199, 0.78); --commune-badge-bg: rgba(245, 158, 11, 0.22); --commune-badge-text: rgb(254, 243, 199);',
            'print_card_class': 'border-amber-300 bg-amber-50',
        },
        {
            'screen_style': '--commune-bg: rgba(244, 63, 94, 0.16); --commune-border: rgba(251, 113, 133, 0.42); --commune-text: rgb(255, 228, 230); --commune-subtext: rgba(255, 228, 230, 0.78); --commune-badge-bg: rgba(244, 63, 94, 0.22); --commune-badge-text: rgb(255, 228, 230);',
            'print_card_class': 'border-rose-300 bg-rose-50',
        },
        {
            'screen_style': '--commune-bg: rgba(139, 92, 246, 0.16); --commune-border: rgba(167, 139, 250, 0.42); --commune-text: rgb(237, 233, 254); --commune-subtext: rgba(237, 233, 254, 0.78); --commune-badge-bg: rgba(139, 92, 246, 0.22); --commune-badge-text: rgb(237, 233, 254);',
            'print_card_class': 'border-violet-300 bg-violet-50',
        },
        {
            'screen_style': '--commune-bg: rgba(6, 182, 212, 0.16); --commune-border: rgba(34, 211, 238, 0.42); --commune-text: rgb(207, 250, 254); --commune-subtext: rgba(207, 250, 254, 0.78); --commune-badge-bg: rgba(6, 182, 212, 0.22); --commune-badge-text: rgb(207, 250, 254);',
            'print_card_class': 'border-cyan-300 bg-cyan-50',
        },
    ]
    commune_color_map = {}

    annee = int(request.GET.get('annee', timezone.localdate().year))
    vue = (request.GET.get('vue') or 'mois').strip().lower()
    if vue not in ('mois', 'semaine'):
        vue = 'mois'

    filter_organisation = request.GET.get('organisation', '')
    filter_region = request.GET.get('region', '')
    filter_district = request.GET.get('district', '')
    filter_commune = request.GET.get('commune', '')
    filter_employe = request.GET.get('employe', '')
    selected_date_raw = request.GET.get('date', '')

    try:
        selected_date = datetime.strptime(selected_date_raw, '%Y-%m-%d').date() if selected_date_raw else timezone.localdate()
    except ValueError:
        selected_date = timezone.localdate()

    accessible_gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    gestionnaire_ids, resolved_organisation = _resolve_gestionnaire_scope(
        accessible_gestionnaire_ids,
        filter_organisation,
    )
    ouvrages_scope = _get_scoped_forfaitaire_ouvrage_ids(
        request.user,
        annee=annee,
        gestionnaire_ids=gestionnaire_ids,
    )

    _cleanup_stale_cut_forfait_points(ouvrage_ids=ouvrages_scope)

    points_qs = _forfait_points_queryset().filter(ouvrage_id__in=ouvrages_scope)
    points_qs = _apply_forfaitaire_point_eau_geo_filters(
        points_qs,
        filter_region=filter_region,
        filter_district=filter_district,
        filter_commune=filter_commune,
    )

    ouvrage_ids_filtered = set(points_qs.values_list('ouvrage_id', flat=True).distinct())
    paiements_qs = (
        PaiementForfaitaire.objects.filter(
            point_eau__ouvrage_id__in=ouvrage_ids_filtered,
            date_facture__year=annee,
        )
        .select_related(
            'point_eau__ouvrage',
            'point_eau__parcelle__village__fokontany__commune__district__region',
            'planning__employe',
        )
        .defer(*DEFER_PHOTOS_PAIEMENT_PLANNING)
        .order_by('date_facture', 'point_eau__ouvrage__nom_ouvrage', 'created_at')
    )

    if filter_employe:
        paiements_qs = paiements_qs.filter(planning__employe_id=filter_employe)

    employee_ids = list(
        PaiementForfaitaire.objects.filter(
            point_eau__ouvrage_id__in=ouvrage_ids_filtered,
            date_facture__year=annee,
            planning__employe_id__isnull=False,
        )
        .values_list('planning__employe_id', flat=True)
        .distinct()
    )
    employes = Employe.objects.filter(id__in=employee_ids).order_by('surnom', 'nom', 'prenom')

    if vue == 'semaine':
        period_start = selected_date - timedelta(days=selected_date.weekday())
        period_end = period_start + timedelta(days=6)
    else:
        period_start = selected_date.replace(day=1)
        period_end = selected_date.replace(day=monthrange(selected_date.year, selected_date.month)[1])

    paiements_qs = paiements_qs.filter(
        date_facture__gte=period_start,
        date_facture__lte=period_end,
    )

    rows_by_day = defaultdict(list)
    totals = {
        'factures': 0,
        'factures_pointees': 0,
        'factures_non_pointees': 0,
        'montant_total': Decimal('0'),
        'montant_pointe': Decimal('0'),
        'montant_non_pointe': Decimal('0'),
    }

    for paiement in paiements_qs:
        day = paiement.date_facture
        ouvrage = paiement.point_eau.ouvrage if paiement.point_eau else None
        employe = getattr(getattr(paiement, 'planning', None), 'employe', None)
        montant = Decimal(str(paiement.montant or 0))
        est_pointe = paiement.est_pointe_complet
        geo = None
        if paiement.point_eau and paiement.point_eau.parcelle and paiement.point_eau.parcelle.village and paiement.point_eau.parcelle.village.fokontany:
            geo = paiement.point_eau.parcelle.village.fokontany.commune

        rows_by_day[day].append({
            'paiement_id': str(paiement.id),
            'date_facture': day,
            'ouvrage_id': str(ouvrage.id) if ouvrage else '',
            'ouvrage_nom': ouvrage.nom_ouvrage if ouvrage else 'Ouvrage inconnu',
            'point_eau_nom': paiement.point_eau.nomabonne or paiement.point_eau.code_point_eau if paiement.point_eau else '-',
            'point_eau_idxls': str(paiement.point_eau.idxls) if paiement.point_eau and paiement.point_eau.idxls else '-',
            'employe_nom': (employe.surnom or employe.nom_complet) if employe else 'Sans employe',
            'commune_nom': geo.nom_commune if geo else '-',
            'montant': float(montant),
            'est_pointe': est_pointe,
            'numero_diamex': paiement.numeroDiameX or '',
            'base_diamex': paiement.baseDiameX or '',
        })
        totals['factures'] += 1
        totals['montant_total'] += montant
        if est_pointe:
            totals['factures_pointees'] += 1
            totals['montant_pointe'] += montant
        else:
            totals['factures_non_pointees'] += 1
            totals['montant_non_pointe'] += montant

    events_by_day = {}
    for day, rows in rows_by_day.items():
        grouped = {}
        for row in rows:
            key = row['ouvrage_id'] or f"missing-{row['ouvrage_nom']}"
            bucket = grouped.setdefault(key, {
                'ouvrage_id': row['ouvrage_id'],
                'ouvrage_nom': row['ouvrage_nom'],
                'employes': set(),
                'communes': set(),
                'factures': 0,
                'factures_pointees': 0,
                'factures_non_pointees': 0,
                'montant_total': Decimal('0'),
                'montant_pointe': Decimal('0'),
                'montant_non_pointe': Decimal('0'),
                'payment_ids': [],
            })
            bucket['factures'] += 1
            bucket['montant_total'] += Decimal(str(row['montant']))
            bucket['employes'].add(row['employe_nom'])
            if row['paiement_id']:
                bucket['payment_ids'].append(row['paiement_id'])
            if row['commune_nom'] and row['commune_nom'] != '-':
                bucket['communes'].add(row['commune_nom'])
            if row['est_pointe']:
                bucket['factures_pointees'] += 1
                bucket['montant_pointe'] += Decimal(str(row['montant']))
            else:
                bucket['factures_non_pointees'] += 1
                bucket['montant_non_pointe'] += Decimal(str(row['montant']))

        events_by_day[day.isoformat()] = sorted([
            {
                **bucket,
                'employes': ', '.join(sorted(bucket['employes'])) or '-',
                'communes': ', '.join(sorted(bucket['communes'])) or '-',
                'montant_total': float(bucket['montant_total']),
                'montant_pointe': float(bucket['montant_pointe']),
                'montant_non_pointe': float(bucket['montant_non_pointe']),
                'payment_ids': bucket['payment_ids'],
                'payment_ids_json': json.dumps(bucket['payment_ids']),
                'can_drag': bucket['factures'] > 0 and bucket['factures_pointees'] == 0,
                **commune_color_map.setdefault(
                    ', '.join(sorted(bucket['communes'])) or '-',
                    commune_palette[len(commune_color_map) % len(commune_palette)]
                ),
            }
            for bucket in grouped.values()
        ], key=lambda item: (item['ouvrage_nom'] or '').lower())

    # Indique dans la check-list si un rapprochement exact est réellement possible :
    # une ou plusieurs lignes forfaitaires non pointées et une ligne DiameX 748411
    # disponible du même mois dont les montants se compensent.
    unpointed_rows_by_ouvrage = defaultdict(list)
    for rows in rows_by_day.values():
        for row in rows:
            row['pointage_possible'] = False
            if not row['est_pointe'] and row['ouvrage_id']:
                unpointed_rows_by_ouvrage[row['ouvrage_id']].append({
                    'id': row['paiement_id'],
                    'montant': row['montant'],
                    'mois': row['date_facture'].month,
                    'point_eau_idxls': row['point_eau_idxls'],
                    'est_pointe': False,
                })

    available_diamex_by_ouvrage = defaultdict(list)
    if unpointed_rows_by_ouvrage:
        displayed_months = {
            row['date_facture'].month
            for rows in rows_by_day.values()
            for row in rows
            if row.get('date_facture')
        }
        pointed_pairs = {
            (str(numero or '').strip().lower(), str(base or '').strip().lower())
            for numero, base in PaiementForfaitaire.objects.filter(
                point_eau__ouvrage_id__in=ouvrage_ids_filtered,
                numeroDiameX__isnull=False,
                baseDiameX__isnull=False,
            ).exclude(numeroDiameX='').exclude(baseDiameX='')
            .values_list('numeroDiameX', 'baseDiameX')
        }
        transactions_for_checklist = BaseDiameX.objects.filter(
            compte_code='748411',
            date_m__year=annee,
            date_m__month__in=displayed_months,
            montant_in__gt=0,
        ).only('id', 'id_access', 'prog', 'description', 'montant_in', 'date_m')
        for transaction in transactions_for_checklist.iterator(chunk_size=500):
            try:
                extraction = extraire_ouvrage_et_mois_generique(transaction.description or '', '748411')
            except Exception:
                # Une écriture historique malformée ne doit jamais rendre le calendrier indisponible.
                continue
            ouvrage_obj = extraction.get('ouvrage_obj')
            ouvrage_key = str(ouvrage_obj.id) if ouvrage_obj else ''
            if ouvrage_key not in unpointed_rows_by_ouvrage:
                continue
            numero = str(transaction.id_access or '').strip()
            base = str(transaction.prog or '').strip()
            if numero and base and (numero.lower(), base.lower()) in pointed_pairs:
                continue
            available_diamex_by_ouvrage[ouvrage_key].append({
                'id': transaction.id,
                'entry_id': transaction.id,
                'id_access': numero,
                'prog': base,
                'description': transaction.description or '',
                'montant_in': float(transaction.montant_in or 0),
                'mois': extraction.get('mois') or (transaction.date_m.month if transaction.date_m else None),
                'already_pointed': False,
            })

        pointable_payment_ids = set()
        for ouvrage_key, payment_rows in unpointed_rows_by_ouvrage.items():
            suggestions = build_auto_pointage_forfaitaire_suggestions(
                payment_rows,
                available_diamex_by_ouvrage.get(ouvrage_key, []),
            ).get('suggestions', [])
            for suggestion in suggestions:
                pointable_payment_ids.update(str(item) for item in suggestion.get('paiement_ids', []))

        for rows in rows_by_day.values():
            for row in rows:
                row['pointage_possible'] = row['paiement_id'] in pointable_payment_ids

    if vue == 'semaine':
        calendar_days = [period_start + timedelta(days=offset) for offset in range(7)]
        title = f"Semaine du {period_start.strftime('%d/%m/%Y')} au {period_end.strftime('%d/%m/%Y')}"
    else:
        first_cell = period_start - timedelta(days=period_start.weekday())
        last_cell = period_end + timedelta(days=(6 - period_end.weekday()))
        total_days = (last_cell - first_cell).days + 1
        calendar_days = [first_cell + timedelta(days=offset) for offset in range(total_days)]
        title = selected_date.strftime('%B %Y').capitalize()

    regions, districts_all, communes_all = _get_forfaitaire_geo_querysets(ouvrages_scope)

    checklist_rows = sorted(
        [row for rows in rows_by_day.values() for row in rows],
        key=lambda row: (
            (row['employe_nom'] or '').lower(),
            (row['commune_nom'] or '').lower(),
            (row['ouvrage_nom'] or '').lower(),
            row['est_pointe'],
            row['date_facture'],
            (row['point_eau_nom'] or '').lower(),
        ),
    )
    checklist_group_map = {}
    for row in checklist_rows:
        employee_key = row['employe_nom'] or 'Sans employe'
        employee_group = checklist_group_map.setdefault(employee_key, {
            'nom': employee_key,
            'nb_lignes': 0,
            'nb_non_pointees': 0,
            'montant_non_pointe': Decimal('0'),
            'communes_map': {},
        })
        commune_key = row['commune_nom'] or '-'
        commune_group = employee_group['communes_map'].setdefault(commune_key, {
            'nom': commune_key,
            'nb_lignes': 0,
            'nb_non_pointees': 0,
            'montant_non_pointe': Decimal('0'),
            'ouvrages_map': {},
        })
        ouvrage_key = row['ouvrage_nom'] or 'Ouvrage inconnu'
        ouvrage_group = commune_group['ouvrages_map'].setdefault(ouvrage_key, {
            'nom': ouvrage_key,
            'nb_lignes': 0,
            'nb_non_pointees': 0,
            'montant_non_pointe': Decimal('0'),
            'rows': [],
        })

        employee_group['nb_lignes'] += 1
        commune_group['nb_lignes'] += 1
        ouvrage_group['nb_lignes'] += 1
        ouvrage_group['rows'].append(row)
        if not row['est_pointe']:
            montant = Decimal(str(row['montant'] or 0))
            for group in (employee_group, commune_group, ouvrage_group):
                group['nb_non_pointees'] += 1
                group['montant_non_pointe'] += montant

    checklist_groups = []
    for employee_group in checklist_group_map.values():
        employee_group['communes'] = []
        for commune_group in employee_group.pop('communes_map').values():
            commune_group['ouvrages'] = list(commune_group.pop('ouvrages_map').values())
            employee_group['communes'].append(commune_group)
        checklist_groups.append(employee_group)

    context = {
        'annee': annee,
        'print_mode': print_mode,
        'accounting_shell_base_template': 'base.html',
        'calendar_title': title,
        'vue': vue,
        'selected_date': selected_date,
        'period_start': period_start,
        'period_end': period_end,
        'calendar_days': calendar_days,
        'events_by_day': events_by_day,
        'checklist_rows': checklist_rows,
        'checklist_groups': checklist_groups,
        'filter_organisation': resolved_organisation,
        'filter_region': filter_region,
        'filter_district': filter_district,
        'filter_commune': filter_commune,
        'filter_employe': filter_employe,
        'organisations': _get_organisations_filtre_queryset(accessible_gestionnaire_ids),
        'regions': regions,
        'districts_all': districts_all,
        'communes_all': communes_all,
        'employes': employes,
        'totals': {
            'factures': totals['factures'],
            'factures_pointees': totals['factures_pointees'],
            'factures_non_pointees': totals['factures_non_pointees'],
            'montant_total': float(totals['montant_total']),
            'montant_pointe': float(totals['montant_pointe']),
            'montant_non_pointe': float(totals['montant_non_pointe']),
        },
    }
    return context


@login_required
def dashboard_paiements_forfaitaire_calendrier(request):
    context = _build_forfaitaire_calendar_context(request, print_mode=False)
    return render(request, 'accounting/dashboard_paiements_forfaitaire_calendrier.html', context)


@login_required
def dashboard_paiements_forfaitaire_calendrier_impression(request):
    context = _build_forfaitaire_calendar_context(request, print_mode=True)
    return render(request, 'accounting/dashboard_paiements_forfaitaire_calendrier_impression.html', context)


@login_required
@require_http_methods(["POST"])
def api_deplacer_paiements_forfaitaires_calendrier(request):
    try:
        payload = json.loads(request.body or '{}')
        paiement_ids = list(dict.fromkeys(
            str(item).strip()
            for item in (payload.get('paiement_ids') or [])
            if str(item).strip()
        ))
        target_date_raw = str(payload.get('target_date') or '').strip()

        if not paiement_ids:
            return JsonResponse({'success': False, 'error': 'Aucun paiement sélectionné'}, status=400)
        if not target_date_raw:
            return JsonResponse({'success': False, 'error': 'Date cible manquante'}, status=400)

        try:
            target_date = datetime.strptime(target_date_raw, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Format de date invalide'}, status=400)

        if not can_reschedule_forfaitaire_factures(request.user):
            return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)

        allowed_ouvrage_ids = _get_scoped_forfaitaire_ouvrage_ids(
            request.user,
            annee=target_date.year,
        )
        paiements = list(
            PaiementForfaitaire.objects.select_related(
                'point_eau',
                'point_eau__ouvrage',
                'planning',
                'planning__employe',
            ).defer(*DEFER_PHOTOS_PAIEMENT_PLANNING).filter(
                id__in=paiement_ids,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids,
            )
        )
        if len(paiements) != len(paiement_ids):
            return JsonResponse({'success': False, 'error': 'Certaines factures sont introuvables ou hors périmètre'}, status=404)

        pointed = [
            str(p.id) for p in paiements
            if (str(p.numeroDiameX or '').strip() and str(p.baseDiameX or '').strip())
        ]
        if pointed:
            return JsonResponse({
                'success': False,
                'error': 'Déplacement interdit: au moins une facture est déjà pointée.'
            }, status=400)

        moved_count = 0
        with transaction.atomic():
            for paiement in paiements:
                employe = getattr(getattr(paiement, 'planning', None), 'employe', None)
                paiement.date_facture = target_date
                duree_mois = int(getattr(paiement, 'duree_mois', 0) or 0)
                paiement.date_fin_validite = (
                    target_date + relativedelta(months=duree_mois) - timedelta(days=1)
                    if duree_mois > 0 else target_date
                )
                if paiement.point_eau_id:
                    paiement.planning = _find_or_create_matching_forfaitaire_planning(
                        point_eau=paiement.point_eau,
                        date_facture=target_date,
                        employe=employe,
                    )
                paiement.save(update_fields=['date_facture', 'date_fin_validite', 'planning', 'updated_at'])
                moved_count += 1

        return JsonResponse({
            'success': True,
            'message': f'{moved_count} facture(s) déplacée(s) au {target_date.strftime("%d/%m/%Y")}.',
            'target_date': target_date.isoformat(),
            'moved_count': moved_count,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def api_paiements_forfaitaire_communes_summary(request):
    """API pour lister le recouvrement forfaitaire par commune (groupé par région/district)."""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        # Filtres
        filter_annee = request.GET.get('annee', str(datetime.now().year))
        filter_region = request.GET.get('region', '')
        filter_district = request.GET.get('district', '')
        filter_commune = request.GET.get('commune', '')
        filter_ouvrage = request.GET.get('ouvrage', '')
        filter_employe = request.GET.get('employe', '')
        filter_organisation = request.GET.get('organisation', '')
        filter_explication = request.GET.get('explication', '')
        filter_taux = request.GET.get('taux', '')
        filter_taux_forfaitaire = request.GET.get('taux_forfaitaire', '')
        filter_trimestre = request.GET.get('trimestre', '')
        filter_semestre = request.GET.get('semestre', '').strip().upper()
        filter_echu = request.GET.get('echu', '')
        filter_non_pointe = request.GET.get('non_pointe', '')
        filter_statut_echu = request.GET.get('statut_echu', '')
        if filter_statut_echu not in {'non_paye_mois_passes', 'non_paye_mois_en_cours'}:
            filter_statut_echu = ''

        try:
            annee = int(filter_annee)
        except Exception:
            annee = datetime.now().year

        trimestre_debut, trimestre_fin = _get_quarter_bounds(annee, filter_trimestre)
        if filter_trimestre and not trimestre_debut:
            filter_trimestre = ''
        semestre_debut, semestre_fin = _get_semester_bounds(annee, filter_semestre)
        if filter_semestre and not semestre_debut:
            filter_semestre = ''
        if semestre_debut and semestre_fin:
            filter_trimestre = ''
            trimestre_debut = trimestre_fin = None
        semestre_exigible_debut, semestre_exigible_fin = _get_due_period_bounds(
            semestre_debut,
            semestre_fin,
        )

        # Scope gestionnaire de l'utilisateur
        accessible_gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
        gestionnaire_ids, _ = _resolve_gestionnaire_scope(
            accessible_gestionnaire_ids,
            filter_organisation
        )

        # Transactions DiameX (compte 748411)
        transactions_qs = BaseDiameX.objects.filter(
            compte_code='748411',
            date_m__year=annee
        )
        if trimestre_debut and trimestre_fin:
            transactions_qs = transactions_qs.filter(date_m__gte=trimestre_debut, date_m__lte=trimestre_fin)
        elif semestre_debut and semestre_fin:
            transactions_qs = transactions_qs.filter(date_m__gte=semestre_debut, date_m__lte=semestre_fin)

        ouvrages_org = _get_scoped_forfaitaire_ouvrage_ids(
            request.user,
            annee=annee,
            gestionnaire_ids=gestionnaire_ids,
        )
        _, ouvrages_org = resolve_dashboard_employee_filter(
            ouvrages_org,
            filter_employe,
        )
        transactions_list = list(transactions_qs)

        # Extraction des ouvrages depuis les descriptions
        transactions_avec_ouvrage = []
        for trans in transactions_list:
            extraction = extraire_ouvrage_et_mois_generique(trans.description or '', '748411')
            mois_extraction = extraction.get('mois')
            if filter_semestre:
                mois_reference = mois_extraction or (trans.date_m.month if trans.date_m else None)
                if not mois_reference or not (semestre_debut.month <= mois_reference <= semestre_fin.month):
                    continue
            elif filter_trimestre:
                if mois_extraction:
                    if _quarter_of_date(date(annee, mois_extraction, 1)) != int(filter_trimestre):
                        continue
                elif trans.date_m and _quarter_of_date(trans.date_m) != int(filter_trimestre):
                    continue
            if extraction['ouvrage_obj']:
                if extraction['ouvrage_obj'].id not in ouvrages_org:
                    continue
                transactions_avec_ouvrage.append({
                    'transaction': trans,
                    'ouvrage': extraction['ouvrage_obj'],
                    'montant': Decimal(str(trans.montant_in)) if trans.montant_in else Decimal('0'),
                    'mois': mois_extraction or (trans.date_m.month if trans.date_m else None),
                })

        pointed_couples_global = {
            (str(numero or '').strip(), str(base or '').strip())
            for numero, base in PaiementForfaitaire.objects.filter(
                point_eau__ouvrage_id__in=ouvrages_org
            ).exclude(
                numeroDiameX__isnull=True
            ).exclude(
                baseDiameX__isnull=True
            ).values_list('numeroDiameX', 'baseDiameX')
            if str(numero or '').strip() and str(base or '').strip()
        }
        transactions_stats_by_ouvrage = defaultdict(lambda: {
            'montant_collecte': Decimal('0'),
            'nb_lignes_diamex_non_pointe': 0,
        })
        transactions_stats_by_ouvrage_mois = defaultdict(
            lambda: defaultdict(lambda: {
                'montant_collecte': Decimal('0'),
                'montant_collecte_non_pointe': Decimal('0'),
            })
        )
        ouvrages_non_pointes_ids = set()
        for tx in transactions_avec_ouvrage:
            ouvrage_id = tx['ouvrage'].id
            tx_stats = transactions_stats_by_ouvrage[ouvrage_id]
            montant_tx = Decimal(str(tx['montant'] or 0))
            tx_stats['montant_collecte'] += montant_tx

            mois_tx = tx.get('mois')
            monthly_tx_stats = None
            if mois_tx:
                monthly_tx_stats = transactions_stats_by_ouvrage_mois[ouvrage_id][mois_tx]
                monthly_tx_stats['montant_collecte'] += montant_tx

            numero_diamex = str(getattr(tx['transaction'], 'id_access', '') or '').strip()
            base_diamex = str(getattr(tx['transaction'], 'prog', '') or '').strip()
            is_pointed = bool(numero_diamex and base_diamex and (numero_diamex, base_diamex) in pointed_couples_global)
            if not is_pointed:
                tx_stats['nb_lignes_diamex_non_pointe'] += 1
                if monthly_tx_stats is not None:
                    monthly_tx_stats['montant_collecte_non_pointe'] += montant_tx
                ouvrages_non_pointes_ids.add(ouvrage_id)

        paiements_forfaitaires_qs = PaiementForfaitaire.objects.filter(
            date_facture__year=annee,
            date_facture__lte=timezone.localdate()
        ).select_related(
            'point_eau',
            'point_eau__ouvrage'
        ).defer(*DEFER_PHOTOS_PAIEMENT)

        paiements_forfaitaires_qs = paiements_forfaitaires_qs.filter(
            point_eau__ouvrage_id__in=ouvrages_org
        )
        if trimestre_debut and trimestre_fin:
            paiements_forfaitaires_qs = paiements_forfaitaires_qs.filter(
                date_facture__gte=trimestre_debut,
                date_facture__lte=trimestre_fin,
            )
        elif semestre_debut and semestre_fin:
            paiements_forfaitaires_qs = paiements_forfaitaires_qs.filter(
                date_facture__gte=semestre_debut,
                date_facture__lte=semestre_fin,
            )

        # L'export mensuel doit aussi inclure les collectes planifiees a venir
        # dans la periode selectionnee (contrairement aux totaux exigibles a date).
        paiements_forfaitaires_export_qs = PaiementForfaitaire.objects.filter(
            date_facture__year=annee,
            point_eau__ouvrage_id__in=ouvrages_org,
        ).select_related('point_eau', 'point_eau__ouvrage').defer(*DEFER_PHOTOS_PAIEMENT)
        if trimestre_debut and trimestre_fin:
            paiements_forfaitaires_export_qs = paiements_forfaitaires_export_qs.filter(
                date_facture__gte=trimestre_debut,
                date_facture__lte=trimestre_fin,
            )
        elif semestre_debut and semestre_fin:
            paiements_forfaitaires_export_qs = paiements_forfaitaires_export_qs.filter(
                date_facture__gte=semestre_debut,
                date_facture__lte=semestre_fin,
            )

        montant_prevu_par_ouvrage = defaultdict(lambda: Decimal('0'))
        paiements_stats_by_ouvrage_mois = defaultdict(
            lambda: defaultdict(lambda: {
                'date_collecte': None,
                'montant_paiement_forfaitaire': Decimal('0'),
                'montant_forfaitaire_non_pointe': Decimal('0'),
            })
        )
        ouvrages_avec_facture_echue = set()
        paiements_par_point_eau = defaultdict(list)
        today = timezone.localdate()
        for paiement in paiements_forfaitaires_qs:
            ouvrage_pf = paiement.point_eau.ouvrage if paiement.point_eau else None
            if not ouvrage_pf:
                continue
            if paiement.point_eau_id:
                paiements_par_point_eau[paiement.point_eau_id].append(paiement)
            montant_paiement = Decimal(str(paiement.montant or 0))
            montant_prevu_par_ouvrage[ouvrage_pf.id] += montant_paiement
            est_paye = paiement.est_paye
            if (not est_paye) and paiement.date_facture and paiement.date_facture <= today:
                ouvrages_avec_facture_echue.add(ouvrage_pf.id)

        ouvrages_non_payes_echus_mois_passes = set()
        ouvrages_non_payes_echus_mois_en_cours = set()
        debut_mois_courant = today.replace(day=1)
        for paiements_point in paiements_par_point_eau.values():
            ouvrage_id = next((
                paiement.point_eau.ouvrage_id
                for paiement in paiements_point
                if paiement.point_eau and paiement.point_eau.ouvrage_id
            ), None)
            if not ouvrage_id:
                continue

            paiements_mois_passes = [
                paiement for paiement in paiements_point
                if paiement.date_facture and paiement.date_facture < debut_mois_courant
            ]
            paiements_mois_en_cours = [
                paiement for paiement in paiements_point
                if paiement.date_facture
                and debut_mois_courant <= paiement.date_facture <= today
            ]

            for paiements_periode, ouvrages_cibles in (
                (paiements_mois_passes, ouvrages_non_payes_echus_mois_passes),
                (paiements_mois_en_cours, ouvrages_non_payes_echus_mois_en_cours),
            ):
                if not paiements_periode:
                    continue
                total_paye = sum(
                    Decimal(str(paiement.montant or 0))
                    for paiement in paiements_periode
                    if paiement.est_paye
                )
                if total_paye <= 0:
                    ouvrages_cibles.add(ouvrage_id)

        for paiement in paiements_forfaitaires_export_qs:
            ouvrage_pf = paiement.point_eau.ouvrage if paiement.point_eau else None
            if not ouvrage_pf or not paiement.date_facture:
                continue
            montant_paiement = Decimal(str(paiement.montant or 0))
            paiement_month_stats = paiements_stats_by_ouvrage_mois[ouvrage_pf.id][paiement.date_facture.month]
            current_date = paiement_month_stats['date_collecte']
            if current_date is None or paiement.date_facture < current_date:
                paiement_month_stats['date_collecte'] = paiement.date_facture
            paiement_month_stats['montant_paiement_forfaitaire'] += montant_paiement
            if not paiement.est_pointe_complet:
                paiement_month_stats['montant_forfaitaire_non_pointe'] += montant_paiement

        # Ouvrages concernés:
        # - réalisé DiameX
        # - paiement forfaitaire facturé
        # - points d'eau forfaitaires (même sans facture/écriture DiameX)
        ouvrages_ids = set([t['ouvrage'].id for t in transactions_avec_ouvrage]) | set(montant_prevu_par_ouvrage.keys())
        _cleanup_stale_cut_forfait_points(ouvrage_ids=ouvrages_org)
        points_eau_forfait_qs = _forfait_points_queryset()
        points_eau_forfait_qs = points_eau_forfait_qs.filter(ouvrage_id__in=ouvrages_org)
        ouvrages_ids |= set(points_eau_forfait_qs.values_list('ouvrage_id', flat=True).distinct())
        ouvrages_ids &= ouvrages_org

        ouvrages_qs = Ouvrage.objects.filter(id__in=ouvrages_ids)

        if filter_ouvrage and filter_ouvrage != 'all':
            ouvrages_qs = ouvrages_qs.filter(id=filter_ouvrage)

        if filter_commune and filter_commune != 'all':
            points_eau_commune = PointEau.objects.filter(
                parcelle__village__fokontany__commune_id=filter_commune
            ).values_list('ouvrage_id', flat=True).distinct()
            ouvrages_qs = ouvrages_qs.filter(id__in=points_eau_commune)

        if filter_district and filter_district != 'all':
            points_eau_district = PointEau.objects.filter(
                parcelle__village__fokontany__commune__district_id=filter_district
            ).values_list('ouvrage_id', flat=True).distinct()
            ouvrages_qs = ouvrages_qs.filter(id__in=points_eau_district)
            
        if filter_region and filter_region != 'all':
            points_eau_region = PointEau.objects.filter(
                parcelle__village__fokontany__commune__district__region_id=filter_region
            ).values_list('ouvrage_id', flat=True).distinct()
            ouvrages_qs = ouvrages_qs.filter(id__in=points_eau_region)

        if filter_non_pointe == '1':
            ouvrages_qs = ouvrages_qs.filter(id__in=ouvrages_non_pointes_ids)

        if filter_statut_echu:
            ouvrages_cibles = (
                ouvrages_non_payes_echus_mois_passes
                if filter_statut_echu == 'non_paye_mois_passes'
                else ouvrages_non_payes_echus_mois_en_cours
            )
            ouvrages_qs = ouvrages_qs.filter(id__in=ouvrages_cibles)

        ouvrages_filtre = list(ouvrages_qs)

        # Explications narratives (optionnel)
        explications_map = {}
        if filter_explication in ['avec', 'sans']:
            explications_qs = ExplicationPaiementForfaitaire.objects.filter(
                annee=annee,
                ouvrage_id__in=[o.id for o in ouvrages_filtre]
            )
            explications_map = {str(e.ouvrage_id): e for e in explications_qs}

        communes_data = {}

        modalite_active_map = _get_modalite_active_map(
            [o.id for o in ouvrages_filtre],
            annee=annee,
            gestionnaire_ids=gestionnaire_ids,
            modalites_paiement=FORFAITAIRE_MODALITES_PAIEMENT
        )
        ouvrages_inclus = []

        for ouvrage in ouvrages_filtre:
            if filter_echu == '1' and ouvrage.id not in ouvrages_avec_facture_echue:
                continue

            # Filtre explication
            if filter_explication in ['avec', 'sans']:
                has_exp = bool(explications_map.get(str(ouvrage.id)) and explications_map[str(ouvrage.id)].explication)
                if (filter_explication == 'avec' and not has_exp) or (filter_explication == 'sans' and has_exp):
                    continue

            points_eau = _apply_forfaitaire_point_eau_geo_filters(
                _forfait_points_queryset().filter(ouvrage_id=ouvrage.id),
                filter_region=filter_region,
                filter_district=filter_district,
                filter_commune=filter_commune,
            ).select_related('parcelle__village__fokontany__commune__district')

            modalite_active = modalite_active_map.get(ouvrage.id)
            trimestres_exigibles = _trimestres_exigibles_depuis_date_debut(
                annee,
                getattr(modalite_active, 'date_debut', None)
            )
            if semestre_debut and semestre_fin:
                trimestres_exigibles = _count_applicable_quarters_in_period(
                    annee,
                    getattr(modalite_active, 'date_debut', None),
                    semestre_debut,
                    semestre_fin,
                    exigible=True,
                )

            total_points_eau = 0
            montant_brut_ouvrage = Decimal('0')
            for pe in points_eau:
                total_points_eau += 1
                tarif = tarif_pour_annee(pe, annee)
                montant_brut_ouvrage += tarif * Decimal(str(trimestres_exigibles))

            decote_ouvrage = calculer_decote_coupures(
                points_eau,
                annee,
                periode_debut=semestre_exigible_debut,
                periode_fin=semestre_exigible_fin,
            )
            montant_a_collecter = montant_brut_ouvrage - decote_ouvrage
            if montant_a_collecter < 0:
                montant_a_collecter = Decimal('0')

            tx_stats = transactions_stats_by_ouvrage.get(ouvrage.id, {})
            montant_collecte = tx_stats.get('montant_collecte', Decimal('0'))
            nb_lignes_diamex_non_pointe = tx_stats.get('nb_lignes_diamex_non_pointe', 0)

            if filter_non_pointe == '1' and nb_lignes_diamex_non_pointe <= 0:
                continue

            has_taux = montant_a_collecter > 0
            taux_ouvrage = int((montant_collecte / montant_a_collecter) * 100) if has_taux else 0
            if filter_taux == 'gt100' and ((not has_taux) or taux_ouvrage <= 100):
                continue
            if filter_taux == '100' and ((not has_taux) or taux_ouvrage != 100):
                continue
            if filter_taux == 'lt100' and ((not has_taux) or taux_ouvrage >= 100):
                continue

            montant_paiement_forfaitaire_ouvrage = montant_prevu_par_ouvrage.get(ouvrage.id, Decimal('0'))
            has_taux_paye_sur_forfaitaire = montant_paiement_forfaitaire_ouvrage > 0
            taux_paye_sur_forfaitaire = int((montant_collecte / montant_paiement_forfaitaire_ouvrage) * 100) if has_taux_paye_sur_forfaitaire else 0

            if filter_taux_forfaitaire == 'gt100':
                if (not has_taux_paye_sur_forfaitaire) or taux_paye_sur_forfaitaire <= 100:
                    continue
            if filter_taux_forfaitaire == '100':
                if (not has_taux_paye_sur_forfaitaire) or taux_paye_sur_forfaitaire != 100:
                    continue
            if filter_taux_forfaitaire == 'lt100':
                if (not has_taux_paye_sur_forfaitaire) or taux_paye_sur_forfaitaire >= 100:
                    continue

            ouvrages_inclus.append(ouvrage)

            # Commune/District/Région depuis le premier point d'eau
            commune = district = region = None
            if points_eau.exists():
                premier_pe = points_eau.first()
                if premier_pe.parcelle and premier_pe.parcelle.village and premier_pe.parcelle.village.fokontany:
                    commune = premier_pe.parcelle.village.fokontany.commune
                    if commune and commune.district:
                        district = commune.district
                        if district.region:
                            region = district.region

            commune_nom = commune.nom_commune if commune else 'Non defini'
            district_nom = district.nom_district if district else 'Non defini'
            region_nom = region.nom_region if region else 'Non defini'
            commune_key = str(commune.id) if commune else f"none-{commune_nom}"

            if commune_key not in communes_data:
                communes_data[commune_key] = {
                    'commune_id': str(commune.id) if commune else None,
                    'commune': commune_nom,
                    'district': district_nom,
                    'region': region_nom,
                    'ouvrages': set(),
                    'nb_points_eau': 0,
                    'total_a_collecter': Decimal('0'),
                    'total_paiement_forfaitaire': Decimal('0'),
                    'total_collecte': Decimal('0')
                }

            row = communes_data[commune_key]
            row['ouvrages'].add(str(ouvrage.id))
            row['nb_points_eau'] += total_points_eau
            row['total_a_collecter'] += montant_a_collecter
            row['total_paiement_forfaitaire'] += montant_paiement_forfaitaire_ouvrage
            row['total_collecte'] += montant_collecte

        communes_list = []
        for row in communes_data.values():
            total_a_collecter = row['total_a_collecter']
            total_paiement_forfaitaire = row['total_paiement_forfaitaire']
            total_collecte = row['total_collecte']
            # Pour la vue "Recouvrement par commune", on compare le collecté
            # au total a collecter apres decote.
            ecart = total_a_collecter - total_collecte
            has_taux = total_a_collecter > 0
            taux = int((total_collecte / total_a_collecter) * 100) if has_taux else None

            communes_list.append({
                'commune_id': row['commune_id'],
                'commune': row['commune'],
                'district': row['district'],
                'region': row['region'],
                    'nb_ouvrages': len(row['ouvrages']),
                    'nb_points_eau': row['nb_points_eau'],
                    'total_a_collecter': float(total_a_collecter),
                    'total_paiement_forfaitaire': float(total_paiement_forfaitaire),
                    'total_collecte': float(total_collecte),
                    'ecart': float(ecart),
                    'taux': taux
                })

        communes_list.sort(
            key=lambda item: (item.get('region') or '', item.get('district') or '', item.get('commune') or '')
        )

        collectes_mensuelles = []
        for ouvrage in ouvrages_inclus:
            mois_disponibles = sorted(
                set(transactions_stats_by_ouvrage_mois.get(ouvrage.id, {}).keys())
                | set(paiements_stats_by_ouvrage_mois.get(ouvrage.id, {}).keys())
            )
            for mois in mois_disponibles:
                collecte_stats = transactions_stats_by_ouvrage_mois.get(ouvrage.id, {}).get(mois, {})
                paiement_stats = paiements_stats_by_ouvrage_mois.get(ouvrage.id, {}).get(mois, {})
                date_collecte = paiement_stats.get('date_collecte') or date(annee, int(mois), 1)
                collectes_mensuelles.append({
                    'ouvrage_id': str(ouvrage.id),
                    'mois': mois,
                    'date_collecte': date_collecte.isoformat(),
                    'montant_paiement_forfaitaire': float(
                        paiement_stats.get('montant_paiement_forfaitaire', Decimal('0'))
                    ),
                    'montant_forfaitaire_non_pointe': float(
                        paiement_stats.get('montant_forfaitaire_non_pointe', Decimal('0'))
                    ),
                    'montant_collecte': float(
                        collecte_stats.get('montant_collecte', Decimal('0'))
                    ),
                    'montant_collecte_non_pointe': float(
                        collecte_stats.get('montant_collecte_non_pointe', Decimal('0'))
                    ),
                })

        return JsonResponse({
            'success': True,
            'communes': communes_list,
            'collectes_mensuelles': collectes_mensuelles,
            'total': len(communes_list)
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
def api_save_explication_forfaitaire(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        ouvrage_id = data.get('ouvrage_id')
        annee = int(data.get('annee'))
        explication = (data.get('explication') or '').strip()

        if not ouvrage_id or not annee:
            return JsonResponse({'success': False, 'error': 'Paramètres manquants'}, status=400)

        allowed_ouvrage_ids = _get_scoped_forfaitaire_ouvrage_ids(
            request.user,
            annee=annee,
            apply_responsable_scope=False,
        )
        if str(ouvrage_id) not in {str(item) for item in allowed_ouvrage_ids}:
            return JsonResponse({'success': False, 'error': 'Accès refusé Ã  cet ouvrage'}, status=403)

        employe = None
        if hasattr(request.user, 'employe'):
            employe = request.user.employe

        obj, created = ExplicationPaiementForfaitaire.objects.get_or_create(
            ouvrage_id=ouvrage_id,
            annee=annee,
            defaults={
                'explication': explication,
                'created_by': employe,
                'updated_by': employe
            }
        )
        if not created:
            obj.explication = explication
            obj.updated_by = employe
            obj.save(update_fields=['explication', 'updated_by', 'updated_at'])

        return JsonResponse({
            'success': True,
            'explication': obj.explication
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def calculer_decote_coupures(
    points_eau_qs,
    annee,
    trimestre=None,
    periode_debut=None,
    periode_fin=None,
):
    """
    Calcule la décote totale pour les coupures d'eau d'une liste de points d'eau

    Règle : la décote se compte par tranches pleines de 3 mois de coupure.
    - 1 ou 2 mois coupés => pas de décote
    - 3, 4 ou 5 mois coupés => 1 x tarif forfaitaire
    - 6, 7 ou 8 mois coupés => 2 x tarif forfaitaire
    etc.

    Args:
        points_eau_qs: QuerySet ou liste de PointEau
        annee: Année de référence pour le calcul

    Returns:
        Decimal: Montant total de la décote
    """
    decote_totale = Decimal('0')

    # Dates de début et fin d'année
    debut_annee = datetime(annee, 1, 1).date()
    fin_annee = datetime(annee, 12, 31).date()
    if periode_debut and periode_fin:
        debut_annee = max(debut_annee, periode_debut)
        fin_annee = min(fin_annee, periode_fin)

    for pe in points_eau_qs:
        tarif = tarif_pour_annee(pe, annee)
        if tarif == 0:
            continue

        periodes_coupure = []
        
        # 1. Déterminer l'état au 1er janvier
        # Chercher le dernier événement AVANT le début de l'année
        dernier_evt_avant = CoupureEau.objects.filter(
            point_eau=pe,
            date_evenement__lt=debut_annee
        ).order_by('-date_evenement').first()

        est_coupe_debut_annee = False
        date_debut_coupure = None

        if dernier_evt_avant and dernier_evt_avant.type_evenement == 'coupure':
            est_coupe_debut_annee = True
            date_debut_coupure = debut_annee  # La coupure court depuis le début de l'année

        # 2. Récupérer les événements DE l'année
        evenements_annee = CoupureEau.objects.filter(
            point_eau=pe,
            date_evenement__gte=debut_annee,
            date_evenement__lte=fin_annee,
        ).order_by('date_evenement')

        # 3. Parcourir les événements
        for evt in evenements_annee:
            if evt.type_evenement == 'remise':
                if est_coupe_debut_annee:
                    # Fin d'une coupure commencée avant ou au début de l'année
                    periodes_coupure.append({
                        'debut': date_debut_coupure,
                        'fin': evt.date_evenement
                    })
                    est_coupe_debut_annee = False
                    date_debut_coupure = None
                elif date_debut_coupure:
                     # Fin d'une coupure commencée dans l'année
                    periodes_coupure.append({
                        'debut': date_debut_coupure,
                        'fin': evt.date_evenement
                    })
                    date_debut_coupure = None
                
            elif evt.type_evenement == 'coupure':
                # Nouvelle coupure (ou correction de données)
                if not est_coupe_debut_annee and not date_debut_coupure:
                    date_debut_coupure = evt.date_evenement
                # Si déjà coupé, on ignore ce doublon potentiel ou on met à jour ?
                # Pour simplicité, on suppose que la première coupure fait foi si pas de remise

        # 4. Gérer le cas où c'est encore coupé à la fin de l'année
        if est_coupe_debut_annee or date_debut_coupure:
            debut = date_debut_coupure if date_debut_coupure else debut_annee
            periodes_coupure.append({
                'debut': debut,
                'fin': fin_annee
            })

        # Calculer la durée et la décote pour chaque période
        for periode in periodes_coupure:
            debut_p = max(periode['debut'], debut_annee)
            fin_p = min(periode['fin'], fin_annee)
            if fin_p <= debut_p:
                continue

            # Calculer la durée en jours
            duree = fin_p - debut_p
            jours = duree.days

            # Arrondir au mois le plus proche (moyenne de 30.4 jours par mois)
            nb_mois = int(round(jours / 30.4))

            # Appliquer la décote par blocs complets de 3 mois.
            nb_tranches_decote = nb_mois // 3
            decote_periode = tarif * nb_tranches_decote
            decote_totale += decote_periode

    return decote_totale


def calculer_tranches_attendues(point_eau, annee, trimestre=None, date_debut_modalite=None):
    """
    Nombre de tranches (trimestres) attendues pour un point d'eau sur l'annee
    (ou le trimestre selectionne), deduction faite des trimestres sans eau.

    Si la modalite de gestion de l'ouvrage a debute en cours d'annee (ex: 1er
    septembre 2026), le nombre de tranches de base n'est plus 4 mais le nombre
    de trimestres restants depuis ce debut (ex: 2 pour un debut en septembre).
    """
    debut_annee = datetime(annee, 1, 1).date()
    fin_annee = datetime(annee, 12, 31).date()
    debut_trimestre, fin_trimestre = _get_quarter_bounds(annee, trimestre)
    if debut_trimestre and fin_trimestre:
        debut_annee = max(debut_annee, debut_trimestre)
        fin_annee = min(fin_annee, fin_trimestre)

    if trimestre:
        tranches_planifiees_base = _get_selected_trimestres_planifies_depuis_date_debut(
            annee, date_debut_modalite, trimestre
        )
    else:
        tranches_planifiees_base = _trimestres_planifies_depuis_date_debut(annee, date_debut_modalite)

    if date_debut_modalite and date_debut_modalite > debut_annee:
        if date_debut_modalite > fin_annee:
            return 0, 0
        debut_annee = date_debut_modalite

    dernier_evt_avant = CoupureEau.objects.filter(
        point_eau=point_eau,
        date_evenement__lt=debut_annee
    ).order_by('-date_evenement').first()

    est_coupe_debut_annee = bool(dernier_evt_avant and dernier_evt_avant.type_evenement == 'coupure')
    date_debut_coupure = debut_annee if est_coupe_debut_annee else None

    evenements_annee = CoupureEau.objects.filter(
        point_eau=point_eau,
        date_evenement__year=annee,
        date_evenement__gte=debut_annee,
        date_evenement__lte=fin_annee,
    ).order_by('date_evenement')

    periodes_coupure = []
    for evt in evenements_annee:
        if evt.type_evenement == 'remise':
            if est_coupe_debut_annee:
                periodes_coupure.append({'debut': date_debut_coupure, 'fin': evt.date_evenement})
                est_coupe_debut_annee = False
                date_debut_coupure = None
            elif date_debut_coupure:
                periodes_coupure.append({'debut': date_debut_coupure, 'fin': evt.date_evenement})
                date_debut_coupure = None
        elif evt.type_evenement == 'coupure':
            if not est_coupe_debut_annee and not date_debut_coupure:
                date_debut_coupure = evt.date_evenement

    if est_coupe_debut_annee or date_debut_coupure:
        periodes_coupure.append({'debut': date_debut_coupure or debut_annee, 'fin': fin_annee})

    trimestres_sans_eau = 0
    for periode in periodes_coupure:
        jours = max(0, (periode['fin'] - periode['debut']).days)
        trimestres_sans_eau += int(round(jours / 91.25))

    trimestres_sans_eau = max(0, min(tranches_planifiees_base, trimestres_sans_eau))
    return max(0, tranches_planifiees_base - trimestres_sans_eau), trimestres_sans_eau


def _get_tranches_realisees_qs(points_eau, annee, trimestre_debut=None, trimestre_fin=None):
    """Factures planifiees utilisees uniquement pour le controle des tranches du modal.

    Ce controle doit tenir compte de toutes les factures de la periode, y compris
    celles dont la date n'est pas encore echue. Les autres donnees du dashboard
    continuent d'appliquer leur filtre d'exigibilite.
    """
    qs = PaiementForfaitaire.objects.filter(
        point_eau__in=points_eau,
        date_facture__year=annee,
    )
    if trimestre_debut and trimestre_fin:
        qs = qs.filter(
            date_facture__gte=trimestre_debut,
            date_facture__lte=trimestre_fin,
        )
    return qs


@login_required
def api_details_ouvrage_forfaitaire(request, ouvrage_id):
    """
    API pour récupérer les détails complets d'un ouvrage pour le modal

    Retourne :
    - Informations de l'ouvrage
    - Liste des points d'eau avec leurs tarifs et coupures
    - Répartition mensuelle des paiements
    """
    try:
        annee = int(request.GET.get('annee', datetime.now().year))
        filter_trimestre = request.GET.get('trimestre', '')
        trimestre_debut, trimestre_fin = _get_quarter_bounds(annee, filter_trimestre)
        if filter_trimestre and not trimestre_debut:
            filter_trimestre = ''
        allowed_ouvrage_ids = set(
            str(item)
            for item in _get_scoped_forfaitaire_ouvrage_ids(
                request.user,
                annee=annee,
            )
        )
        allowed_ouvrage_ids.add(str(ouvrage_id))

        if str(ouvrage_id) not in {str(item) for item in allowed_ouvrage_ids}:
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé Ã  cet ouvrage'
            }, status=403)

        try:
            ouvrage = Ouvrage.objects.get(id=ouvrage_id)
        except Ouvrage.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage introuvable'
            }, status=404)

        points_eau = PointEau.objects.filter(
            ouvrage_id=ouvrage.id
        ).filter(
            Q(tarifforfaitaire__isnull=False, tarifforfaitaire__gt=0)
            | Q(paiements_forfaitaires__isnull=False)
            | Q(coupures_eau__isnull=False)
        ).distinct().select_related('ouvrage').defer('photos')

        # Date de debut de la modalite de gestion en cours: si elle tombe dans
        # l'annee affichee, le nombre de tranches attendues doit etre reduit
        # en consequence (cf. calculer_tranches_attendues).
        modalite_active = _get_modalite_active_map(
            [ouvrage.id],
            annee=annee,
            gestionnaire_ids=None,
            modalites_paiement=FORFAITAIRE_MODALITES_PAIEMENT,
        ).get(ouvrage.id)
        date_debut_modalite = getattr(modalite_active, 'date_debut', None)

        reference_date = _get_dashboard_reference_date(annee)
        points_eau = list(points_eau)
        derniers_evenements_coupure = _latest_cut_events_by_point(
            points_eau,
            reference_date,
        )

        # Nombre de tranches (factures) deja enregistrees par point d'eau sur la periode filtree,
        # utilise pour le controle de conformite "tranches attendues vs realisees" (cf. dashboard_payments_flat).
        tranches_realisees_qs = _get_tranches_realisees_qs(
            points_eau,
            annee,
            trimestre_debut=trimestre_debut,
            trimestre_fin=trimestre_fin,
        )
        tranches_realisees_par_point = defaultdict(int)
        for point_eau_id, quantite in tranches_realisees_qs.values_list('point_eau_id', 'quantite'):
            tranches_realisees_par_point[str(point_eau_id)] += int(quantite or 0)

        # Total cumule depuis toujours (pas seulement l'annee affichee) : utilise
        # pour projeter la prochaine echeance quand un point a paye d'avance
        # (ex: 4 tranches payees en une fois couvrent 12 mois a partir du debut
        # de la modalite, meme si elles depassent le nombre attendu cette annee).
        borne_sup_cumul = trimestre_fin or date(annee, 12, 31)
        tranches_realisees_cumul_qs = PaiementForfaitaire.objects.filter(
            point_eau__in=points_eau,
            date_facture__lte=borne_sup_cumul,
        )
        tranches_realisees_cumul_par_point = defaultdict(int)
        for point_eau_id, quantite in tranches_realisees_cumul_qs.values_list('point_eau_id', 'quantite'):
            tranches_realisees_cumul_par_point[str(point_eau_id)] += int(quantite or 0)

        points_eau_data = []
        total_points_eau = 0
        for pe in points_eau:
            total_points_eau += 1
            tarif = tarif_pour_annee(pe, annee)
            dernier_evenement = derniers_evenements_coupure.get(str(pe.id))
            coupures = CoupureEau.objects.filter(
                point_eau=pe,
                date_evenement__year=annee
            ).order_by('date_evenement')
            coupures_data = [{
                'type': coupure.type_evenement,
                'date': coupure.date_evenement.strftime('%d/%m/%Y'),
                'motif': (coupure.get_raison_display() if coupure.raison else (coupure.notes or '-'))
            } for coupure in coupures]
            est_coupe_actuellement, date_arret_value = _resolve_point_cut_state(
                pe,
                latest_event=dernier_evenement,
                reference_date=reference_date,
            )
            date_arret_branchement = (
                date_arret_value.strftime('%Y-%m-%d')
                if date_arret_value else None
            )
            tranches_attendues, trimestres_sans_eau = calculer_tranches_attendues(
                pe,
                annee,
                trimestre=filter_trimestre or None,
                date_debut_modalite=date_debut_modalite,
            )

            tranches_realisees = tranches_realisees_par_point.get(str(pe.id), 0)
            tranches_ecart = tranches_realisees - tranches_attendues
            prochaine_echeance = None
            if tranches_ecart == 0:
                tranches_controle_badge = 'success'
                tranches_controle_action = 'Conforme'
            elif tranches_ecart < 0:
                tranches_controle_badge = 'warning'
                tranches_controle_action = f'Ajouter {abs(tranches_ecart)}'
            else:
                # Un paiement qui depasse le nombre de tranches attendues cette
                # annee n'est pas une erreur a corriger : il s'agit d'une avance
                # dont la couverture court au-dela de l'annee en cours. On
                # projette la prochaine echeance a partir du cumul de tranches
                # payees depuis le debut de la modalite (3 mois par tranche).
                tranches_realisees_cumul = tranches_realisees_cumul_par_point.get(str(pe.id), tranches_realisees)
                ancrage_echeance = date_debut_modalite or date(annee, 1, 1)
                prochaine_echeance_date = ancrage_echeance + relativedelta(months=3 * tranches_realisees_cumul)
                prochaine_echeance = prochaine_echeance_date.strftime('%d/%m/%Y')
                tranches_controle_badge = 'info'
                tranches_controle_action = f"Payé d'avance jusqu'en {prochaine_echeance_date.strftime('%m/%Y')}"

            points_eau_data.append({
                'id': str(pe.id),
                'nom': pe.nomabonne or pe.code_point_eau or '-',
                'code': pe.code_point_eau or '-',
                'tarif_trimestriel': float(tarif),
                'est_coupe_actuellement': est_coupe_actuellement,
                'date_arret_branchement': date_arret_branchement,
                'dernier_evenement_type': dernier_evenement.type_evenement if dernier_evenement else None,
                'dernier_evenement_date': dernier_evenement.date_evenement.strftime('%Y-%m-%d') if dernier_evenement and dernier_evenement.date_evenement else None,
                'tranches_attendues': tranches_attendues,
                'tranches_realisees': tranches_realisees,
                'tranches_ecart': tranches_ecart,
                'tranches_controle_badge': tranches_controle_badge,
                'tranches_controle_action': tranches_controle_action,
                'prochaine_echeance': prochaine_echeance,
                'trimestres_sans_eau': trimestres_sans_eau,
                'nb_coupures': len(coupures_data),
                'coupures': coupures_data
            })

        paiements_forfaitaires_qs = PaiementForfaitaire.objects.filter(
            point_eau__ouvrage_id=ouvrage.id,
            date_facture__year=annee,
            date_facture__lte=timezone.localdate()
        ).select_related('point_eau', 'planning').defer(*DEFER_PHOTOS_PAIEMENT_PLANNING).order_by('date_facture', 'created_at')
        if trimestre_debut and trimestre_fin:
            paiements_forfaitaires_qs = paiements_forfaitaires_qs.filter(
                date_facture__gte=trimestre_debut,
                date_facture__lte=trimestre_fin,
            )

        paiements_forfaitaires_data = []
        montant_prevu_total = Decimal('0')
        montant_prevu_mensuel = defaultdict(lambda: Decimal('0'))
        pointed_couples = set()
        latest_paid_forfait_by_point_eau = {}

        for paiement in paiements_forfaitaires_qs:
            montant = Decimal(str(paiement.montant or 0))
            montant_prevu_total += montant
            if paiement.date_facture:
                montant_prevu_mensuel[paiement.date_facture.month] += montant

            effective_payment_date = paiement.effective_payment_date
            paiement_latest_cut_event = (
                derniers_evenements_coupure.get(str(paiement.point_eau_id))
                if paiement.point_eau_id else None
            )
            paiement_point_is_cut, paiement_cut_date = (
                _resolve_point_cut_state(
                    paiement.point_eau,
                    latest_event=paiement_latest_cut_event,
                    reference_date=reference_date,
                )
                if paiement.point_eau else (False, None)
            )
            if paiement.point_eau_id and paiement.est_paye and effective_payment_date:
                current_latest_paid = latest_paid_forfait_by_point_eau.get(paiement.point_eau_id)
                if current_latest_paid is None or effective_payment_date > current_latest_paid:
                    latest_paid_forfait_by_point_eau[paiement.point_eau_id] = effective_payment_date

            numero_diamex = (paiement.numeroDiameX or '').strip()
            base_diamex = (paiement.baseDiameX or '').strip()
            if numero_diamex and base_diamex:
                pointed_couples.add((numero_diamex, base_diamex))

            paiements_forfaitaires_data.append({
                'id': str(paiement.id),
                'date_facture': paiement.date_facture.strftime('%d/%m/%Y') if paiement.date_facture else '-',
                'date_facture_iso': paiement.date_facture.strftime('%Y-%m-%d') if paiement.date_facture else None,
                'mois': paiement.date_facture.month if paiement.date_facture else None,
                'point_eau': paiement.point_eau.nomabonne if paiement.point_eau and paiement.point_eau.nomabonne else (paiement.point_eau.code_point_eau if paiement.point_eau else '-'),
                'point_eau_id': str(paiement.point_eau_id) if paiement.point_eau_id else '',
                'point_eau_idxls': str(paiement.point_eau.idxls) if paiement.point_eau and paiement.point_eau.idxls else '-',
                'point_eau_est_coupe': paiement_point_is_cut,
                'has_cut_status_anomaly': bool(
                    paiement.est_paye
                    and paiement_point_is_cut
                    and paiement_cut_date
                    and effective_payment_date
                    and effective_payment_date >= paiement_cut_date
                ),
                'date_paiement_effective': effective_payment_date.strftime('%d/%m/%Y') if effective_payment_date else '',
                'date_arret_branchement': (
                    paiement_cut_date.strftime('%d/%m/%Y')
                    if paiement_cut_date else ''
                ),
                'quantite': int(paiement.quantite or 0),
                'prix_unitaire': float(paiement.prix_unitaire or 0),
                'montant': float(montant),
                'planning_id': str(paiement.planning_id) if paiement.planning_id else '',
                'numeroDiameX': paiement.numeroDiameX or '',
                'baseDiameX': paiement.baseDiameX or '',
                'est_pointe': bool(numero_diamex and base_diamex),
            })

        points_eau_paid_cut_alerts = []
        for pe in points_eau:
            paid_cut_alert = _get_paid_cut_alert(
                pe,
                latest_paid_forfait_by_point_eau.get(pe.id),
                latest_event=derniers_evenements_coupure.get(str(pe.id)),
                reference_date=reference_date,
            )
            if paid_cut_alert:
                points_eau_paid_cut_alerts.append({
                    'point_eau_id': str(pe.id),
                    'point_eau_nom': pe.nomabonne or pe.code_point_eau or '-',
                    'date_arret': paid_cut_alert['date_arret'].strftime('%d/%m/%Y'),
                    'date_paiement': paid_cut_alert['date_paiement'].strftime('%d/%m/%Y'),
                })

        transactions_qs = BaseDiameX.objects.filter(
            compte_code='748411',
            date_m__year=annee
        )

        transactions_data = []
        montant_collecte = Decimal('0')
        montant_collecte_mensuel = defaultdict(lambda: Decimal('0'))
        base_cache = {}

        def _resolve_scan_path(scan_value, prog_value):
            scan_raw = (scan_value or '').strip()
            if not scan_raw:
                return ''

            scan_clean = scan_raw.lstrip('#')
            if (
                (len(scan_clean) > 2 and scan_clean[1] == ':' and scan_clean[2] in ('\\', '/')) or
                scan_clean.startswith('\\\\') or
                scan_clean.startswith('/')
            ):
                return scan_clean

            prog_key = (prog_value or '').strip()
            if not prog_key:
                return scan_clean

            if prog_key not in base_cache:
                base_cache[prog_key] = (EmployeBaseDiameX.objects.filter(base_diamex__icontains=prog_key).first())

            employe_base = base_cache.get(prog_key)
            chemin_base = (employe_base.chemin_base_diamex or '').strip() if employe_base else ''
            if not chemin_base:
                return scan_clean

            scan_rel = scan_clean[2:] if scan_clean.startswith('./') or scan_clean.startswith('.\\') else scan_clean.lstrip('.')
            return os.path.normpath(os.path.join(chemin_base, scan_rel.lstrip('\\/')))

        for trans in transactions_qs:
            extraction = extraire_ouvrage_et_mois_generique(trans.description or '', '748411')
            ouvrage_obj = extraction.get('ouvrage_obj')
            if not ouvrage_obj or ouvrage_obj.id != ouvrage.id:
                continue

            montant_trans = Decimal(str(trans.montant_in or 0))
            montant_collecte += montant_trans
            if trans.date_m:
                montant_collecte_mensuel[trans.date_m.month] += montant_trans

            numero_diamex = str(trans.id_access).strip() if trans.id_access is not None else ''
            base_diamex = (trans.prog or '').strip()
            already_pointed = bool(numero_diamex and base_diamex and (numero_diamex, base_diamex) in pointed_couples)
            scan_path = _resolve_scan_path(trans.scan, trans.prog)

            transactions_data.append({
                'id': trans.id,
                'entry_id': trans.id,
                'id_access': numero_diamex,
                'date_rec': trans.date_rec.strftime('%d/%m/%Y') if trans.date_rec else '-',
                'date': trans.date_m.strftime('%d/%m/%Y') if trans.date_m else '-',
                'description': trans.description or '',
                'montant_in': float(montant_trans),
                'mois': extraction.get('mois') or (trans.date_m.month if trans.date_m else None),
                'prog': trans.prog or '',
                'scan': trans.scan or '',
                'scan_path': scan_path,
                'rec': trans.rec or '',
                'already_pointed': already_pointed,
            })

        # Comparaison globale par couple (ID/prog DiameX vs Numero/Base PaiementForfaitaire)
        def _pair_key(num, base):
            return f"{str(num or '').strip().lower()}||{str(base or '').strip().lower()}"

        diamex_couples = set()
        for tx in transactions_data:
            numero = str(tx.get('id_access') or '').strip()
            base = str(tx.get('prog') or '').strip()
            if numero and base:
                diamex_couples.add((numero, base))

        common_couples = pointed_couples.intersection(diamex_couples)
        matching_couples_stats = []

        if common_couples:
            q_pf = Q()
            q_diamex = Q()
            for numero_diamex, base_diamex in common_couples:
                q_pf |= Q(numeroDiameX=numero_diamex, baseDiameX=base_diamex)
                q_diamex |= Q(id_access=numero_diamex, prog=base_diamex)

            pf_global_rows = PaiementForfaitaire.objects.filter(
                q_pf,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids,
                montant__isnull=False
            ).values('numeroDiameX', 'baseDiameX').annotate(total=Sum('montant'))

            diamex_global_rows = BaseDiameX.objects.filter(
                q_diamex,
                compte_code='748411',
                montant_in__isnull=False
            ).values('id_access', 'prog').annotate(total=Sum('montant_in'))

            pf_totals = {
                _pair_key(row['numeroDiameX'], row['baseDiameX']): Decimal(str(row['total'] or 0))
                for row in pf_global_rows
            }
            diamex_totals = {
                _pair_key(row['id_access'], row['prog']): Decimal(str(row['total'] or 0))
                for row in diamex_global_rows
            }

            for numero_diamex, base_diamex in sorted(common_couples, key=lambda x: (x[0], x[1])):
                key = _pair_key(numero_diamex, base_diamex)
                total_pf_global = pf_totals.get(key, Decimal('0'))
                total_diamex_global = diamex_totals.get(key, Decimal('0'))
                ecart_global = total_pf_global - total_diamex_global
                matching_couples_stats.append({
                    'numero_diamex': numero_diamex,
                    'base_diamex': base_diamex,
                    'pair_key': key,
                    'total_forfaitaires_global': float(total_pf_global),
                    'total_diamex_global': float(total_diamex_global),
                    'ecart_global': float(ecart_global),
                })

        recouvrement_mensuel = {}
        for mois in range(1, 13):
            montant_mois_prevu = montant_prevu_mensuel.get(mois, Decimal('0'))
            montant_mois_collecte = montant_collecte_mensuel.get(mois, Decimal('0'))
            taux_mois = int((montant_mois_collecte / montant_mois_prevu) * 100) if montant_mois_prevu > 0 else 0
            recouvrement_mensuel[mois] = {
                'mois': mois,
                'mois_nom': ['Jan', 'Fev', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aou', 'Sep', 'Oct', 'Nov', 'Dec'][mois - 1],
                'prevu': float(montant_mois_prevu),
                'collecte': float(montant_mois_collecte),
                'taux': taux_mois,
            }

        has_taux = montant_prevu_total > 0
        taux = int((montant_collecte / montant_prevu_total) * 100) if has_taux else None
        explication_obj = ExplicationPaiementForfaitaire.objects.filter(
            ouvrage_id=ouvrage.id,
            annee=annee
        ).first()
        auto_pointage = build_auto_pointage_forfaitaire_suggestions(
            paiements_forfaitaires_data,
            transactions_data,
        )

        return JsonResponse({
            'success': True,
            'ouvrage': {
                'id': str(ouvrage.id),
                'nom': ouvrage.nom_ouvrage,
                'est_saisonnier': ouvrage.saisonnier,
                'date_debut_gestion': date_debut_modalite.strftime('%Y-%m-%d') if date_debut_modalite else None,
                'date_debut_gestion_annee_courante': bool(date_debut_modalite and date_debut_modalite.year == annee),
                'nb_points_eau': total_points_eau,
                'montant_brut': float(montant_prevu_total),
                'decote_totale': 0.0,
                'montant_a_collecter': float(montant_prevu_total),
                'montant_collecte': float(montant_collecte),
                'ecart': float(montant_prevu_total - montant_collecte),
                'taux': taux,
                'has_taux': has_taux,
                'nb_points_eau_payes_coupes': len(points_eau_paid_cut_alerts),
                'has_paid_cut_alert': bool(points_eau_paid_cut_alerts),
                'paid_cut_alert_points': points_eau_paid_cut_alerts,
                'explication': explication_obj.explication if explication_obj else ''
            },
            'points_eau': points_eau_data,
            'paiements': transactions_data,
            'paiements_forfaitaires': paiements_forfaitaires_data,
            'transactions_diamex': transactions_data,
            'auto_pointage': auto_pointage,
            'matching_couples_stats': matching_couples_stats,
            'can_manage_forfaitaire_factures': can_manage_forfaitaire_factures(request.user),
            'recouvrement_mensuel': list(recouvrement_mensuel.values()),
            'stats': {
                'nb_paiements_forfaitaires': len(paiements_forfaitaires_data),
                'nb_transactions_diamex': len(transactions_data),
                'total_prevu': float(montant_prevu_total),
                'total_diamex': float(montant_collecte),
                'ecart': float(montant_prevu_total - montant_collecte),
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_pointage_paiements_forfaitaires(request):
    """
    Pointe un lot de PaiementForfaitaire sur une ligne DiameX 748411.
    Le couple (ID Access, Prog) de la ligne DiameX est recopie
    vers (numeroDiameX, baseDiameX) sur toutes les lignes selectionnees.
    """
    try:
        data = json.loads(request.body)
        raw_paiement_ids = data.get('paiement_ids') or []
        diamex_entry_id = data.get('diamex_entry_id')
        montant_diamex_selection = data.get('montant_diamex_selection')
        annee_raw = data.get('annee')

        if not isinstance(raw_paiement_ids, list) or not raw_paiement_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucune ligne forfaitaire selectionnee'
            }, status=400)
        if not diamex_entry_id:
            return JsonResponse({
                'success': False,
                'error': 'Ligne DiameX manquante'
            }, status=400)

        try:
            annee = int(annee_raw) if annee_raw else timezone.localdate().year
        except (TypeError, ValueError):
            annee = timezone.localdate().year

        allowed_ouvrage_ids = _get_scoped_forfaitaire_ouvrage_ids(
            request.user,
            annee=annee,
        )

        try:
            diamex_entry = BaseDiameX.objects.get(id=int(diamex_entry_id))
        except (BaseDiameX.DoesNotExist, ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Ligne DiameX introuvable'
            }, status=404)

        if (diamex_entry.compte_code or '') != '748411':
            return JsonResponse({
                'success': False,
                'error': "La ligne selectionnee n'est pas du compte 748411"
            }, status=400)

        extraction = extraire_ouvrage_et_mois_generique(diamex_entry.description or '', '748411')
        ouvrage_diamex = extraction.get('ouvrage_obj') if extraction else None
        if not ouvrage_diamex or ouvrage_diamex.id not in allowed_ouvrage_ids:
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé Ã  cette ligne DiameX'
            }, status=403)

        numero_diamex = str(diamex_entry.id_access or '').strip()
        base_diamex = (diamex_entry.prog or '').strip()
        if not numero_diamex:
            return JsonResponse({
                'success': False,
                'error': 'ID DiameX introuvable sur la ligne selectionnee'
            }, status=400)
        if not base_diamex:
            return JsonResponse({
                'success': False,
                'error': 'Prog/Base DiameX introuvable sur la ligne selectionnee'
            }, status=400)

        paiement_ids = list(dict.fromkeys(str(pid).strip() for pid in raw_paiement_ids if str(pid).strip()))
        paiements = list(
            PaiementForfaitaire.objects.filter(
                id__in=paiement_ids,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids,
            ).select_related('point_eau').defer(*DEFER_PHOTOS_PAIEMENT)
        )
        if len(paiements) != len(paiement_ids):
            return JsonResponse({
                'success': False,
                'error': 'Une ou plusieurs lignes forfaitaires sont introuvables ou hors scope'
            }, status=404)

        paiement_months = {
            paiement.date_facture.month
            for paiement in paiements
            if paiement.date_facture
        }
        if len(paiement_months) != 1:
            return JsonResponse({
                'success': False,
                'error': 'Le pointage forfaitaire doit porter sur des lignes d un seul mois.'
            }, status=400)
        paiement_month = next(iter(paiement_months), None)

        total_paiements = sum(Decimal(str(p.montant or 0)) for p in paiements)
        montant_diamex = Decimal(str(diamex_entry.montant_in or 0))
        if montant_diamex_selection is not None:
            try:
                montant_selection = Decimal(str(montant_diamex_selection))
                if Decimal('0') < montant_selection <= montant_diamex:
                    montant_diamex = montant_selection
            except Exception:
                pass

        ecart = total_paiements - montant_diamex
        if abs(ecart) > Decimal('0.01'):
            return JsonResponse({
                'success': False,
                'error': (
                    f"Pointage impossible: total forfaitaire ({total_paiements}) "
                    f"!= montant DiameX ({montant_diamex})"
                ),
                'total_paiements': float(total_paiements),
                'montant_diamex': float(montant_diamex),
                'ecart': float(ecart),
            }, status=400)

        extraction_mois = extraction.get('mois') if extraction else None
        mois_diamex = extraction_mois or (diamex_entry.date_m.month if diamex_entry.date_m else None)
        if paiement_month and mois_diamex and paiement_month != mois_diamex:
            return JsonResponse({
                'success': False,
                'error': 'Le pointage forfaitaire est autorise uniquement avec une ligne DiameX du meme mois.'
            }, status=400)

        with transaction.atomic():
            auto_remises = []
            for paiement in paiements:
                planning_obj = getattr(paiement, 'planning', None)
                point_eau_obj = getattr(paiement, 'point_eau', None)
                planning_ouvrage_id = getattr(planning_obj, 'ouvrage_id', None)
                point_eau_ouvrage_id = getattr(point_eau_obj, 'ouvrage_id', None)
                if (
                    paiement.planning_id
                    and point_eau_ouvrage_id
                    and planning_ouvrage_id
                    and planning_ouvrage_id != point_eau_ouvrage_id
                ):
                    paiement.planning = _find_or_create_matching_forfaitaire_planning(
                        point_eau=point_eau_obj,
                        date_facture=paiement.date_facture,
                        employe=getattr(planning_obj, 'employe', None),
                    )
                paiement.numeroDiameX = numero_diamex
                paiement.baseDiameX = base_diamex
                update_fields = ['numeroDiameX', 'baseDiameX', 'updated_at']
                if paiement.planning_id:
                    update_fields.append('planning')
                paiement.save(update_fields=update_fields)
                if getattr(paiement, '_auto_remise_effectuee', False):
                    auto_remises.append(
                        paiement.point_eau.nomabonne if paiement.point_eau and paiement.point_eau.nomabonne
                        else str(paiement.point_eau_id or paiement.id)
                    )
                close_forfaitaire_conversation(
                    paiement,
                    actor=getattr(request.user, 'employe', None),
                    reason='Paiement enregistre en comptabilite (pointage 748411). Discussion archivee.',
                )

            # Verification defensive : toutes les lignes doivent porter le meme couple.
            synced_rows = PaiementForfaitaire.objects.filter(id__in=paiement_ids).values(
                'id', 'numeroDiameX', 'baseDiameX'
            )
            unsynced = [
                str(row['id']) for row in synced_rows
                if (row.get('numeroDiameX') or '').strip() != numero_diamex
                or (row.get('baseDiameX') or '').strip() != base_diamex
            ]
            if unsynced:
                raise ValueError(
                    f"Pointage incomplet: {len(unsynced)} ligne(s) n'ont pas recu le couple DiameX."
                )

        return JsonResponse({
            'success': True,
            'message': (
                f'Pointage applique a {len(paiements)} paiement(s) forfaitaire(s)'
                + (
                    f'. {len(auto_remises)} point(s) d eau ont ete remis automatiquement en eau.'
                    if auto_remises else ''
                )
            ),
            'numero_diamex': numero_diamex,
            'base_diamex': base_diamex,
            'total_paiements': float(total_paiements),
            'montant_diamex': float(montant_diamex),
            'paiement_ids': paiement_ids,
            'auto_remise_count': len(auto_remises),
            'auto_remises': auto_remises,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_annuler_pointage_paiements_forfaitaires(request):
    """
    Annule un pointage forfaitaire pour un couple (numeroDiameX, baseDiameX).

    Effets:
    - vide numeroDiameX/baseDiameX sur toutes les lignes PaiementForfaitaire du couple
    - reouvre les conversations forfaitaires associees
    - renvoie aussi le nombre de lignes DiameX 748411 partageant ce couple
    """
    try:
        data = json.loads(request.body)
        numero_diamex = str(data.get('numero_diamex') or '').strip()
        base_diamex = str(data.get('base_diamex') or '').strip()
        annee_raw = data.get('annee')

        if not numero_diamex:
            return JsonResponse({
                'success': False,
                'error': 'Numero DiameX manquant'
            }, status=400)
        if not base_diamex:
            return JsonResponse({
                'success': False,
                'error': 'Base DiameX manquante'
            }, status=400)

        try:
            annee = int(annee_raw) if annee_raw else timezone.localdate().year
        except (TypeError, ValueError):
            annee = timezone.localdate().year

        allowed_ouvrage_ids = _get_scoped_forfaitaire_ouvrage_ids(
            request.user,
            annee=annee,
        )

        paiements = list(
            PaiementForfaitaire.objects.filter(
                numeroDiameX=numero_diamex,
                baseDiameX=base_diamex,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids,
            ).select_related('point_eau', 'point_eau__ouvrage').defer(*DEFER_PHOTOS_PAIEMENT)
        )
        if not paiements:
            return JsonResponse({
                'success': False,
                'error': 'Aucun paiement forfaitaire ne correspond a ce pointage'
            }, status=404)

        try:
            numero_diamex_int = int(numero_diamex)
        except (TypeError, ValueError):
            numero_diamex_int = None

        diamex_entries_qs = BaseDiameX.objects.filter(
            compte_code='748411',
            prog=base_diamex,
        )
        if numero_diamex_int is not None:
            diamex_entries_qs = diamex_entries_qs.filter(id_access=numero_diamex_int)
        else:
            diamex_entries_qs = diamex_entries_qs.none()

        diamex_entry_ids = list(diamex_entries_qs.values_list('id', flat=True))
        paiement_ids = [str(paiement.id) for paiement in paiements]
        actor = getattr(request.user, 'employe', None)

        with transaction.atomic():
            for paiement in paiements:
                paiement.numeroDiameX = None
                paiement.baseDiameX = None
                paiement.save(update_fields=[
                    'numeroDiameX',
                    'baseDiameX',
                    'updated_at',
                ])
                ensure_forfaitaire_conversation(paiement, actor=actor)

        return JsonResponse({
            'success': True,
            'message': (
                f'Pointage annule pour {len(paiements)} paiement(s) forfaitaire(s). '
                f'{len(diamex_entry_ids)} ligne(s) comptables 748411 partageaient ce couple.'
            ),
            'numero_diamex': numero_diamex,
            'base_diamex': base_diamex,
            'paiement_ids': paiement_ids,
            'diamex_entry_ids': diamex_entry_ids,
            'paiements_count': len(paiements),
            'diamex_entries_count': len(diamex_entry_ids),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def dashboard_paiements_forfaitaire_impression(request):
    """
    Version imprimable du dashboard paiements forfaitaires.
    Réutilise la logique de la vue principale mais avec un template simplifié.
    """
    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Filtres
    filter_annee = request.GET.get('annee', str(datetime.now().year))
    filter_region = request.GET.get('region', '')
    filter_district = request.GET.get('district', '')
    filter_commune = request.GET.get('commune', '')
    filter_ouvrage = request.GET.get('ouvrage', '')
    filter_organisation = request.GET.get('organisation', '')
    filter_taux = request.GET.get('taux', '')
    filter_taux_forfaitaire = request.GET.get('taux_forfaitaire', '')
    filter_trimestre = request.GET.get('trimestre', '')
    filter_echu = request.GET.get('echu', '')
    filter_statut_echu = request.GET.get('statut_echu', '')
    if filter_statut_echu not in {'non_paye_mois_passes', 'non_paye_mois_en_cours'}:
        filter_statut_echu = ''

    try:
        annee = int(filter_annee)
    except ValueError:
        annee = datetime.now().year

    trimestre_debut, trimestre_fin = _get_quarter_bounds(annee, filter_trimestre)
    if filter_trimestre and not trimestre_debut:
        filter_trimestre = ''

    # Scope gestionnaire de l'utilisateur
    organisation_user = get_user_organisation(request.user)
    accessible_gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    gestionnaire_ids, filter_organisation = _resolve_gestionnaire_scope(
        accessible_gestionnaire_ids,
        filter_organisation
    )
    organisations = _get_organisations_filtre_queryset(accessible_gestionnaire_ids)

    # Données DiameX - Paiements forfaitaires
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique

    transactions_qs = BaseDiameX.objects.filter(
        compte_code='748411',
        date_m__year=annee
    )
    if trimestre_debut and trimestre_fin:
        transactions_qs = transactions_qs.filter(date_m__gte=trimestre_debut, date_m__lte=trimestre_fin)

    # Extraction des ouvrages depuis les descriptions (réalisé)
    ouvrages_org_ids = _get_scoped_forfaitaire_ouvrage_ids(
        request.user,
        annee=annee,
        gestionnaire_ids=gestionnaire_ids,
    )

    ouvrage_ids_diamex = set()
    for transaction in transactions_qs:
        info = extraire_ouvrage_et_mois_generique(transaction.description, '748411')
        mois_extraction = info.get('mois') if info else None
        if filter_trimestre:
            if mois_extraction:
                if _quarter_of_date(date(annee, mois_extraction, 1)) != int(filter_trimestre):
                    continue
            elif transaction.date_m and _quarter_of_date(transaction.date_m) != int(filter_trimestre):
                continue
        if info and info.get('ouvrage_obj'):
            if info['ouvrage_obj'].id in ouvrages_org_ids:
                ouvrage_ids_diamex.add(info['ouvrage_obj'].id)

    # Ouvrages ayant du paiement forfaitaire (rattaché à date_facture)
    paiements_forfaitaires_qs = PaiementForfaitaire.objects.filter(
        date_facture__year=annee,
        date_facture__lte=timezone.localdate()
    ).select_related('point_eau', 'point_eau__ouvrage').defer(*DEFER_PHOTOS_PAIEMENT)
    if trimestre_debut and trimestre_fin:
        paiements_forfaitaires_qs = paiements_forfaitaires_qs.filter(
            date_facture__gte=trimestre_debut,
            date_facture__lte=trimestre_fin,
        )
    ouvrage_ids_prevus = set()
    montant_prevu_par_ouvrage = defaultdict(lambda: Decimal('0'))
    ouvrages_avec_facture_echue = set()
    today = timezone.localdate()
    for paiement in paiements_forfaitaires_qs:
        if paiement.point_eau and paiement.point_eau.ouvrage_id and paiement.point_eau.ouvrage_id in ouvrages_org_ids:
            ouvrage_ids_prevus.add(paiement.point_eau.ouvrage_id)
            montant_prevu_par_ouvrage[paiement.point_eau.ouvrage_id] += Decimal(str(paiement.montant or 0))
            est_paye = paiement.est_paye
            if (not est_paye) and paiement.date_facture and paiement.date_facture <= today:
                ouvrages_avec_facture_echue.add(paiement.point_eau.ouvrage_id)

    # Ouvrages ayant des points d'eau au forfait (même sans facture/DiameX)
    _cleanup_stale_cut_forfait_points(ouvrage_ids=ouvrages_org_ids)
    points_eau_forfait_qs = _forfait_points_queryset()
    points_eau_forfait_qs = points_eau_forfait_qs.filter(ouvrage_id__in=ouvrages_org_ids)
    ouvrage_ids_forfait_points = set(points_eau_forfait_qs.values_list('ouvrage_id', flat=True).distinct())

    # Filtrage ouvrages
    ouvrages_qs = Ouvrage.objects.filter(
        id__in=((ouvrage_ids_diamex | ouvrage_ids_prevus | ouvrage_ids_forfait_points) & ouvrages_org_ids)
    )

    # Filtre organisation
    ouvrages_qs = ouvrages_qs.filter(id__in=ouvrages_org_ids)

    # Filtres géographiques via PointEau
    if filter_region or filter_district or filter_commune or filter_ouvrage:
        points_eau_qs = PointEau.objects.defer('photos')

        if filter_region:
            points_eau_qs = points_eau_qs.filter(
                parcelle__village__fokontany__commune__district__region_id=filter_region
            )
        if filter_district:
            points_eau_qs = points_eau_qs.filter(
                parcelle__village__fokontany__commune__district_id=filter_district
            )
        if filter_commune:
            points_eau_qs = points_eau_qs.filter(
                parcelle__village__fokontany__commune_id=filter_commune
            )
        if filter_ouvrage:
            points_eau_qs = points_eau_qs.filter(ouvrage_id=filter_ouvrage)

        ouvrage_ids_geo = points_eau_qs.values_list('ouvrage_id', flat=True).distinct()
        ouvrages_qs = ouvrages_qs.filter(id__in=ouvrage_ids_geo)

    ouvrages_filtre = list(ouvrages_qs.distinct())

    # Calcul des montants par ouvrage
    recouvrement_par_ouvrage = {}

    modalite_active_map = _get_modalite_active_map(
        [o.id for o in ouvrages_filtre],
        annee=annee,
        gestionnaire_ids=gestionnaire_ids,
        modalites_paiement=FORFAITAIRE_MODALITES_PAIEMENT
    )

    for ouvrage in ouvrages_filtre:
        modalite_active = modalite_active_map.get(ouvrage.id)
        trimestres_exigibles = _trimestres_exigibles_depuis_date_debut(
            annee,
            getattr(modalite_active, 'date_debut', None)
        )
        if filter_trimestre:
            trimestres_exigibles = _get_selected_trimestres_exigibles_depuis_date_debut(
                annee,
                getattr(modalite_active, 'date_debut', None),
                filter_trimestre,
            )
        points_eau = _forfait_points_queryset().filter(
            ouvrage_id=ouvrage.id
        ).select_related('parcelle__village__fokontany__commune__district')

        if not points_eau.exists():
            continue

        # Montant prévu = tarif trimestriel x trimestres exigibles à date.
        montant_brut = Decimal('0')
        for pe in points_eau:
            montant_brut += tarif_pour_annee(pe, annee) * Decimal(str(trimestres_exigibles))

        decote_totale = calculer_decote_coupures(points_eau, annee, trimestre=filter_trimestre or None)
        montant_a_collecter = montant_brut - decote_totale
        if montant_a_collecter < 0:
            montant_a_collecter = Decimal('0')

        montant_paiement_forfaitaire = montant_prevu_par_ouvrage.get(ouvrage.id, Decimal('0'))

        # Montant collecté depuis DiameX
        montant_collecte = Decimal('0')
        for transaction in transactions_qs:
            info = extraire_ouvrage_et_mois_generique(transaction.description, '748411')
            if info and info.get('ouvrage_obj') and info['ouvrage_obj'].id == ouvrage.id:
                montant_collecte += Decimal(str(transaction.montant_in or 0))

        # Taux principal = Paye / A collecter (apres decote)
        has_taux_a_collecter = montant_a_collecter > 0
        taux_a_collecter = int((montant_collecte / montant_a_collecter) * 100) if has_taux_a_collecter else 0

        # Taux alternatif = Paye / Paiement forfaitaire
        has_taux = montant_paiement_forfaitaire > 0
        taux = int((montant_collecte / montant_paiement_forfaitaire) * 100) if has_taux else 0

        if filter_taux == 'gt100':
            if (not has_taux_a_collecter) or taux_a_collecter <= 100:
                continue
        if filter_taux == '100':
            if (not has_taux_a_collecter) or taux_a_collecter != 100:
                continue
        if filter_taux == 'lt100':
            if (not has_taux_a_collecter) or taux_a_collecter >= 100:
                continue
        if filter_taux_forfaitaire == 'gt100':
            if (not has_taux) or taux <= 100:
                continue
        if filter_taux_forfaitaire == '100':
            if (not has_taux) or taux != 100:
                continue
        if filter_taux_forfaitaire == 'lt100':
            if (not has_taux) or taux >= 100:
                continue
        if filter_echu == '1' and ouvrage.id not in ouvrages_avec_facture_echue:
            continue

        # Géographie
        premier_pe = points_eau.first()
        district_nom = 'Non défini'
        if premier_pe and premier_pe.parcelle:
            village = premier_pe.parcelle.village
            if village and village.fokontany and village.fokontany.commune:
                commune = village.fokontany.commune
                if commune.district:
                    district_nom = commune.district.nom_district

        recouvrement_par_ouvrage[ouvrage.id] = {
            'ouvrage_id': ouvrage.id,
            'ouvrage_nom': ouvrage.nom_ouvrage,
            'nb_points_eau': points_eau.count(),
            'montant_brut': montant_brut,
            'decote_totale': decote_totale,
            'montant_paiement_forfaitaire': montant_paiement_forfaitaire,
            'montant_a_collecter': montant_a_collecter,
            'montant_collecte': montant_collecte,
            'ecart': montant_a_collecter - montant_collecte,
            'taux': taux,
            'has_taux': has_taux,
            'district_nom': district_nom,
        }

    # Statistiques globales
    total_a_collecter_global = sum(data['montant_a_collecter'] for data in recouvrement_par_ouvrage.values())
    total_paiement_forfaitaire_global = sum(data['montant_paiement_forfaitaire'] for data in recouvrement_par_ouvrage.values())
    total_collecte_global = sum(data['montant_collecte'] for data in recouvrement_par_ouvrage.values())

    has_taux_recouvrement_global = total_paiement_forfaitaire_global > 0
    if has_taux_recouvrement_global:
        taux_recouvrement_global = int((total_collecte_global / total_paiement_forfaitaire_global) * 100)
    else:
        taux_recouvrement_global = 0

    # Conversion en milliers
    total_a_collecter_k = int(total_a_collecter_global / 1000)
    total_collecte_k = int(total_collecte_global / 1000)
    ecart_k = total_a_collecter_k - total_collecte_k

    # Groupement par district
    from itertools import groupby

    recouvrement_liste = sorted(
        recouvrement_par_ouvrage.values(),
        key=lambda x: (x['district_nom'], -x['taux'])
    )

    recouvrement_par_district = {}
    for district_nom, items in groupby(recouvrement_liste, key=lambda x: x['district_nom']):
        recouvrement_par_district[district_nom] = list(items)

    # --- Logique pour les filtres (similaire au dashboard volume) ---
    # 1. Récupérer les IDs d'ouvrages de l'organisation
    ouvrages_org_ids = list(_get_scoped_forfaitaire_ouvrage_ids(
        request.user,
        annee=annee,
        gestionnaire_ids=gestionnaire_ids,
    ))

    # 2. Récupérer PointEau filtrés
    points_eau_filtre_base = _forfait_points_queryset().select_related(
        'parcelle__village__fokontany__commune__district__region'
    )
    points_eau_filtre_base = points_eau_filtre_base.filter(ouvrage_id__in=ouvrages_org_ids)

    # 3. Extraire IDs
    district_ids = set()
    region_ids = set()
    commune_ids = set()
    
    for pe in points_eau_filtre_base.distinct():
        if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
            fokontany = pe.parcelle.village.fokontany
            if fokontany.commune:
                commune_ids.add(fokontany.commune.id)
                if fokontany.commune.district:
                    district_ids.add(fokontany.commune.district.id)
                    if fokontany.commune.district.region:
                         region_ids.add(fokontany.commune.district.region.id)

    # 4. Construire QuerySets
    if gestionnaire_ids is None:
        regions = Region.objects.all().order_by('nom_region')
        districts_all = District.objects.all().order_by('nom_district')
        communes_all = Commune.objects.select_related('district__region').order_by('nom_commune')
    else:
        regions = Region.objects.filter(id__in=list(region_ids)).order_by('nom_region') if region_ids else Region.objects.none()
        districts_all = (
            District.objects.filter(id__in=list(district_ids)).order_by('nom_district')
            if district_ids else District.objects.none()
        )
        communes_all = (
            Commune.objects.filter(id__in=list(commune_ids)).select_related('district__region').order_by('nom_commune')
            if commune_ids else Commune.objects.none()
        )

    districts_qs = districts_all
    if filter_region and filter_region != 'all':
        districts_qs = districts_qs.filter(region_id=filter_region)
    districts = districts_qs

    communes_qs = communes_all
    if filter_district and filter_district != 'all':
        communes_qs = communes_qs.filter(district_id=filter_district)
    elif filter_region and filter_region != 'all':
         communes_qs = communes_qs.filter(district__region_id=filter_region)
         
    communes = communes_qs

    organisation_label = 'Toutes'
    if filter_organisation:
        selected_org = organisations.filter(id=filter_organisation).first()
        if selected_org:
            organisation_label = selected_org.nom_organisation
    elif organisation_user:
        if organisation_user.type_organisation == Organisation.TYPE_PARTENAIRE:
            organisation_label = 'Toutes les organisations affectées'
        else:
            organisation_label = organisation_user.nom_organisation

    # Contexte pour le template
    context = {
        'annee': annee,
        'filter_region': filter_region,
        'filter_district': filter_district,
        'filter_commune': filter_commune,
        'filter_ouvrage': filter_ouvrage,
        'filter_organisation': filter_organisation,
        'filter_taux': filter_taux,
        'filter_taux_forfaitaire': filter_taux_forfaitaire,
        'filter_trimestre': filter_trimestre,
        'filter_echu': filter_echu,
        'organisations': organisations,
        'regions': regions,
        'districts': districts,
        'districts_all': districts_all,
        'communes': communes,
        'communes_all': communes_all,
        'date_impression': datetime.now(tz_madagascar),
        'organisation': organisation_label,
        'stats_global': {
            'total_a_collecter': total_a_collecter_global,
            'total_collecte': total_collecte_global,
            'ecart': total_a_collecter_global - total_collecte_global,
            'total_a_collecter_k': total_a_collecter_k,
            'total_collecte_k': total_collecte_k,
            'ecart_k': ecart_k,
            'taux_recouvrement': taux_recouvrement_global,
            'has_taux_recouvrement': has_taux_recouvrement_global,
            'nb_ouvrages': len(recouvrement_par_ouvrage)
        },
        'recouvrement_par_district': recouvrement_par_district,
    }

    return render(request, 'accounting/dashboard_paiements_forfaitaire_impression.html', context)
