from django.shortcuts import render
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q, Avg, Case, When, Value, CharField, F
from django.utils import timezone
from datetime import datetime, timedelta
from apps.planning.models import Planning
from apps.billing.models import PointEau, Releve, ModaliteGestion, CompteurTete, TypePointEau
from apps.billing.tarifs_forfaitaires import tarif_pour_annee
from apps.inventory.models import Stock, Product
from apps.employees.models import Employe
from apps.accounting.models import BaseDiameX
from apps.organization.models import Ouvrage
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_user_accessible_gestionnaire_ids,
    get_user_organisation,
    filter_ouvrages_by_gestionnaire_period,
    filter_modalites_by_gestionnaire_period,
    filter_current_modalites,
)
from apps.accounting.dashboard_employee_filter import (
    build_employee_geo_filter_options,
    calculate_water_point_score,
    get_water_point_score_gap_ids,
    is_closed_payment_month,
    resolve_dashboard_employee_filter,
    resolve_score_scope,
)
from apps.billing.payment_modalities import (
    build_payment_modality_scope,
    build_point_usage_modality_breakdown,
)
from apps.geography.models import Region, District, Commune, Village
from apps.infrastructure.models import CarteSociale, EquipementConstitutif
from apps.employees.permissions import (
    employe_required,
    filter_queryset_by_permissions,
    can_manage_forfaitaire_factures,
)


def _planning_photos(raw_value):
    """Normalise les anciennes et nouvelles photos JSON d'un planning."""
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []

    photos = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            continue
        source = str(item.get('data') or item.get('url') or '').strip()
        if source and not source.startswith(('data:image/', 'http://', 'https://', '/media/')):
            content_type = str(item.get('content_type') or item.get('type') or 'image/jpeg')
            if not content_type.startswith('image/'):
                continue
            source = f'data:{content_type};base64,{source}'
        if not source:
            continue
        photos.append({
            'data': source,
            'name': str(item.get('name') or f'Photo {index}'),
        })
    return photos


def _planning_photo_count(raw_value):
    """Compte les photos sans casser une fiche à cause d'une ancienne valeur JSON."""
    return len(_planning_photos(raw_value))


def _exclude_from_repair_history(activity_label):
    """Écarte les activités opérationnelles qui ne sont pas des réparations."""
    from apps.planning.repair_classification import is_excluded_repair_activity

    return is_excluded_repair_activity(activity_label)


def _get_ouvrage_repair_plannings(ouvrage, fiche_ids, activite_ids):
    """Retourne les reparations d'un ouvrage, avec ou sans PlanningDetail."""
    return Planning.objects.filter(
        Q(ouvrage=ouvrage)
        | Q(details__point_eau__ouvrage=ouvrage)
        | Q(details__equipement_constitutif__ouvrage=ouvrage)
    ).filter(
        Q(fiche_poste_id__in=fiche_ids)
        | Q(fiche_poste__activites_postes__activite_id__in=activite_ids)
        | Q(remarque__startswith='[Saisie depuis la fiche ouvrage]')
    ).select_related(
        'fiche_poste',
        'type_activite',
        'employe',
    ).prefetch_related(
        'details__point_eau',
        'details__equipement_constitutif',
    ).order_by('-date').distinct()


def _normalize_dashboard_point_type_label(value, fallback='Sans type'):
    label = (value or '').strip()
    if not label:
        return fallback

    compact_upper = ''.join(label.upper().split())
    if compact_upper == 'BF':
        return 'BF'
    if compact_upper in {'BI', 'BIVOLUME'}:
        return 'BI'
    if 'KIOSQUE' in compact_upper:
        return 'Kiosque'
    if compact_upper in {'PMH', 'PMHI'}:
        return 'PMH'
    if compact_upper == 'BP':
        return 'BP'
    return label


def _normalize_dashboard_ouvrage_type_label(value, fallback='Type non défini'):
    label = (value or '').strip()
    if not label:
        return fallback

    compact_upper = ''.join(label.upper().split())
    if compact_upper in {'FPMH', 'PMH', 'PPMH'}:
        return 'PMH'
    return label


def _dashboard_point_type_case():
    return Case(
        When(type_point_eau__isnull=True, then=Value('Sans type')),
        When(type_point_eau__nom_type__isnull=True, then=Value('Sans type')),
        # « BI » = BF ou BP cochés « branchement institutionnel » (anciens types BI / BI volume) ;
        # doit précéder la règle BF, sinon un BF institutionnel resterait classé BF
        When(
            Q(estbranchementinstitutionnel=True, type_point_eau__nom_type__iregex=r'^\s*(BF|BP)\s*$'),
            then=Value('BI'),
        ),
        When(type_point_eau__nom_type__iregex=r'^\s*BF\s*$', then=Value('BF')),
        When(type_point_eau__nom_type__icontains='kiosque', then=Value('Kiosque')),
        When(type_point_eau__nom_type__iregex=r'^\s*PMHI?\s*$', then=Value('PMH')),
        When(type_point_eau__nom_type__iregex=r'^\s*BP\s*$', then=Value('BP')),
        default=F('type_point_eau__nom_type'),
        output_field=CharField(),
    )


@employe_required
def dashboard(request):
    """Dashboard principal avec statistiques globales (filtrées selon les permissions)"""
    try:
        # Appliquer les filtres de permissions (sauf pour les superutilisateurs)
        plannings = filter_queryset_by_permissions(Planning.objects.all(), request.user)
        releves = filter_queryset_by_permissions(Releve.objects.all(), request.user)
        employes = filter_queryset_by_permissions(Employe.objects.all(), request.user)
        points_eau = filter_queryset_by_permissions(PointEau.objects.all(), request.user)
        stocks = filter_queryset_by_permissions(Stock.objects.all(), request.user)

        # Une date de fin vide ne suffit pas : un contrat futur n'est pas
        # encore une affectation active.
        modalites_actives = filter_current_modalites(ModaliteGestion.objects.all())
        ouvrages_forfaitaire = modalites_actives.filter(modalitepaiement='forfaitaire').values('ouvrage').distinct().count()
        ouvrages_volume = modalites_actives.filter(modalitepaiement='au_volume').values('ouvrage').distinct().count()

        # Compter les points d'eau par modalité de paiement
        # Via les ouvrages qui ont des modalités actives forfaitaires/volume
        ouvrages_ids_forfaitaire = modalites_actives.filter(modalitepaiement='forfaitaire').values_list('ouvrage_id', flat=True).distinct()
        ouvrages_ids_volume = modalites_actives.filter(modalitepaiement='au_volume').values_list('ouvrage_id', flat=True).distinct()

        points_eau_forfaitaire = points_eau.filter(ouvrage_id__in=ouvrages_ids_forfaitaire).count()
        points_eau_volume = points_eau.filter(ouvrage_id__in=ouvrages_ids_volume).count()

        stats = {
            'plannings_actifs': plannings.count(),
            'factures_impayees': releves.filter(statut='impaye').count(),
            'employes_actifs': employes.filter(is_active=True).count(),
            'clients_actifs': points_eau.filter(datearretbranchement__isnull=True).count(),
            'produits_stock_bas': stocks.filter(
                available_quantity__lte=10  # Seuil d'alerte
            ).count(),
            'ouvrages_forfaitaire': ouvrages_forfaitaire,
            'ouvrages_volume': ouvrages_volume,
            'points_eau_forfaitaire': points_eau_forfaitaire,
            'points_eau_volume': points_eau_volume,
        }
    except Exception as e:
        # Si les tables n'existent pas encore ou sont vides
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur dashboard: {e}")
        stats = {
            'plannings_actifs': 0,
            'factures_impayees': 0,
            'employes_actifs': 0,
            'clients_actifs': 0,
            'produits_stock_bas': 0,
            'ouvrages_forfaitaire': 0,
            'ouvrages_volume': 0,
            'points_eau_forfaitaire': 0,
            'points_eau_volume': 0,
        }

    return render(request, 'core/dashboard.html', {
        'stats': stats,
        'title': 'Tableau de Bord Principal'
    })


@login_required
def rapports(request):
    """Page des rapports et analytics"""
    return render(request, 'core/rapports.html', {
        'title': 'Rapports et Analyses'
    })


@login_required
def cartes_sociales(request):
    """Gestion des cartes sociales"""
    return render(request, 'core/cartes_sociales.html', {
        'title': 'Cartes Sociales'
    })


def dashboard_payments_flat(request):
    """Dashboard des paiements forfaitaires avec vue consolidée par point d'eau"""
    from apps.billing.models import PointEau, ModaliteGestion, PaiementForfaitaire, CoupureEau
    from apps.organization.models import Ouvrage
    from apps.accounting.models import BaseDiameX
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
    from django.db.models import Q, Count
    from datetime import datetime, timedelta
    from decimal import Decimal
    from django.core.paginator import Paginator
    from dateutil.relativedelta import relativedelta
    import json
    import re
    import unicodedata

    # CRITICAL: Récupérer uniquement les ouvrages avec modalité forfaitaire ou mixte
    # ET dont la date_debut est <= 31 décembre de l'année filtrée
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    annee = int(annee_filter)
    employe_filter = request.GET.get('employe', '')
    from datetime import date as date_class
    date_fin_annee = date_class(annee, 12, 31)

    ouvrages_forfaitaires_ids = set(ModaliteGestion.objects.filter(
        date_fin__isnull=True,  # Modalité active
        modalitepaiement__in=['forfaitaire', 'mixte'],
        date_debut__lte=date_fin_annee  # Modalité commencée avant ou pendant l'année filtrée
    ).values_list('ouvrage_id', flat=True).distinct())
    # Conserver l'ensemble non-restreint pour les options des filtres géographiques (dropdowns).
    # L'intention est de cloisonner les DONNÉES par utilisateur, pas les options de filtres.
    ouvrages_forfaitaires_ids_unscoped = set(ouvrages_forfaitaires_ids)
    ouvrages_forfaitaires_ids = apply_user_responsable_ouvrage_scope(
        ouvrages_forfaitaires_ids,
        request.user,
        allow_same_base_support_roles=True,
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
    employe_ids_par_ouvrage = {}
    for employe_option in employes_responsables:
        for ouvrage_id_option in employe_option.get('ouvrage_ids', []):
            employe_ids_par_ouvrage.setdefault(str(ouvrage_id_option), []).append(
                str(employe_option['id'])
            )

    # Filtres (annee_filter déjÃ  défini ci-dessus pour le filtre modalité)
    region_filter = request.GET.get('region', '')
    district_filter = request.GET.get('district', '')
    commune_filter = request.GET.get('commune', '')
    ouvrage_filter = request.GET.get('ouvrage', '')
    type_point_eau_filter = request.GET.get('type_point_eau', '')
    statut_filter = request.GET.get('statut', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    try:
        date_debut_value = datetime.strptime(date_debut, '%Y-%m-%d').date() if date_debut else None
    except ValueError:
        date_debut_value = None
    try:
        date_fin_value = datetime.strptime(date_fin, '%Y-%m-%d').date() if date_fin else None
    except ValueError:
        date_fin_value = None
    impayes_echus_filter = str(request.GET.get('impayes_echus', '') or '').strip().lower()
    if impayes_echus_filter in {'1', 'true', 'on', 'yes', 'tous'}:
        impayes_echus_mode = 'tous'
    elif impayes_echus_filter in {'avant_mois', 'mois_courant'}:
        impayes_echus_mode = impayes_echus_filter
    else:
        impayes_echus_mode = ''
    show_only_impayes_echus = bool(impayes_echus_mode)
    controle_tranches_filter = (request.GET.get('controle_tranches') or '').strip()
    if controle_tranches_filter not in {'a_completer', 'a_corriger'}:
        controle_tranches_filter = ''
    diamex_non_pointe_filter = str(request.GET.get('diamex_non_pointe', '') or '').strip().lower()
    show_only_diamex_non_pointes = diamex_non_pointe_filter in {'1', 'true', 'on', 'yes'}
    score_ecart_filter = str(request.GET.get('score_ecart', '') or '').strip().lower()
    show_only_score_gap = score_ecart_filter in {'1', 'true', 'on', 'yes'}

    # Récupérer les options de filtres géographiques disponibles.
    # Utiliser l'ensemble non-restreint (toute l'organisation) pour que les filtres
    # restent interactifs même pour les utilisateurs ayant un périmètre restreint.
    points_eau_geo_base = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=ouvrages_forfaitaires_ids_unscoped
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

    regions = Region.objects.filter(id__in=region_ids).order_by('nom_region')
    districts_all = District.objects.filter(id__in=district_ids).select_related('region').order_by('nom_district')
    communes_all = Commune.objects.filter(id__in=commune_ids).select_related('district__region').order_by('district__nom_district', 'nom_commune')

    districts = districts_all
    if region_filter:
        districts = districts.filter(region_id=region_filter)

    communes = communes_all
    if district_filter:
        communes = communes.filter(district_id=district_filter)
    elif region_filter:
        communes = communes.filter(district__region_id=region_filter)

    employe_ids_par_region = {}
    employe_ids_par_district = {}
    employe_ids_par_commune = {}
    geo_ouvrage_rows = points_eau_geo_base.values_list(
        'ouvrage_id',
        'parcelle__village__fokontany__commune__district__region_id',
        'parcelle__village__fokontany__commune__district_id',
        'parcelle__village__fokontany__commune_id',
    ).distinct()
    for geo_ouvrage_id, geo_region_id, geo_district_id, geo_commune_id in geo_ouvrage_rows:
        ouvrage_employe_ids = employe_ids_par_ouvrage.get(str(geo_ouvrage_id), [])
        for employee_id in ouvrage_employe_ids:
            if geo_region_id:
                employe_ids_par_region.setdefault(str(geo_region_id), set()).add(employee_id)
            if geo_district_id:
                employe_ids_par_district.setdefault(str(geo_district_id), set()).add(employee_id)
            if geo_commune_id:
                employe_ids_par_commune.setdefault(str(geo_commune_id), set()).add(employee_id)

    regions = list(regions)
    districts_all = list(districts_all)
    communes_all = list(communes_all)
    for region in regions:
        region.filter_employe_ids = ','.join(sorted(
            employe_ids_par_region.get(str(region.id), set())
        ))
    for district in districts_all:
        district.filter_employe_ids = ','.join(sorted(
            employe_ids_par_district.get(str(district.id), set())
        ))
    for commune in communes_all:
        commune.filter_employe_ids = ','.join(sorted(
            employe_ids_par_commune.get(str(commune.id), set())
        ))

    from django.db.models import OuterRef, Subquery
    commune_subquery = PointEau.objects.filter(
        ouvrage_id=OuterRef('pk')
    ).values('parcelle__village__fokontany__commune_id')[:1]
    district_subquery = PointEau.objects.filter(
        ouvrage_id=OuterRef('pk')
    ).values('parcelle__village__fokontany__commune__district_id')[:1]
    region_subquery = PointEau.objects.filter(
        ouvrage_id=OuterRef('pk')
    ).values('parcelle__village__fokontany__commune__district__region_id')[:1]

    ouvrages = list(Ouvrage.objects.filter(
        id__in=ouvrages_forfaitaires_ids_unscoped
    ).annotate(
        filter_commune_id=Subquery(commune_subquery),
        filter_district_id=Subquery(district_subquery),
        filter_region_id=Subquery(region_subquery),
    ).order_by('nom_ouvrage'))
    for ouvrage in ouvrages:
        ouvrage.filter_employe_ids = ','.join(
            employe_ids_par_ouvrage.get(str(ouvrage.id), [])
        )

    from apps.billing.models import TypePointEau
    types_point_eau = TypePointEau.objects.filter(
        id__in=PointEau.objects.filter(
            tarifforfaitaire__isnull=False,
            ouvrage_id__in=ouvrages_forfaitaires_ids_unscoped
        ).values_list('type_point_eau_id', flat=True).distinct()
    ).order_by('nom_type')

    # Filtrer les points d'eau avec tarif forfaitaire non null
    # ET modalité forfaitaire/mixte
    points_eau = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=ouvrages_forfaitaires_ids  # FILTRE MODALITE
    ).select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune'
    ).only(
        'id', 'ouvrage_id', 'type_point_eau_id', 'parcelle_id',
        'tarifforfaitaire', 'idxls', 'datearretbranchement',
        'code_point_eau', 'nomabonne', 'estbranchementinstitutionnel', 'pourcentage_tarif',
        'ouvrage__id', 'ouvrage__nom_ouvrage',
        'type_point_eau__id', 'type_point_eau__nom_type',
        'parcelle__id', 'parcelle__village_id',
        'parcelle__village__id', 'parcelle__village__fokontany_id',
        'parcelle__village__fokontany__id',
        'parcelle__village__fokontany__commune_id',
        'parcelle__village__fokontany__commune__id',
        'parcelle__village__fokontany__commune__nom_commune',
    )

    if region_filter:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune__district__region_id=region_filter)
    if district_filter:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune__district_id=district_filter)
    if commune_filter:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune_id=commune_filter)
    if ouvrage_filter:
        points_eau = points_eau.filter(ouvrage_id=ouvrage_filter)
    if type_point_eau_filter:
        points_eau = points_eau.filter(type_point_eau_id=type_point_eau_filter)

    points_eau_materialized = list(points_eau)
    point_ids = [pe.id for pe in points_eau_materialized]
    coupures_by_point = {str(point_id): [] for point_id in point_ids}
    derniers_evenements_coupure = {}
    for evt in CoupureEau.objects.filter(point_eau_id__in=point_ids).only(
        'id', 'point_eau_id', 'date_evenement', 'created_at', 'type_evenement'
    ).order_by('point_eau_id', 'date_evenement', 'created_at'):
        point_key = str(evt.point_eau_id)
        coupures_by_point.setdefault(point_key, []).append(evt)
        derniers_evenements_coupure[point_key] = evt

    point_idxls_to_ids = {}
    ouvrage_point_ids = {}
    for pe in points_eau_materialized:
        ouvrage_point_ids.setdefault(pe.ouvrage_id, []).append(pe.id)
        idxls_value = str(pe.idxls or '').strip()
        if idxls_value:
            point_idxls_to_ids.setdefault((pe.ouvrage_id, idxls_value), []).append(pe.id)

    # Date de debut de la modalite de gestion (forfaitaire/mixte) active de chaque
    # ouvrage : si elle tombe dans l'annee affichee, le nombre de tranches
    # attendues cette annee-la doit etre reduit en consequence (cf.
    # calculate_expected_tranches) et la date est affichee sous le nom de l'ouvrage.
    modalite_debut_par_ouvrage = {}
    if ouvrage_point_ids:
        for ouvrage_id_val, date_debut_val in ModaliteGestion.objects.filter(
            ouvrage_id__in=ouvrage_point_ids.keys(),
            date_fin__isnull=True,
            modalitepaiement__in=['forfaitaire', 'mixte'],
            date_debut__lte=date_fin_annee,
        ).order_by('ouvrage_id', 'date_debut').values_list('ouvrage_id', 'date_debut'):
            modalite_debut_par_ouvrage.setdefault(ouvrage_id_val, date_debut_val)

    today = datetime.now().date()
    debut_annee = datetime(annee, 1, 1).date()
    fin_annee = datetime(annee, 12, 31).date()
    if annee < today.year:
        limit_date = fin_annee
    else:
        limit_date = min(today, fin_annee)
    if limit_date < debut_annee:
        limit_date = debut_annee
    debut_mois_repere = limit_date.replace(day=1)

    paiements_by_point = {str(point_id): [] for point_id in point_ids}
    paiements_du_perimetre = PaiementForfaitaire.objects.filter(
        point_eau_id__in=point_ids,
    ).filter(
        Q(date_facture__year=annee)
        | Q(date_facture__isnull=True, planning__date__date__year=annee)
    ).select_related('planning').only(
        'id', 'point_eau_id', 'planning_id', 'date_facture', 'quantite',
        'montant', 'paye', 'numeroDiameX', 'baseDiameX', 'planning__date', 'date_encaissement'
    ).order_by('point_eau_id', 'date_facture', 'id')
    for paiement in paiements_du_perimetre:
        paiements_by_point.setdefault(str(paiement.point_eau_id), []).append(paiement)

    # Total cumule depuis toujours (pas seulement l'annee affichee) : utilise pour
    # projeter la prochaine echeance quand un point a paye d'avance (un paiement qui
    # depasse le nombre de tranches attendues cette annee n'est pas une erreur, il
    # couvre juste une periode qui court au-dela de l'annee en cours).
    tranches_realisees_cumul_par_point = {}
    for point_eau_id_cumul, quantite_cumul in PaiementForfaitaire.objects.filter(
        point_eau_id__in=point_ids,
        date_facture__lte=fin_annee,
    ).values_list('point_eau_id', 'quantite'):
        key_cumul = str(point_eau_id_cumul)
        tranches_realisees_cumul_par_point[key_cumul] = (
            tranches_realisees_cumul_par_point.get(key_cumul, 0) + int(quantite_cumul or 0)
        )

    pointed_couples_global = {
        (str(numero or '').strip(), str(base or '').strip())
        for numero, base in PaiementForfaitaire.objects.filter(point_eau_id__in=point_ids)
        .exclude(numeroDiameX__isnull=True)
        .exclude(baseDiameX__isnull=True)
        .values_list('numeroDiameX', 'baseDiameX')
        if str(numero or '').strip() and str(base or '').strip()
    }

    point_compta_total = {}
    point_compta_non_pointe = {}
    point_compta_non_pointe_count = {}

    def _parse_forfaitaire_idxls_hint(description):
        text = str(description or '').strip()
        if not text:
            return []
        paren_matches = re.findall(r"\(([^()]*)\)\s*$", text)
        if not paren_matches:
            return []
        hint = paren_matches[-1].strip()
        if not hint:
            return []
        return [part.strip() for part in re.findall(r'BF"([^"]+)"', hint, flags=re.IGNORECASE) if part.strip()]

    def _normalize_forfaitaire_matching_text(value):
        normalized = unicodedata.normalize('NFKD', str(value or ''))
        normalized = ''.join(char for char in normalized if not unicodedata.combining(char))
        return ' '.join(re.sub(r'[^a-z0-9]+', ' ', normalized.lower()).split())

    # Indexer les noms par leur premier mot evite de comparer chaque libelle
    # DiameX avec tous les ouvrages. L'index global permet aussi d'ecarter sans
    # requete SQL de secours une transaction appartenant a un autre district.
    ouvrage_ids_visibles = set(ouvrage_point_ids)
    ouvrages_matching_par_premier_mot = {}
    for ouvrage_item in Ouvrage.objects.filter(
        id__in=ouvrages_forfaitaires_ids
    ).only('id', 'nom_ouvrage'):
        normalized_name = _normalize_forfaitaire_matching_text(ouvrage_item.nom_ouvrage)
        if not normalized_name:
            continue
        premier_mot = normalized_name.split()[0]
        ouvrages_matching_par_premier_mot.setdefault(premier_mot, []).append(
            (ouvrage_item.id, normalized_name)
        )
    for candidates in ouvrages_matching_par_premier_mot.values():
        candidates.sort(key=lambda item: len(item[1]), reverse=True)

    def _match_ouvrage_forfaitaire_normalized(normalized_description):
        description_with_boundaries = f" {normalized_description} "
        best_match = None
        for token in set(normalized_description.split()):
            for candidate_id, normalized_name in ouvrages_matching_par_premier_mot.get(token, []):
                if f" {normalized_name} " not in description_with_boundaries:
                    continue
                if best_match is None or len(normalized_name) > best_match[0]:
                    best_match = (len(normalized_name), candidate_id)
        return best_match[1] if best_match else None

    transactions_forfaitaires = (
        BaseDiameX.objects.filter(
            compte_code='748411',
            date_m__year=annee,
            date_m__lte=limit_date,
        ).only('id', 'description', 'montant_in', 'id_access', 'prog')
        if ouvrage_point_ids
        else BaseDiameX.objects.none()
    )
    extraction_forfaitaire_cache = {}
    for trans in transactions_forfaitaires:
        description_key = trans.description or ''
        if description_key in extraction_forfaitaire_cache:
            ouvrage_id = extraction_forfaitaire_cache[description_key]
        else:
            normalized_description = _normalize_forfaitaire_matching_text(description_key)
            ouvrage_id = _match_ouvrage_forfaitaire_normalized(normalized_description)
            if ouvrage_id is None:
                # Secours pour les anciens formats que la correspondance directe
                # ne reconnait pas encore.
                extraction = extraire_ouvrage_et_mois_generique(description_key, '748411')
                ouvrage_obj = extraction.get('ouvrage_obj')
                ouvrage_id = ouvrage_obj.id if ouvrage_obj else None
            extraction_forfaitaire_cache[description_key] = ouvrage_id

        if not ouvrage_id or ouvrage_id not in ouvrage_ids_visibles:
            continue
        target_point_id = None
        hinted_idxls = _parse_forfaitaire_idxls_hint(trans.description or '')

        if len(hinted_idxls) == 1:
            matched_point_ids = point_idxls_to_ids.get((ouvrage_id, hinted_idxls[0]), [])
            if len(matched_point_ids) == 1:
                target_point_id = matched_point_ids[0]
        elif not hinted_idxls:
            ouvrage_point_matches = ouvrage_point_ids.get(ouvrage_id, [])
            if len(ouvrage_point_matches) == 1:
                target_point_id = ouvrage_point_matches[0]

        if not target_point_id:
            continue

        montant_trans = Decimal(str(trans.montant_in or 0))
        point_compta_total[target_point_id] = point_compta_total.get(target_point_id, Decimal('0.00')) + montant_trans

        numero_diamex = str(trans.id_access or '').strip()
        base_diamex = str(trans.prog or '').strip()
        already_pointed = bool(numero_diamex and base_diamex and (numero_diamex, base_diamex) in pointed_couples_global)
        if not already_pointed:
            point_compta_non_pointe[target_point_id] = point_compta_non_pointe.get(target_point_id, Decimal('0.00')) + montant_trans
            point_compta_non_pointe_count[target_point_id] = point_compta_non_pointe_count.get(target_point_id, 0) + 1

    # Construire le tableau consolidé par point d'eau
    points_eau_list = []
    mois_labels = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aou', 'Sep', 'Oct', 'Nov', 'Déc']

    # Statistiques par statut
    nb_tout_paye = 0
    nb_partiellement_paye = 0
    nb_non_paye = 0
    nb_coupe = 0
    nb_tranches_ok = 0
    nb_tranches_a_completer = 0
    nb_tranches_a_corriger = 0
    nb_tranches_payees = 0
    nb_tranches_non_payees_echues = 0
    nb_tranches_non_payees_non_echues = 0
    montant_prevu_total = Decimal('0.00')
    montant_planifie_total = Decimal('0.00')
    montant_paye_total = Decimal('0.00')
    decote_totale_globale = Decimal('0.00')  # Nouvelle variable pour la décote totale

    import pytz
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    def get_paiement_date(paiement):
        date_value = None
        if paiement.date_facture:
            date_value = paiement.date_facture
        elif getattr(paiement, 'planning_id', None) and paiement.planning and paiement.planning.date:
            date_value = paiement.planning.date

        if not date_value:
            return None

        if isinstance(date_value, datetime):
            if date_value.tzinfo:
                date_madagascar = date_value.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_value)
            return date_madagascar.date()

        return date_value

    total_days_in_year = (fin_annee - debut_annee).days + 1
    elapsed_days_in_year = max(0, (limit_date - debut_annee).days + 1)
    pct_annee_ecoulee = int(round((elapsed_days_in_year * 100) / total_days_in_year)) if total_days_in_year else 0
    mois_reperes = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Avr', 5: 'Mai', 6: 'Juin', 7: 'Juil', 8: 'Aou', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
    mois_repere_numero = limit_date.month
    mois_repere_label = mois_reperes.get(mois_repere_numero, '')

    def calculate_details_financiers(pe, annee, limit_date):
        tarif = tarif_pour_annee(pe, annee)
        if tarif == 0:
            return Decimal('0.00'), Decimal('0.00'), Decimal('0.00')

        debut_annee = datetime(annee, 1, 1).date()

        if limit_date < debut_annee:
            nb_mois_ecoules = 0
        else:
            delta_jours = (limit_date - debut_annee).days + 1
            nb_mois_ecoules = int(round(delta_jours / 30.4))

        montant_brut = (tarif / 3) * nb_mois_ecoules

        point_events = coupures_by_point.get(str(pe.id), [])
        events_before_year = [evt for evt in point_events if evt.date_evenement < debut_annee]
        or_debut = events_before_year[-1] if events_before_year else None
        est_coupe = (or_debut and or_debut.type_evenement == 'coupure')
        date_debut_coupure = debut_annee if est_coupe else None

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
            d = date_debut_coupure if date_debut_coupure else debut_annee
            periodes.append({'debut': d, 'fin': limit_date})

        decote = Decimal('0.00')
        for p in periodes:
            nb = int(round((p['fin'] - p['debut']).days / 30.4))
            decote += (tarif / 3) * nb

        net = max(Decimal('0.00'), montant_brut - decote)
        return montant_brut, decote, net

    def calculate_expected_tranches(pe, annee):
        """
        Nombre de tranches (trimestres) attendues sur l'annee, deduction faite
        des trimestres sans eau.

        Si la modalite de gestion de l'ouvrage a demarre en cours d'annee
        (ex: 1er septembre 2026), la base n'est plus 4 mais le nombre de
        trimestres restants depuis ce debut (ex: 2 pour un debut en septembre,
        3 pour un debut en avril).
        """
        debut_annee = datetime(annee, 1, 1).date()
        fin_annee = datetime(annee, 12, 31).date()

        date_debut_modalite = modalite_debut_par_ouvrage.get(pe.ouvrage_id)

        # Le renouvellement a toujours lieu sur le meme mois calendaire chaque
        # annee, donc le decalage introduit par un debut en cours d'annee (ex:
        # septembre -> 2 tranches) se reproduit chaque annee suivante et n'est
        # pas limite a l'annee de debut.
        tranches_planifiees_base = 4
        if date_debut_modalite:
            if date_debut_modalite.year > annee:
                tranches_planifiees_base = 0
            else:
                quarter_debut = ((date_debut_modalite.month - 1) // 3) + 1
                tranches_planifiees_base = max(0, 4 - quarter_debut + 1)

        if date_debut_modalite and date_debut_modalite > debut_annee:
            if date_debut_modalite > fin_annee:
                return 0, 0
            debut_annee = date_debut_modalite

        point_events = coupures_by_point.get(str(pe.id), [])
        events_before_year = [evt for evt in point_events if evt.date_evenement < debut_annee]
        or_debut = events_before_year[-1] if events_before_year else None
        est_coupe = bool(or_debut and or_debut.type_evenement == 'coupure')
        date_debut_coupure = debut_annee if est_coupe else None

        evenements = [
            evt for evt in point_events
            if evt.date_evenement.year == annee and evt.date_evenement >= debut_annee and evt.date_evenement <= fin_annee
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
            periodes.append({'debut': date_debut_coupure or debut_annee, 'fin': fin_annee})

        trimestres_sans_eau = 0
        for periode in periodes:
            jours = max(0, (periode['fin'] - periode['debut']).days)
            trimestres_sans_eau += int(round(jours / 91.25))

        trimestres_sans_eau = max(0, min(tranches_planifiees_base, trimestres_sans_eau))
        return max(0, tranches_planifiees_base - trimestres_sans_eau), trimestres_sans_eau

    raison_coupure_labels = dict(CoupureEau.RAISON_CHOICES)

    def compute_coupure_periodes(pe):
        """Périodes de coupure d'eau du point sur l'année filtrée.

        Retourne une liste de {debut, fin, raison, raison_label, en_cours}. Inclut
        aussi bien les coupures déjà terminées (coupure -> remise) que la coupure
        encore en cours, pour rendre visibles les points "coupés puis remis".
        """
        events = coupures_by_point.get(str(pe.id), [])
        events_avant = [e for e in events if e.date_evenement < debut_annee]
        dernier_avant = events_avant[-1] if events_avant else None
        coupe_debut = debut_annee if (dernier_avant and dernier_avant.type_evenement == 'coupure') else None
        coupe_raison = dernier_avant.raison if coupe_debut else None

        periodes = []
        for e in events:
            if e.date_evenement < debut_annee or e.date_evenement > limit_date:
                continue
            if e.type_evenement == 'coupure':
                if coupe_debut is None:
                    coupe_debut = e.date_evenement
                    coupe_raison = e.raison
            elif e.type_evenement == 'remise':
                if coupe_debut is not None:
                    periodes.append({
                        'debut': coupe_debut,
                        'fin': e.date_evenement,
                        'raison': coupe_raison,
                        'raison_label': raison_coupure_labels.get(coupe_raison, ''),
                        'en_cours': False,
                    })
                    coupe_debut = None
                    coupe_raison = None
        if coupe_debut is not None:
            periodes.append({
                'debut': coupe_debut,
                'fin': limit_date,
                'raison': coupe_raison,
                'raison_label': raison_coupure_labels.get(coupe_raison, ''),
                'en_cours': True,
            })
        return periodes

    for pe in points_eau_materialized:
        # Calculer les montants financiers ajustés
        tarif = tarif_pour_annee(pe, annee)
        
        montant_prevu_brut, decote_montant, montant_prevu_annuel = calculate_details_financiers(pe, annee, limit_date)

        # Récupérer tous les paiements forfaitaires pour ce point d'eau pour l'année filtrée
        paiements_annee = paiements_by_point.get(str(pe.id), [])
        
        # Calculer les paiements par trimestre
        trimestres = {
            'T1': {'paye': 0, 'non_paye': 0, 'paye_montant': Decimal('0.00'), 'non_paye_montant': Decimal('0.00'), 'mois': [1, 2, 3]},
            'T2': {'paye': 0, 'non_paye': 0, 'paye_montant': Decimal('0.00'), 'non_paye_montant': Decimal('0.00'), 'mois': [4, 5, 6]},
            'T3': {'paye': 0, 'non_paye': 0, 'paye_montant': Decimal('0.00'), 'non_paye_montant': Decimal('0.00'), 'mois': [7, 8, 9]},
            'T4': {'paye': 0, 'non_paye': 0, 'paye_montant': Decimal('0.00'), 'non_paye_montant': Decimal('0.00'), 'mois': [10, 11, 12]},
            'planifie_annee': Decimal('0.00')
        }
        mois_stats = {
            mois: {'paye': 0, 'non_paye': 0, 'paye_montant': Decimal('0.00'), 'non_paye_montant': Decimal('0.00')}
            for mois in range(1, 13)
        }
        montant_forfaitaire_non_pointe = Decimal('0.00')
        montant_encaisse_non_pointe = Decimal('0.00')  # encaissé caissière, pas encore pointé
        montant_planifie_graph = Decimal('0.00')
        montant_paye_graph = Decimal('0.00')
        has_facture_echue_non_pointee = False
        has_facture_echue_avant_mois = False
        has_facture_echue_mois_courant = False
        qte_non_payee_echue = 0

        for paiement in paiements_annee:
            date_locale = get_paiement_date(paiement)
            if not date_locale:
                continue

            if date_locale.year == annee:
                montant_ligne = (
                    Decimal(str(paiement.montant))
                    if paiement.montant is not None
                    else (Decimal(str(paiement.quantite or 1)) * tarif)
                )
                # Filtrer les paiements planifiés (YTD) pour le total global
                if date_locale <= limit_date:
                    trimestres['planifie_annee'] += montant_ligne
                    numero_diamex = (paiement.numeroDiameX or '').strip()
                    base_diamex = (paiement.baseDiameX or '').strip()
                    est_pointe = bool(numero_diamex and base_diamex)
                    est_paye = bool(paiement.paye or numero_diamex or base_diamex)
                    graph_date_ok = (
                        (not date_debut_value or date_locale >= date_debut_value)
                        and (not date_fin_value or date_locale <= date_fin_value)
                    )
                    if graph_date_ok:
                        montant_planifie_graph += montant_ligne
                        if est_paye:
                            montant_paye_graph += montant_ligne
                    if (not est_paye) and (not est_pointe):
                        has_facture_echue_non_pointee = True
                        if date_locale < debut_mois_repere:
                            has_facture_echue_avant_mois = True
                        else:
                            has_facture_echue_mois_courant = True
                    if not est_pointe:
                        montant_forfaitaire_non_pointe += montant_ligne
                        if paiement.date_encaissement:
                            montant_encaisse_non_pointe += montant_ligne

                mois = date_locale.month
                quantite = int(paiement.quantite) if paiement.quantite else 1

                if paiement.numeroDiameX:
                    nb_tranches_payees += quantite
                elif date_locale <= limit_date:
                    nb_tranches_non_payees_echues += quantite
                    qte_non_payee_echue += quantite
                else:
                    nb_tranches_non_payees_non_echues += quantite

                mois_data = mois_stats[mois]
                if paiement.numeroDiameX:
                    mois_data['paye'] += quantite
                    mois_data['paye_montant'] += montant_ligne
                else:
                    mois_data['non_paye'] += quantite
                    mois_data['non_paye_montant'] += montant_ligne

                for trimestre, data in trimestres.items():
                    if trimestre == 'planifie_annee': continue
                    if mois in data['mois']:
                        if paiement.numeroDiameX:
                            data['paye'] += quantite
                            data['paye_montant'] += montant_ligne
                        else:
                            data['non_paye'] += quantite
                            data['non_paye_montant'] += montant_ligne
                        break

        # Calculer les totaux pour les statistiques
        qte_payee = sum(t['paye'] for k, t in trimestres.items() if k != 'planifie_annee')
        qte_non_payee = sum(t['non_paye'] for k, t in trimestres.items() if k != 'planifie_annee')
        qte_totale = qte_payee + qte_non_payee

        tranches_reference, trimestres_sans_eau = calculate_expected_tranches(pe, annee)
        tranches_ecart = qte_totale - tranches_reference
        prochaine_echeance = None
        if tranches_ecart == 0:
            tranches_controle_badge = 'success'
            tranches_controle_action = 'Conforme'
            tranches_controle_detail = (
                f'Somme des tranches = {tranches_reference}'
                + (f' ({trimestres_sans_eau} trimestre(s) sans eau)' if trimestres_sans_eau else '')
            )
            nb_tranches_ok += 1
        elif tranches_ecart < 0:
            tranches_controle_badge = 'warning'
            tranches_controle_action = f'Ajouter {abs(tranches_ecart)}'
            tranches_controle_detail = (
                f'{abs(tranches_ecart)} tranche(s) manquante(s)'
                + (f' apres deduction de {trimestres_sans_eau} trimestre(s) sans eau' if trimestres_sans_eau else '')
            )
            nb_tranches_a_completer += 1
        else:
            # Un paiement qui depasse le nombre de tranches attendues cette
            # annee n'est pas une erreur a corriger : c'est une avance dont la
            # couverture court au-dela de l'annee en cours. La prochaine
            # echeance est projetee a partir du cumul de tranches payees
            # depuis le debut de la modalite (3 mois par tranche).
            date_debut_modalite_pe = modalite_debut_par_ouvrage.get(pe.ouvrage_id)
            tranches_realisees_cumul = tranches_realisees_cumul_par_point.get(str(pe.id), qte_totale)
            ancrage_echeance = date_debut_modalite_pe or datetime(annee, 1, 1).date()
            prochaine_echeance_date = ancrage_echeance + relativedelta(months=3 * tranches_realisees_cumul)
            prochaine_echeance = prochaine_echeance_date.strftime('%d/%m/%Y')
            tranches_controle_badge = 'info'
            tranches_controle_action = f"Payé d'avance jusqu'en {prochaine_echeance_date.strftime('%m/%Y')}"
            tranches_controle_detail = (
                f'{tranches_ecart} tranche(s) payee(s) d\'avance, couverture jusqu\'en {prochaine_echeance_date.strftime("%m/%Y")}'
                + (f' (apres deduction de {trimestres_sans_eau} trimestre(s) sans eau)' if trimestres_sans_eau else '')
            )
            nb_tranches_a_corriger += 1

        montant_paye = Decimal(qte_payee) * tarif if tarif > 0 else Decimal('0.00')
        
        # Déterminer le statut
        dernier_evenement_coupure = derniers_evenements_coupure.get(str(pe.id))
        est_coupe = bool(
            (dernier_evenement_coupure and dernier_evenement_coupure.type_evenement == 'coupure')
            or pe.datearretbranchement is not None
        )
        date_arret = (
            dernier_evenement_coupure.date_evenement
            if dernier_evenement_coupure and dernier_evenement_coupure.type_evenement == 'coupure'
            else pe.datearretbranchement
        )

        if est_coupe:
            statut = 'coupe'
            statut_label = 'Coupé'
            statut_badge = 'error'
            statut_icon = 'scissors'
            nb_coupe += 1
        elif qte_payee == 0:
            statut = 'non_paye'
            statut_label = 'Non payé'
            statut_badge = 'ghost'
            statut_icon = 'times-circle'
            nb_non_paye += 1
        elif qte_non_payee_echue == 0 and qte_payee > 0:
            statut = 'tout_paye'
            statut_label = 'Tout payé'
            statut_badge = 'success'
            statut_icon = 'check-circle'
            nb_tout_paye += 1
        else:
            statut = 'partiellement_paye'
            statut_label = 'Partiellement payé'
            statut_badge = 'warning'
            statut_icon = 'exclamation-circle'
            nb_partiellement_paye += 1

        montant_prevu_total += montant_prevu_annuel
        montant_paye_total += montant_paye
        decote_totale_globale += decote_montant
        montant_planifie_total += trimestres['planifie_annee']

        # Commune
        commune_nom = pe.parcelle.village.fokontany.commune.nom_commune if (
            pe.parcelle and
            pe.parcelle.village and
            pe.parcelle.village.fokontany and
            pe.parcelle.village.fokontany.commune
        ) else 'Non assignée'

        coupure_periodes = compute_coupure_periodes(pe)
        mois_coupes = set()
        for periode_coupure in coupure_periodes:
            for mois_num in range(periode_coupure['debut'].month, periode_coupure['fin'].month + 1):
                mois_coupes.add(mois_num)
        a_ete_coupe = bool(coupure_periodes)
        coupe_puis_remis = a_ete_coupe and not est_coupe

        mois_cells = []
        for idx, label in enumerate(mois_labels, start=1):
            mois_data = mois_stats[idx]
            mois_cells.append({
                'numero': idx,
                'label': label,
                'is_current_month': idx == mois_repere_numero,
                'paye': mois_data['paye'],
                'non_paye': mois_data['non_paye'],
                'paye_montant': mois_data['paye_montant'],
                'non_paye_montant': mois_data['non_paye_montant'],
                'coupe': idx in mois_coupes,
            })

        montant_compta_total = point_compta_total.get(pe.id, Decimal('0.00'))
        montant_compta_non_pointe = point_compta_non_pointe.get(pe.id, Decimal('0.00'))
        nb_lignes_diamex_non_pointees = point_compta_non_pointe_count.get(pe.id, 0)
        montant_ecart_compta = montant_forfaitaire_non_pointe - montant_compta_non_pointe

        date_debut_gestion_ouvrage = modalite_debut_par_ouvrage.get(pe.ouvrage_id)

        points_eau_list.append({
            'id': pe.id,
            'ouvrage_id': pe.ouvrage_id,
            'nom': pe.code_point_eau or pe.nomabonne or f'Point eau {pe.id}',
            'idxls': pe.idxls or '',  # Ajout de l'idxls
            'nomabonne': pe.nomabonne,
            'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
            'date_debut_gestion': date_debut_gestion_ouvrage,
            'date_debut_gestion_annee_courante': bool(
                date_debut_gestion_ouvrage and date_debut_gestion_ouvrage.year == annee
            ),
            'type_point_eau': pe.type_point_eau.nom_type if pe.type_point_eau else 'N/A',
            'est_institutionnel': bool(pe.estbranchementinstitutionnel),
            'commune': commune_nom,
            'tarif_forfaitaire': tarif,
            'montant_prevu_annuel': montant_prevu_annuel,
            'qte_totale': qte_totale,
            'qte_payee': qte_payee,
            'qte_non_payee': qte_non_payee,
            'tranches_reference': tranches_reference,
            'trimestres_sans_eau': trimestres_sans_eau,
            'tranches_annuelles': qte_totale,
            'tranches_ecart': tranches_ecart,
            'tranches_controle_badge': tranches_controle_badge,
            'tranches_controle_action': tranches_controle_action,
            'tranches_controle_detail': tranches_controle_detail,
            'prochaine_echeance': prochaine_echeance,
            'montant_paye': montant_paye,
            'montant_factures_total': trimestres['planifie_annee'],
            'montant_planifie_graph': montant_planifie_graph,
            'montant_paye_graph': montant_paye_graph,
            'montant_recettes_compta': montant_compta_total,
            'montant_forfaitaire_non_pointe': montant_forfaitaire_non_pointe,
            'montant_encaisse_non_pointe': montant_encaisse_non_pointe,
            'montant_compta_non_pointe': montant_compta_non_pointe,
            'nb_lignes_diamex_non_pointees': nb_lignes_diamex_non_pointees,
            'has_diamex_non_pointe': nb_lignes_diamex_non_pointees > 0,
            'montant_ecart_compta': montant_ecart_compta,
            'has_facture_echue_non_pointee': has_facture_echue_non_pointee,
            'has_facture_echue_avant_mois': has_facture_echue_avant_mois,
            'has_facture_echue_mois_courant': has_facture_echue_mois_courant,
            'statut': statut,
            'statut_label': statut_label,
            'statut_badge': statut_badge,
            'statut_icon': statut_icon,
            'est_coupe': est_coupe,
            'a_ete_coupe': a_ete_coupe,
            'coupe_puis_remis': coupe_puis_remis,
            'coupure_periodes': coupure_periodes,
            'date_arret': date_arret,
            'mois_cells': mois_cells,
            'est_tout_paye': (statut == 'tout_paye'),  # Indicateur tout payé
            # Données par trimestre
            'T1_paye': trimestres['T1']['paye'],
            'T1_non_paye': trimestres['T1']['non_paye'],
            'T1_paye_montant': trimestres['T1']['paye_montant'],
            'T1_non_paye_montant': trimestres['T1']['non_paye_montant'],
            'T2_paye': trimestres['T2']['paye'],
            'T2_non_paye': trimestres['T2']['non_paye'],
            'T2_paye_montant': trimestres['T2']['paye_montant'],
            'T2_non_paye_montant': trimestres['T2']['non_paye_montant'],
            'T3_paye': trimestres['T3']['paye'],
            'T3_non_paye': trimestres['T3']['non_paye'],
            'T3_paye_montant': trimestres['T3']['paye_montant'],
            'T3_non_paye_montant': trimestres['T3']['non_paye_montant'],
            'T4_paye': trimestres['T4']['paye'],
            'T4_non_paye': trimestres['T4']['non_paye'],
            'T4_paye_montant': trimestres['T4']['paye_montant'],
            'T4_non_paye_montant': trimestres['T4']['non_paye_montant'],
        })

    # Jeu consolide reutilise pour les graphiques, sans relancer les calculs par commune.
    points_eau_chart_list = list(points_eau_list)

    score_point_ids = {str(point['id']) for point in points_eau_list}
    score_totals_by_point = {}
    point_tarifs = {
        str(point_eau.id): Decimal(str(point_eau.tarifforfaitaire or 0))
        for point_eau in points_eau_materialized
    }
    score_reference_month = timezone.localdate().replace(day=1)
    for point_id, paiements_point in paiements_by_point.items():
        normalized_point_id = str(point_id)
        if normalized_point_id not in score_point_ids:
            continue
        for paiement in paiements_point:
            paiement_date = get_paiement_date(paiement)
            if not paiement_date or not is_closed_payment_month(paiement_date, score_reference_month):
                continue
            if date_debut_value and paiement_date < date_debut_value:
                continue
            if date_fin_value and paiement_date > date_fin_value:
                continue
            montant = (
                Decimal(str(paiement.montant))
                if paiement.montant is not None
                else Decimal(str(paiement.quantite or 1)) * point_tarifs.get(normalized_point_id, Decimal('0'))
            )
            totals = score_totals_by_point.setdefault(
                normalized_point_id,
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
            employee_id=employe_filter,
            ouvrage_id=ouvrage_filter,
            commune_id=commune_filter,
            district_id=district_filter,
            region_id=region_filter,
            default_organisation_name=getattr(organisation_user, 'nom_organisation', '') or '',
        ),
    })

    # Base de répartition des statuts (avant filtres de liste par statut/impayés échus)
    nb_points_eau_stats = len(points_eau_list)

    if show_only_score_gap:
        points_eau_list = [
            point for point in points_eau_list
            if str(point['id']) in score_gap_point_ids
        ]

    # Filtrer par statut si demandé
    if statut_filter == 'coupe_remis':
        points_eau_list = [p for p in points_eau_list if p['coupe_puis_remis']]
    elif statut_filter == 'a_ete_coupe':
        points_eau_list = [p for p in points_eau_list if p['a_ete_coupe']]
    elif statut_filter:
        points_eau_list = [p for p in points_eau_list if p['statut'] == statut_filter]
    if impayes_echus_mode == 'tous':
        points_eau_list = [p for p in points_eau_list if p['has_facture_echue_non_pointee']]
    elif impayes_echus_mode == 'avant_mois':
        points_eau_list = [p for p in points_eau_list if p['has_facture_echue_avant_mois']]
    elif impayes_echus_mode == 'mois_courant':
        points_eau_list = [p for p in points_eau_list if p['has_facture_echue_mois_courant']]

    # Les cartes de controle de tranches decrivent le perimetre obtenu apres
    # les filtres usuels, mais avant leur propre filtre interactif.
    points_eau_controle_stats = list(points_eau_list)
    nb_points_eau_tranches_stats = len(points_eau_controle_stats)
    nb_tranches_ok = sum(1 for p in points_eau_controle_stats if p['tranches_ecart'] == 0)
    nb_tranches_a_completer = sum(1 for p in points_eau_controle_stats if p['tranches_ecart'] < 0)
    nb_tranches_a_corriger = sum(1 for p in points_eau_controle_stats if p['tranches_ecart'] > 0)

    if controle_tranches_filter == 'a_completer':
        points_eau_list = [p for p in points_eau_list if p['tranches_ecart'] < 0]
    elif controle_tranches_filter == 'a_corriger':
        points_eau_list = [p for p in points_eau_list if p['tranches_ecart'] > 0]

    # La carte DiameX décrit le périmètre courant avant d'appliquer son propre
    # filtre. Elle reste ainsi visible et désactivable pendant le filtrage.
    points_eau_diamex_stats = list(points_eau_list)
    nb_points_diamex_non_pointes = sum(
        1 for point in points_eau_diamex_stats if point['has_diamex_non_pointe']
    )
    nb_lignes_diamex_non_pointees = sum(
        point['nb_lignes_diamex_non_pointees'] for point in points_eau_diamex_stats
    )
    if show_only_diamex_non_pointes:
        points_eau_list = [p for p in points_eau_list if p['has_diamex_non_pointe']]

    # La repartition par statut doit toujours decrire exactement les lignes
    # restantes apres tous les filtres rapides et les filtres du formulaire.
    nb_points_eau_stats = len(points_eau_list)
    nb_tout_paye = sum(1 for p in points_eau_list if p['statut'] == 'tout_paye')
    nb_partiellement_paye = sum(1 for p in points_eau_list if p['statut'] == 'partiellement_paye')
    nb_non_paye = sum(1 for p in points_eau_list if p['statut'] == 'non_paye')
    nb_coupe = sum(1 for p in points_eau_list if p['statut'] == 'coupe')
    nb_coupe_remis = sum(1 for p in points_eau_list if p['coupe_puis_remis'])

    visible_month_numbers = [
        month_number
        for month_number in range(1, 13)
        if any(
            any(
                cell['numero'] == month_number and (
                    int(cell.get('paye') or 0) > 0
                    or int(cell.get('non_paye') or 0) > 0
                    or Decimal(str(cell.get('paye_montant') or 0)) > 0
                    or Decimal(str(cell.get('non_paye_montant') or 0)) > 0
                    or cell.get('coupe')
                )
                for cell in point['mois_cells']
            )
            for point in points_eau_list
        )
    ]
    for point in points_eau_list:
        point['visible_mois_cells'] = [
            cell
            for cell in point['mois_cells']
            if cell['numero'] in visible_month_numbers
        ]
        point['mobile_mois_cells'] = [
            cell
            for cell in point['visible_mois_cells']
            if int(cell.get('paye') or 0) > 0 or int(cell.get('non_paye') or 0) > 0
        ]

    # Définition d'une fonction de tri pour IDXls numérique
    def get_pe_sort_key(p):
        idxls = str(p.get('idxls', '')).strip()
        # Commune first, then ouvrage.
        ouvrage = p.get('ouvrage', '')
        commune = p.get('commune', '')
        
        # Parse numeric parts of IDXls
        import re
        try:
            # Essayer d'extraire le premier nombre
            match = re.search(r'\d+', idxls)
            num = int(match.group()) if match else 999999
        except (ValueError, TypeError, AttributeError):
            num = 999999
            
        return (commune, ouvrage, num, idxls)

    # Trier par ouvrage, commune puis IDXls numérique
    points_eau_list.sort(key=get_pe_sort_key)

    # Ajouter une propriété pour détecter le changement d'ouvrage
    prev_commune = None
    prev_ouvrage = None
    for point in points_eau_list:
        point['nouvelle_commune'] = (point['commune'] != prev_commune)
        point['nouveau_ouvrage'] = point['nouvelle_commune'] or (point['ouvrage'] != prev_ouvrage)
        prev_commune = point['commune']
        prev_ouvrage = point['ouvrage']

    # Export Excel des paiements prévus par point d'eau et par mois : mêmes
    # points que la page (tous filtres appliqués), sans pagination.
    if request.GET.get('export') == 'excel':
        from apps.core.export_paiements_forfaitaires import export_paiements_prevus_excel
        return export_paiements_prevus_excel(points_eau_list, annee)

    # Pagination
    page_number = request.GET.get('page', 1)
    paginator = Paginator(points_eau_list, 50)  # 50 lignes par page
    page_obj = paginator.get_page(page_number)

    # Convertir en milliers pour affichage
    montant_prevu_k = round(float(montant_prevu_total) / 1000)
    montant_planifie_k = round(float(montant_planifie_total) / 1000)
    montant_paye_k = round(float(montant_paye_total) / 1000)
    decote_totale_k = round(float(decote_totale_globale) / 1000)
    ecart_planifie_vs_prevu = montant_planifie_total - montant_prevu_total
    ecart_planifie_vs_prevu_k = round(float(ecart_planifie_vs_prevu) / 1000)

    ecart_planifie_vs_prevu_pct = 0
    if montant_prevu_total > 0:
        ecart_planifie_vs_prevu_pct = int(round((float(ecart_planifie_vs_prevu) / float(montant_prevu_total)) * 100))

    planifie_vs_prevu_pct = 0
    if montant_prevu_total > 0:
        planifie_vs_prevu_pct = int(round((float(montant_planifie_total) / float(montant_prevu_total)) * 100))

    # Compter les ouvrages (distincts dans la liste filtrée)
    nb_ouvrages = len(set(p['ouvrage'] for p in points_eau_list))

    # Recouvrement reel par mois de facturation (mois passes vs mois en cours),
    # base sur les paiements individuels (mois_cells calcules plus haut), independamment
    # du decoupage trimestriel des tranches attendues. Mirroir de la logique utilisee
    # sur le dashboard paiements au volume.
    if annee < today.year:
        mois_passes_set_forfait = set(range(1, 13))
        mois_en_cours_set_forfait = set()
    elif annee == today.year:
        mois_passes_set_forfait = set(range(1, mois_repere_numero))
        mois_en_cours_set_forfait = {mois_repere_numero}
    else:
        mois_passes_set_forfait = set()
        mois_en_cours_set_forfait = set()

    montant_prevu_mois_passes_forfait = Decimal('0.00')
    montant_paye_mois_passes_forfait = Decimal('0.00')
    montant_prevu_mois_en_cours_forfait = Decimal('0.00')
    montant_paye_mois_en_cours_forfait = Decimal('0.00')

    for point in points_eau_list:
        for cell in point.get('mois_cells', []):
            numero_mois = cell['numero']
            paye_montant_cell = Decimal(str(cell.get('paye_montant') or 0))
            non_paye_montant_cell = Decimal(str(cell.get('non_paye_montant') or 0))
            prevu_montant_cell = paye_montant_cell + non_paye_montant_cell
            if numero_mois in mois_passes_set_forfait:
                montant_prevu_mois_passes_forfait += prevu_montant_cell
                montant_paye_mois_passes_forfait += paye_montant_cell
            elif numero_mois in mois_en_cours_set_forfait:
                montant_prevu_mois_en_cours_forfait += prevu_montant_cell
                montant_paye_mois_en_cours_forfait += paye_montant_cell

    # Decote (manque a facturer du aux coupures d'eau) repartie sur les memes
    # deux periodes, par difference de cumul (logique deja utilisee pour
    # decote_totale_globale, appliquee a deux dates de reference distinctes).
    from calendar import monthrange as _monthrange_forfait

    if annee < today.year:
        fin_mois_passes_forfait = fin_annee
    elif annee == today.year and mois_repere_numero > 1:
        dernier_mois_passe_forfait = mois_repere_numero - 1
        dernier_jour_forfait = _monthrange_forfait(annee, dernier_mois_passe_forfait)[1]
        fin_mois_passes_forfait = date_class(annee, dernier_mois_passe_forfait, dernier_jour_forfait)
    else:
        fin_mois_passes_forfait = None

    if fin_mois_passes_forfait:
        decote_mois_passes_forfait = sum(
            (calculate_details_financiers(pe, annee, fin_mois_passes_forfait)[1] for pe in points_eau_materialized),
            Decimal('0.00')
        )
    else:
        decote_mois_passes_forfait = Decimal('0.00')

    decote_mois_en_cours_forfait = max(
        Decimal('0.00'), decote_totale_globale - decote_mois_passes_forfait
    )

    def _totaux_recouvrement_mois_forfait(total_prevu, total_paye, nb_mois, decote):
        taux = int(round((float(total_paye) / float(total_prevu)) * 100)) if total_prevu > 0 else 0
        ecart = total_prevu - total_paye
        return {
            'total_prevu': total_prevu,
            'total_paye': total_paye,
            'total_prevu_k': round(float(total_prevu) / 1000),
            'total_paye_k': round(float(total_paye) / 1000),
            'ecart': ecart,
            'ecart_k': round(float(ecart) / 1000),
            'decote': decote,
            'decote_k': round(float(decote) / 1000),
            'taux': taux,
            'progression': min(taux, 100),
            'has_data': (total_prevu > 0 or decote > 0),
            'nb_mois': nb_mois,
        }

    recouvrement_mois_passes_forfait = _totaux_recouvrement_mois_forfait(
        montant_prevu_mois_passes_forfait, montant_paye_mois_passes_forfait,
        len(mois_passes_set_forfait), decote_mois_passes_forfait
    )
    recouvrement_mois_en_cours_forfait = _totaux_recouvrement_mois_forfait(
        montant_prevu_mois_en_cours_forfait, montant_paye_mois_en_cours_forfait,
        len(mois_en_cours_set_forfait), decote_mois_en_cours_forfait
    )
    noms_mois_fr_forfait = [
        '', 'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre'
    ]
    recouvrement_mois_en_cours_forfait['libelle_mois'] = (
        noms_mois_fr_forfait[mois_repere_numero]
        if mois_en_cours_set_forfait
        else ''
    )
    afficher_recouvrement_mois_en_cours_forfait = (annee == today.year)

    ouvrages_recouvrement = {}
    for point in points_eau_list:
        ouvrage_nom = point.get('ouvrage') or 'N/A'
        if ouvrage_nom not in ouvrages_recouvrement:
            ouvrages_recouvrement[ouvrage_nom] = {
                'montant_prevu_annuel': Decimal('0.00'),
                'montant_paye': Decimal('0.00'),
            }
        ouvrages_recouvrement[ouvrage_nom]['montant_prevu_annuel'] += Decimal(str(point.get('montant_prevu_annuel') or 0))
        ouvrages_recouvrement[ouvrage_nom]['montant_paye'] += Decimal(str(point.get('montant_paye') or 0))
    nb_ouvrages_recouvrement_100 = sum(
        1
        for data in ouvrages_recouvrement.values()
        if data['montant_prevu_annuel'] > 0 and data['montant_paye'] >= data['montant_prevu_annuel']
    )

    # Calculer les taux de recouvrement
    taux_recouvrement_prevu = 0
    if montant_prevu_total > 0:
        taux_recouvrement_prevu = int(round((float(montant_paye_total) / float(montant_prevu_total)) * 100))

    taux_recouvrement_planifie = 0
    if montant_planifie_total > 0:
        taux_recouvrement_planifie = int(round((float(montant_paye_total) / float(montant_planifie_total)) * 100))

    planifie_vs_prevu_ok = montant_planifie_total >= montant_prevu_total
    paye_vs_planifie_ok = montant_paye_total >= montant_planifie_total
    recouvrement_prevu_ok = taux_recouvrement_prevu >= 100
    recouvrement_planifie_ok = taux_recouvrement_planifie >= 100

    # Calculer prévu, planifié, payé par commune (Top 10) pour le graphique
    communes_stats = []
    # Les donnees du graphique sont deja disponibles dans points_eau_chart_list.
    # On neutralise l'ancien parcours ORM par commune pour eviter un second N+1.
    communes_list = Commune.objects.none()
    if region_filter:
        communes_list = communes_list.filter(district__region_id=region_filter)
    if district_filter:
        communes_list = communes_list.filter(district_id=district_filter)
    if commune_filter:
        communes_list = communes_list.filter(id=commune_filter)

    for commune in communes_list:
        # Points d'eau de cette commune (avec filtre modalité)
        points_eau_commune = PointEau.objects.filter(
            tarifforfaitaire__isnull=False,
            parcelle__village__fokontany__commune=commune,
            ouvrage_id__in=ouvrages_forfaitaires_ids  # FILTRE MODALITE
        )

        # Appliquer le filtre ouvrage si présent
        if ouvrage_filter:
            points_eau_commune = points_eau_commune.filter(ouvrage_id=ouvrage_filter)

        # Montant prévu ajusté (NET = Brut - Décote)
        montant_prevu = sum([calculate_details_financiers(pe, annee, limit_date)[2] for pe in points_eau_commune], Decimal('0.00'))

        # Paiements pour cette commune (avec filtre modalité)
        paiements_commune = PaiementForfaitaire.objects.filter(
            point_eau__parcelle__village__fokontany__commune=commune,
            point_eau__ouvrage_id__in=ouvrages_forfaitaires_ids  # FILTRE MODALITE
        )

        # Appliquer les filtres
        if ouvrage_filter:
            paiements_commune = paiements_commune.filter(point_eau__ouvrage_id=ouvrage_filter)
        if date_debut:
            paiements_commune = paiements_commune.filter(
                Q(planning__date__date__gte=date_debut) | Q(planning__isnull=True, date_facture__gte=date_debut)
            )
        if date_fin:
            paiements_commune = paiements_commune.filter(
                Q(planning__date__date__lte=date_fin) | Q(planning__isnull=True, date_facture__lte=date_fin)
            )

        # Montant Planifié (Filtré YTD)
        # On doit récupérer les paiements et filtrer Python-side ou utiliser une requÃªte complexe avec annotations de date
        # Pour simplifier etêtre cohérent avec get_paiement_date, on peut itérer. Mais pour les perfs c'est moyen.
        # Vu le nombre de communes (Top 10), itérer sur les paiements est acceptable si pas trop nombreux.
        # Ou on filtre grossièrement par date_facture / planning__date__date <= limit_date
        
        # Filtre sur la date limite (YTD)
        paiements_commune_ytd = paiements_commune.filter(
             Q(planning__date__date__lte=limit_date) | Q(planning__isnull=True, date_facture__lte=limit_date)
        )

        montant_planifie = paiements_commune_ytd.aggregate(total=Sum('montant'))['total'] or Decimal('0.00')

        # Paiements payés (avec numeroDiameX non null)
        # Payé reste payé, peu importe la date planifiée ? 
        # "Paiement planifié, il faut prendre en compte seulement les paiements de date passé"
        # Pour "Paiement Payé", l'user n'a pas spécifié de filtre date, mais logiquement c'est aussi YTD ?
        # Si un paiement est fait en avance pour décembre alors qu'on est en janvier ?
        # Généralement "Payé" est un fait comptable. Si l'argent est lÃ , il est lÃ .
        # Mais pour la comparabilité (Recouvrement), comparer Payé total vs Prévu YTD peut donner > 100%.
        # On va assumer que Payé suit la mÃªme logique temporelle (paiements enregistrés jusqu'Ã  aujourd'hui).
        # Le filtre `paiements_commune_ytd` s'applique aussi au payé si on veutêtre strict sur la date du paiement.
        # Mais `date_facture` ou `planning` n'est pas forcément la date de paiement réelle (date du reçu).
        # On va garder `paiements_commune.filter` (sans limite YTD stricte) ou `paiements_commune_ytd` ?
        # Dans le doute, on applique le mÃªme filtre temporel que planifié pour cohérence.
        
        montant_paye = paiements_commune_ytd.filter(
            numeroDiameX__isnull=False
        ).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')

        if montant_prevu > 0 or montant_planifie > 0 or montant_paye > 0:
            communes_stats.append({
                'commune': commune.nom_commune,
                'prevu': float(montant_prevu),
                'planifie': float(montant_planifie),
                'paye': float(montant_paye),
            })

    communes_aggregates = {}
    for point in points_eau_chart_list:
        commune_nom = point.get('commune') or 'Non assignee'
        aggregate = communes_aggregates.setdefault(commune_nom, {
            'commune': commune_nom,
            'prevu': Decimal('0.00'),
            'planifie': Decimal('0.00'),
            'paye': Decimal('0.00'),
        })
        aggregate['prevu'] += Decimal(str(point.get('montant_prevu_annuel') or 0))
        aggregate['planifie'] += Decimal(str(point.get('montant_planifie_graph') or 0))
        aggregate['paye'] += Decimal(str(point.get('montant_paye_graph') or 0))

    communes_stats = [
        {
            'commune': aggregate['commune'],
            'prevu': float(aggregate['prevu']),
            'planifie': float(aggregate['planifie']),
            'paye': float(aggregate['paye']),
        }
        for aggregate in communes_aggregates.values()
        if aggregate['prevu'] > 0 or aggregate['planifie'] > 0 or aggregate['paye'] > 0
    ]

    total_tranches_stats = (
        nb_tranches_payees
        + nb_tranches_non_payees_echues
        + nb_tranches_non_payees_non_echues
    )
    def compute_percentage(value, total):
        if not total:
            return 0
        return int(round((value * 100) / total))

    pct_tranches_ok = compute_percentage(nb_tranches_ok, nb_points_eau_tranches_stats)
    pct_tranches_a_completer = compute_percentage(nb_tranches_a_completer, nb_points_eau_tranches_stats)
    pct_tranches_a_corriger = compute_percentage(nb_tranches_a_corriger, nb_points_eau_tranches_stats)
    pct_tranches_payees = compute_percentage(nb_tranches_payees, total_tranches_stats)
    pct_tranches_non_payees_echues = compute_percentage(nb_tranches_non_payees_echues, total_tranches_stats)
    pct_tranches_non_payees_non_echues = compute_percentage(nb_tranches_non_payees_non_echues, total_tranches_stats)

    # Trier par montant prévu décroissant et garder top 10
    communes_stats = sorted(communes_stats, key=lambda x: x['prevu'], reverse=True)[:10]

    # Générer la liste des années disponibles (de 2020 Ã  année courante + 1)
    annees_disponibles = list(range(2020, datetime.now().year + 2))
    mois_colonnes = [
        {'numero': idx + 1, 'label': label}
        for idx, label in enumerate(mois_labels)
        if (idx + 1) in visible_month_numbers
    ]

    return render(request, 'core/dashboard_payments_flat.html', {
        'debit_scope_ids': {p['ouvrage_id'] for p in points_eau_list if p.get('ouvrage_id')},
        'title': 'Tableau de bord Paiements Forfaitaires',
        'points_eau': page_obj.object_list,
        'page_obj': page_obj,
        'total_lignes': len(points_eau_list),
        'nb_points_eau': len(points_eau_list),
        'nb_ouvrages': nb_ouvrages,  # Ajout du nombre d'ouvrages
        'nb_ouvrages_recouvrement_100': nb_ouvrages_recouvrement_100,
        'montant_prevu': montant_prevu_total,
        'montant_prevu_k': montant_prevu_k,
        'decote_totale': decote_totale_globale,
        'decote_totale_k': decote_totale_k,  # Ajout de la version K
        'montant_planifie': montant_planifie_total,
        'montant_planifie_k': montant_planifie_k,
        'ecart_planifie_vs_prevu': ecart_planifie_vs_prevu,
        'ecart_planifie_vs_prevu_k': ecart_planifie_vs_prevu_k,
        'ecart_planifie_vs_prevu_pct': ecart_planifie_vs_prevu_pct,
        'planifie_vs_prevu_pct': planifie_vs_prevu_pct,
        'montant_paye': montant_paye_total,
        'montant_paye_k': montant_paye_k,
        'taux_recouvrement_prevu': taux_recouvrement_prevu,
        'taux_recouvrement_planifie': taux_recouvrement_planifie,
        'planifie_vs_prevu_ok': planifie_vs_prevu_ok,
        'paye_vs_planifie_ok': paye_vs_planifie_ok,
        'recouvrement_prevu_ok': recouvrement_prevu_ok,
        'recouvrement_planifie_ok': recouvrement_planifie_ok,
        'nb_tout_paye': nb_tout_paye,
        'nb_partiellement_paye': nb_partiellement_paye,
        'nb_non_paye': nb_non_paye,
        'nb_coupe': nb_coupe,
        'nb_coupe_remis': nb_coupe_remis,
        'nb_points_diamex_non_pointes': nb_points_diamex_non_pointes,
        'nb_lignes_diamex_non_pointees': nb_lignes_diamex_non_pointees,
        'nb_tranches_ok': nb_tranches_ok,
        'nb_tranches_a_completer': nb_tranches_a_completer,
        'nb_tranches_a_corriger': nb_tranches_a_corriger,
        'nb_tranches_payees': nb_tranches_payees,
        'nb_tranches_non_payees_echues': nb_tranches_non_payees_echues,
        'nb_tranches_non_payees_non_echues': nb_tranches_non_payees_non_echues,
        'nb_points_eau_stats': nb_points_eau_stats,
        'nb_points_eau_tranches_stats': nb_points_eau_tranches_stats,
        'total_tranches_stats': total_tranches_stats,
        'pct_annee_ecoulee': pct_annee_ecoulee,
        'mois_repere_numero': mois_repere_numero,
        'mois_repere_label': mois_repere_label,
        'date_repere': limit_date,
        'recouvrement_mois_passes': recouvrement_mois_passes_forfait,
        'recouvrement_mois_en_cours': recouvrement_mois_en_cours_forfait,
        'afficher_recouvrement_mois_en_cours': afficher_recouvrement_mois_en_cours_forfait,
        'pct_tranches_ok': pct_tranches_ok,
        'pct_tranches_a_completer': pct_tranches_a_completer,
        'pct_tranches_a_corriger': pct_tranches_a_corriger,
        'pct_tranches_payees': pct_tranches_payees,
        'pct_tranches_non_payees_echues': pct_tranches_non_payees_echues,
        'pct_tranches_non_payees_non_echues': pct_tranches_non_payees_non_echues,
        'communes_stats': json.dumps(communes_stats),
        'regions': regions,
        'districts': districts,
        'districts_all': districts_all,
        'communes': communes,
        'communes_all': communes_all,
        'ouvrages': ouvrages,
        'employes_responsables': employes_responsables,
        'employee_points_score': employee_points_score,
        'show_only_score_gap': show_only_score_gap,
        'types_point_eau': types_point_eau,
        'mois_colonnes': mois_colonnes,
        'region_filter': region_filter,
        'district_filter': district_filter,
        'commune_filter': commune_filter,
        'ouvrage_filter': ouvrage_filter,
        'employe_filter': employe_filter,
        'type_point_eau_filter': type_point_eau_filter,
        'statut_filter': statut_filter,
        'show_only_impayes_echus': show_only_impayes_echus,
        'impayes_echus_mode': impayes_echus_mode,
        'controle_tranches_filter': controle_tranches_filter,
        'show_only_diamex_non_pointes': show_only_diamex_non_pointes,
        'annee_filter': annee_filter,
        'annees_disponibles': annees_disponibles,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'can_manage_forfaitaire_factures': can_manage_forfaitaire_factures(request.user),
    })


def dashboard_payments_flat_kanban(request):
    """Vue Kanban des paiements forfaitaires avec colonnes par statut"""
    from apps.billing.models import PointEau, ModaliteGestion, PaiementForfaitaire, CoupureEau
    from apps.organization.models import Ouvrage
    from django.db.models import Q, Count, Sum
    from datetime import datetime, timedelta
    from decimal import Decimal
    import json
    import pytz

    # CRITICAL: Récupérer uniquement les ouvrages avec modalité forfaitaire ou mixte
    ouvrages_forfaitaires_ids = set(ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['forfaitaire', 'mixte']
    ).values_list('ouvrage_id', flat=True).distinct())
    ouvrages_forfaitaires_ids = apply_user_responsable_ouvrage_scope(
        ouvrages_forfaitaires_ids,
        request.user,
        allow_same_base_support_roles=True,
    )
    ouvrages_filter_scope = set(ouvrages_forfaitaires_ids)

    # Filtres
    employe_filter = request.GET.get('employe', '')
    region_filter = request.GET.get('region', '')
    district_filter = request.GET.get('district', '')
    commune_filter = request.GET.get('commune', '')
    ouvrage_filter = request.GET.get('ouvrage', '')
    type_point_eau_filter = request.GET.get('type_point_eau', '')
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    annee = int(annee_filter)
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    employes_responsables, ouvrages_forfaitaires_ids = resolve_dashboard_employee_filter(
        ouvrages_forfaitaires_ids,
        employe_filter,
    )
    if employe_filter and not any(
        str(option.get('id', '')) == str(employe_filter)
        for option in employes_responsables
    ):
        employe_filter = ''

    # --- LOGIQUE YTD (Date Limite) ---
    today = datetime.now().date()
    debut_annee = datetime(annee, 1, 1).date()
    fin_annee = datetime(annee, 12, 31).date()
    
    if annee < today.year:
        limit_date = fin_annee
    else:
        limit_date = min(today, fin_annee)

    if limit_date < debut_annee:
        limit_date = debut_annee

    # --- HELPER FINANCIER (Dupliqué pour isolation) ---
    def calculate_details_financiers(pe, annee, limit_date):
        tarif = tarif_pour_annee(pe, annee)
        if tarif == 0:
            return Decimal('0.00'), Decimal('0.00'), Decimal('0.00')

        debut_annee = datetime(annee, 1, 1).date()
        
        if limit_date < debut_annee:
            nb_mois_ecoules = 0
        else:
            delta_jours = (limit_date - debut_annee).days + 1
            nb_mois_ecoules = int(round(delta_jours / 30.4))
            
        montant_brut = (tarif / 3) * nb_mois_ecoules

        or_debut = CoupureEau.objects.filter(point_eau=pe, date_evenement__lt=debut_annee).order_by('-date_evenement').first()
        est_coupe = (or_debut and or_debut.type_evenement == 'coupure')
        date_debut_coupure = debut_annee if est_coupe else None

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
            d = date_debut_coupure if date_debut_coupure else debut_annee
            periodes.append({'debut': d, 'fin': limit_date})

        decote = Decimal('0.00')
        for p in periodes:
            nb = int(round((p['fin'] - p['debut']).days / 30.4))
            decote += (tarif / 3) * nb

        net = max(Decimal('0.00'), montant_brut - decote)
        return montant_brut, decote, net

    # Récupérer les options de filtres
    regions, districts, communes, ouvrages = build_employee_geo_filter_options(
        ouvrages_filter_scope,
        employes_responsables,
    )

    from apps.billing.models import TypePointEau
    types_point_eau = TypePointEau.objects.filter(
        id__in=PointEau.objects.filter(
            tarifforfaitaire__isnull=False,
            ouvrage_id__in=ouvrages_forfaitaires_ids
        ).values_list('type_point_eau_id', flat=True).distinct()
    ).order_by('nom_type')

    # Filtrer les points d'eau
    points_eau = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        ouvrage_id__in=ouvrages_forfaitaires_ids
    ).select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune'
    )

    if region_filter:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune__district__region_id=region_filter)
    if district_filter:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune__district_id=district_filter)
    if commune_filter:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune_id=commune_filter)
    if ouvrage_filter:
        points_eau = points_eau.filter(ouvrage_id=ouvrage_filter)
    if type_point_eau_filter:
        points_eau = points_eau.filter(type_point_eau_id=type_point_eau_filter)

    derniers_evenements_coupure = {}
    for evt in CoupureEau.objects.filter(point_eau__in=points_eau).order_by('point_eau_id', '-date_evenement', '-created_at'):
        point_id = str(evt.point_eau_id)
        if point_id not in derniers_evenements_coupure:
            derniers_evenements_coupure[point_id] = evt

    # Statistiques globales
    nb_tout_paye = 0
    nb_partiellement_paye = 0
    nb_non_paye = 0
    nb_coupe = 0
    montant_prevu_total = Decimal('0.00')
    montant_paye_total = Decimal('0.00')
    montant_planifie_total = Decimal('0.00') # NEW
    decote_totale_globale = Decimal('0.00') # NEW

    import pytz
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    def get_paiement_date(paiement):
        date_value = None
        if paiement.date_facture:
            date_value = paiement.date_facture
        elif getattr(paiement, 'planning_id', None) and paiement.planning and paiement.planning.date:
            date_value = paiement.planning.date

        if not date_value:
            return None

        if isinstance(date_value, datetime):
            if date_value.tzinfo:
                date_madagascar = date_value.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_value)
            return date_madagascar.date()

        return date_value

    # Préparer les colonnes Kanban par statut
    kanban_columns = {
        'tout_paye': {'label': 'Tout payé', 'badge': 'success', 'icon': 'check-circle', 'cards': []},
        'partiellement_paye': {'label': 'Partiellement payé', 'badge': 'warning', 'icon': 'exclamation-circle', 'cards': []},
        'non_paye': {'label': 'Non payé', 'badge': 'ghost', 'icon': 'times-circle', 'cards': []},
        'coupe': {'label': 'Coupé', 'badge': 'error', 'icon': 'exclamation-triangle', 'cards': []},
    }

    # Liste pour compter les ouvrages distincts
    ouvrages_concernes = set()

    for pe in points_eau:
        # Stocker l'ouvrage pour le comptage
        if pe.ouvrage:
            ouvrages_concernes.add(pe.ouvrage.id)

        # Calcul YTD
        tarif = tarif_pour_annee(pe, annee)
        montant_prevu_brut, decote_montant, montant_prevu_annuel = calculate_details_financiers(pe, annee, limit_date)

        # Récupérer les paiements pour l'année filtrée
        paiements_annee = PaiementForfaitaire.objects.filter(point_eau=pe)

        # Filtrer par année et calculer
        qte_payee = 0
        qte_non_payee = 0
        montant_planifie_pe = Decimal('0.00')

        for paiement in paiements_annee:
            date_locale = get_paiement_date(paiement)
            if not date_locale:
                continue

            if date_locale.year == annee:
                # Calcul Planifié YTD
                if paiement.montant is not None and date_locale <= limit_date:
                    montant_planifie_pe += Decimal(str(paiement.montant))

                # Récupérer la quantité (Pour le statut, on regarde TOUT ce qui est prévu dans l'année, ou YTD ?)
                # Dans la vue List, le statut est basé sur Trimestres T1-T4 (année entière).
                # Ici on garde la logique "Année entière" pour le statut visuel (Tout Payé = toute l'année payée ?)
                # User: "ajouter les mÃªmes stats... et les montant tenant compte de la date d'aujourd'hui"
                # Le statut (vert/rouge) dépend de si on a payé ce qu'on DOIT payer.
                # Si on est en Janvier et qu'on a payé Janvier, est-ce "Tout Payé" ?
                # Dans `views_dashboard_forfaitaire.py` old Logic, c'était basé sur qte_totale.
                # Ici je ne change PAS la logique de "qte_totale" car elle détermine la colonne Kanban.
                # Je touche seulement aux montants globaux.
                
                quantite = int(paiement.quantite) if paiement.quantite else 1

                if paiement.numeroDiameX:
                    qte_payee += quantite
                else:
                    qte_non_payee += quantite

        qte_totale = qte_payee + qte_non_payee
        # Montant payé basé sur ce qui est réellement payé (pas de filtre date pour le 'déjÃ  payé' souvent ?)
        # On garde la logique simple: qte_payee * tarif. 
        # Note: qte_payee vient de la boucle qui filtre `year == annee`.
        montant_paye = Decimal(qte_payee) * tarif if tarif > 0 else Decimal('0.00')
        montant_non_paye = Decimal(qte_non_payee) * tarif if tarif > 0 else Decimal('0.00')

        # Déterminer le statut
        dernier_evenement_coupure = derniers_evenements_coupure.get(str(pe.id))
        est_coupe = bool(
            (dernier_evenement_coupure and dernier_evenement_coupure.type_evenement == 'coupure')
            or pe.datearretbranchement is not None
        )
        date_arret = (
            dernier_evenement_coupure.date_evenement
            if dernier_evenement_coupure and dernier_evenement_coupure.type_evenement == 'coupure'
            else pe.datearretbranchement
        )

        if est_coupe:
            statut = 'coupe'
            nb_coupe += 1
        elif qte_payee == 0:
            statut = 'non_paye'
            nb_non_paye += 1
        elif qte_non_payee == 0 and qte_payee > 0:
            statut = 'tout_paye'
            nb_tout_paye += 1
        else:
            statut = 'partiellement_paye'
            nb_partiellement_paye += 1

        montant_prevu_total += montant_prevu_annuel
        montant_paye_total += montant_paye
        montant_planifie_total += montant_planifie_pe
        decote_totale_globale += decote_montant

        # Commune
        commune_nom = pe.parcelle.village.fokontany.commune.nom_commune if (
            pe.parcelle and pe.parcelle.village and
            pe.parcelle.village.fokontany and
            pe.parcelle.village.fokontany.commune
        ) else 'Non assignée'

        # Ajouter la carte Ã  la bonne colonne
        card = {
            'id': pe.id,
            'nom': pe.code_point_eau or pe.nomabonne or f'Point eau {pe.id}',
            'nomabonne': pe.nomabonne,
            'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
            'type_point_eau': pe.type_point_eau.nom_type if pe.type_point_eau else 'N/A',
            'est_institutionnel': bool(pe.estbranchementinstitutionnel),
            'commune': commune_nom,
            'tarif_forfaitaire': tarif,
            'qte_totale': qte_totale,
            'qte_payee': qte_payee,
            'qte_non_payee': qte_non_payee,
            'montant_paye': montant_paye,
            'est_coupe': est_coupe,
            'date_arret': date_arret,
        }

        kanban_columns[statut]['cards'].append(card)

    # Trier les cartes par commune puis nom
    for col in kanban_columns.values():
        col['cards'].sort(key=lambda x: (x['commune'], x['nom']))

    # Convertir en milliers
    montant_prevu_k = round(float(montant_prevu_total) / 1000)
    montant_planifie_k = round(float(montant_planifie_total) / 1000)
    montant_paye_k = round(float(montant_paye_total) / 1000)
    decote_totale_k = round(float(decote_totale_globale) / 1000)

    # Taux de recouvrement
    taux_recouvrement = 0
    if montant_prevu_total > 0:
        taux_recouvrement = int(round((float(montant_paye_total) / float(montant_prevu_total)) * 100))
    
    # Nb Ouvrages
    nb_ouvrages = len(ouvrages_concernes)

    # Générer la liste des années disponibles (de 2020 Ã  année courante + 1)
    annees_disponibles = list(range(2020, datetime.now().year + 2))

    return render(request, 'core/dashboard_payments_flat_kanban.html', {
        'title': 'Kanban Paiements Forfaitaires',
        'kanban_columns': kanban_columns,
        'montant_prevu': montant_prevu_total,
        'montant_prevu_k': montant_prevu_k,
        'montant_planifie': montant_planifie_total, # NEW
        'montant_planifie_k': montant_planifie_k, # NEW
        'decote_totale': decote_totale_globale, # NEW
        'decote_totale_k': decote_totale_k, # NEW
        'montant_paye': montant_paye_total,
        'montant_paye_k': montant_paye_k,
        'taux_recouvrement': taux_recouvrement,
        'nb_tout_paye': nb_tout_paye,
        'nb_partiellement_paye': nb_partiellement_paye,
        'nb_non_paye': nb_non_paye,
        'nb_coupe': nb_coupe,
        'nb_ouvrages': nb_ouvrages, # NEW
        'employes_responsables': employes_responsables,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'types_point_eau': types_point_eau,
        'employe_filter': employe_filter,
        'region_filter': region_filter,
        'district_filter': district_filter,
        'commune_filter': commune_filter,
        'ouvrage_filter': ouvrage_filter,
        'type_point_eau_filter': type_point_eau_filter,
        'annee_filter': annee_filter,
        'annees_disponibles': annees_disponibles,
        'date_debut': date_debut,
        'date_fin': date_fin,
    })


def dashboard_payments_volume(request):
    """Dashboard des paiements au volume (compteurs)"""
    # Filtres
    commune_filter = request.GET.get('commune')
    ouvrage_filter = request.GET.get('ouvrage')

    # Récupérer les options de filtres (priorité aux ouvrages gérés par l'organisation)
    ouvrages_ids = None
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            ouvrages_ids = list(
                ModaliteGestion.objects.filter(
                    date_fin__isnull=True,
                    gestionnaire_id__in=gestionnaire_ids
                ).values_list('ouvrage_id', flat=True).distinct()
            )
        else:
            ouvrages_ids = []

    if ouvrages_ids:
        ouvrages = Ouvrage.objects.filter(id__in=ouvrages_ids).order_by('nom_ouvrage')
        communes = Commune.objects.filter(
            id__in=PointEau.objects.filter(
                ouvrage_id__in=ouvrages_ids
            ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()
        ).order_by('nom_commune')
    else:
        communes = Commune.objects.all().order_by('nom_commune')
        ouvrages = Ouvrage.objects.filter(pointeau__isnull=False).distinct().order_by('nom_ouvrage')

    # Query de base pour les relevés
    releves = Releve.objects.all()

    # Appliquer les filtres (Ã  adapter selon la structure)
    if commune_filter:
        # releves = releves.filter(point_eau__parcelle__village__commune_id=commune_filter)
        pass
    if ouvrage_filter:
        # releves = releves.filter(point_eau__ouvrage_id=ouvrage_filter)
        pass

    # Statistiques des relevés
    stats = {
        'total_releves': releves.count(),
        'releves_payes': releves.filter(statut='paye').count(),
        'releves_impayes': releves.filter(statut='impaye').count(),
        'montant_total': releves.aggregate(Sum('montant'))['montant__sum'] or 0,
    }

    # Evolution des paiements (par mois)
    evolution_paiements = []
    for i in range(6):  # 6 derniers mois
        month_start = timezone.now().replace(day=1) - timedelta(days=30 * i)
        month_releves = releves.filter(
            datereleve__year=month_start.year,
            datereleve__month=month_start.month
        )
        evolution_paiements.append({
            'mois': month_start.strftime('%Y-%m'),
            'payes': month_releves.filter(statut='paye').count(),
            'impayes': month_releves.filter(statut='impaye').count(),
        })

    evolution_paiements.reverse()

    return render(request, 'core/dashboard_payments_volume.html', {
        'title': 'Paiements au Volume',
        'stats': stats,
        'evolution_paiements': evolution_paiements,
        'communes': communes,
        'ouvrages': ouvrages,
        'commune_filter': commune_filter,
        'ouvrage_filter': ouvrage_filter,
    })


def dashboard_expenses(request):
    """Dashboard des dépenses"""
    # Filtres
    commune_filter = request.GET.get('commune')
    ouvrage_filter = request.GET.get('ouvrage')

    # Récupérer les options de filtres (priorité aux ouvrages gérés par l'organisation)
    ouvrages_ids = None
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            ouvrages_ids = list(
                ModaliteGestion.objects.filter(
                    date_fin__isnull=True,
                    gestionnaire_id__in=gestionnaire_ids
                ).values_list('ouvrage_id', flat=True).distinct()
            )
        else:
            ouvrages_ids = []

    if ouvrages_ids:
        ouvrages = Ouvrage.objects.filter(id__in=ouvrages_ids).order_by('nom_ouvrage')
        communes = Commune.objects.filter(
            id__in=PointEau.objects.filter(
                ouvrage_id__in=ouvrages_ids
            ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()
        ).order_by('nom_commune')
    else:
        communes = Commune.objects.all().order_by('nom_commune')
        ouvrages = Ouvrage.objects.filter(pointeau__isnull=False).distinct().order_by('nom_ouvrage')

    # Calculer les dépenses depuis les plannings (indemnités, etc.)
    plannings = Planning.objects.all()

    # Appliquer les filtres
    if commune_filter:
        # plannings = plannings.filter(ouvrage__commune_id=commune_filter)
        pass
    if ouvrage_filter:
        plannings = plannings.filter(ouvrage_id=ouvrage_filter)

    # Récupérer les dépenses réelles depuis la comptabilité (BaseDiameX)
    entries_qs = BaseDiameX.objects.select_related(
        'compte', 'journal', 'journal__base', 'compte__organisation'
    ).filter(montant_out__gt=0).exclude(compte_code__startswith='00')

    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            entries_qs = entries_qs.filter(
                Q(journal__base__organisation_id__in=gestionnaire_ids) |
                Q(compte__organisation_id__in=gestionnaire_ids)
            )
        else:
            employe = getattr(request.user, 'employe', None)
            entries_qs = entries_qs.filter(imported_by=employe) if employe else entries_qs.none()

    total_depenses = entries_qs.aggregate(total=Sum('montant_out'))['total'] or 0
    total_depenses_value = float(total_depenses or 0)
    total_plannings = plannings.count()
    moyenne_par_planning = (total_depenses / total_plannings) if total_plannings else 0

    today = timezone.localdate()
    depenses_mois_courant = entries_qs.filter(
        date_m__year=today.year,
        date_m__month=today.month
    ).aggregate(total=Sum('montant_out'))['total'] or 0
    depenses_mois_courant_value = float(depenses_mois_courant or 0)

    # Statistiques des dépenses
    stats = {
        'total_plannings': total_plannings,
        'total_depenses': total_depenses,
        'moyenne_par_planning': moyenne_par_planning,
        'depenses_mois_courant': depenses_mois_courant,
    }

    # Dépenses par catégorie
    categories_qs = entries_qs.values(
        'compte__nom_compte', 'compte_code'
    ).annotate(
        montant=Sum('montant_out')
    ).order_by('-montant')

    def _icon_for_category(label: str) -> str:
        label_lower = (label or '').lower()
        if 'indem' in label_lower:
            return 'fa-users'
        if 'transport' in label_lower or 'carbur' in label_lower:
            return 'fa-truck'
        if 'maint' in label_lower or 'repar' in label_lower:
            return 'fa-tools'
        if 'salaire' in label_lower or 'cnaps' in label_lower or 'irsa' in label_lower:
            return 'fa-file-invoice-dollar'
        return 'fa-coins'

    depenses_par_categorie = []
    for cat in categories_qs[:6]:
        categorie = cat['compte__nom_compte'] or cat['compte_code'] or 'Sans compte'
        montant = float(cat['montant'] or 0)
        pourcentage = round((montant / total_depenses_value) * 100) if total_depenses_value else 0
        depenses_par_categorie.append({
            'categorie': categorie,
            'montant': montant,
            'pourcentage': pourcentage,
            'icon': _icon_for_category(categorie),
        })

    # Dépenses par catégorie pour le mois courant (bloc "budgets")
    depenses_mois_par_categorie = []
    categories_mois_qs = entries_qs.filter(
        date_m__year=today.year,
        date_m__month=today.month
    ).values(
        'compte__nom_compte', 'compte_code'
    ).annotate(
        montant=Sum('montant_out')
    ).order_by('-montant')
    for cat in categories_mois_qs[:3]:
        categorie = cat['compte__nom_compte'] or cat['compte_code'] or 'Sans compte'
        montant = float(cat['montant'] or 0)
        pourcentage = round((montant / depenses_mois_courant_value) * 100) if depenses_mois_courant_value else 0
        depenses_mois_par_categorie.append({
            'categorie': categorie,
            'montant': montant,
            'pourcentage': pourcentage,
        })

    # Evolution mensuelle (6 derniers mois)
    month_names = ['Janv', 'Févr', 'Mars', 'Avr', 'Mai', 'Juin', 'Juil', 'Aout', 'Sept', 'Oct', 'Nov', 'Déc']
    monthly_labels = []
    monthly_values = []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        month_total = entries_qs.filter(date_m__year=y, date_m__month=m).aggregate(
            total=Sum('montant_out')
        )['total'] or 0
        monthly_labels.append(month_names[m - 1])
        monthly_values.append(float(month_total))

    # Dépenses récentes
    depenses_recentes = []
    for entry in entries_qs.order_by('-date_m', '-id')[:6]:
        depenses_recentes.append({
            'description': entry.description or entry.compte.nom_compte if entry.compte else 'Sans description',
            'compte': entry.compte.nom_compte if entry.compte else (entry.compte_code or '-'),
            'montant': entry.montant_out or 0,
            'date': entry.date_m or entry.date_rec,
            'fichier_source': entry.fichier_source,
        })

    return render(request, 'core/dashboard_expenses.html', {
        'title': 'Tableau de Bord Dépenses',
        'stats': stats,
        'depenses_par_categorie': depenses_par_categorie,
        'depenses_mois_par_categorie': depenses_mois_par_categorie,
        'depenses_recentes': depenses_recentes,
        'monthly_labels': monthly_labels,
        'monthly_values': monthly_values,
        'communes': communes,
        'ouvrages': ouvrages,
        'commune_filter': commune_filter,
        'ouvrage_filter': ouvrage_filter,
    })


def dashboard_infrastructure(request):
    """Dashboard de l'état des ouvrages"""
    # Filtres
    commune_filter = request.GET.get('commune')
    region_filter = request.GET.get('region')

    # Récupérer les options de filtres
    communes = Commune.objects.all().order_by('nom_commune')
    regions = Region.objects.all().order_by('nom_region')

    # Query des ouvrages
    ouvrages = Ouvrage.objects.filter(pointeau__isnull=False).distinct()

    # Appliquer les filtres
    if commune_filter:
        # ouvrages = ouvrages.filter(commune_id=commune_filter)
        pass
    if region_filter:
        # ouvrages = ouvrages.filter(commune__district__region_id=region_filter)
        pass

    # Statistiques des ouvrages
    stats = {
        'total_ouvrages': ouvrages.count(),
        'ouvrages_actifs': ouvrages.filter(is_active=True).count() if hasattr(Ouvrage, 'is_active') else ouvrages.count(),
        'maintenance_requise': 0,  # Ã€ calculer selon vos critères
        'nouveaux_ce_mois': ouvrages.filter(
            createdat__gte=timezone.now().replace(day=1)
        ).count() if hasattr(Ouvrage, 'createdat') else 0,
    }

    # Etat des ouvrages par type - Temporaire : désactivé Ã  cause du mismatch UUID/int
    ouvrages_par_type = []  # ouvrages.values('typeouvrage__nomtype').annotate(count=Count('id')).order_by('-count')[:5]

    # Dernières interventions - Limiter pour éviter les erreurs de relation
    dernieres_interventions = ouvrages.order_by('-updatedat')[:5] if hasattr(Ouvrage, 'updatedat') else []

    return render(request, 'core/dashboard_infrastructure.html', {
        'title': 'Etat des Ouvrages',
        'stats': stats,
        'ouvrages_par_type': ouvrages_par_type,
        'dernieres_interventions': dernieres_interventions,
        'communes': communes,
        'regions': regions,
        'commune_filter': commune_filter,
        'region_filter': region_filter,
    })


def dashboard_map(request):
    """Dashboard cartographique avec GeoDjango"""
    # Pour l'instant, une version basique
    # GeoDjango sera ajouté plus tard

    # Récupérer les données géographiques
    regions = Region.objects.all()
    communes = Commune.objects.all()
    ouvrages = Ouvrage.objects.filter(pointeau__isnull=False).distinct()

    # Préparer les données pour la carte (format GeoJSON)
    ouvrages_data = []
    for ouvrage in ouvrages:
        # Coordonnées fictives pour l'instant
        ouvrages_data.append({
            'id': str(ouvrage.id),
            'nom': ouvrage.nom_ouvrage,
            'type': 'Standard',  # Temporaire - relation typeouvrage Ã  corriger
            'statut': 'actif',  # Ã€ adapter selon votre logique
            'latitude': -18.8792 + (len(str(ouvrage.id)) * 0.1),  # Coordonnées fictives
            'longitude': 47.5079 + (len(ouvrage.nom_ouvrage) * 0.01),
        })

    return render(request, 'core/dashboard_map.html', {
        'title': 'Carte Interactive',
        'regions': regions,
        'communes': communes,
        'ouvrages_data': ouvrages_data,
    })


from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

@require_http_methods(["POST"])
def chatbot_query(request):
    """API pour répondre aux questions du chatbot avec données de la base - Version modernisée avec AIAssistant"""
    import json
    import asyncio

    try:
        data = json.loads(request.body)
        question = data.get('question', '')

        # Utiliser le nouveau système AIAssistant pour toutes les questions
        from chatbot.services.ai_assistant import AIAssistant

        ai_assistant = AIAssistant()

        # Exécuter de manière asynchrone
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ai_response = loop.run_until_complete(
                ai_assistant.process_message(question, None)
            )
        finally:
            loop.close()

        # Adapter la réponse au format attendu par l'ancienne API
        response = {
            'success': ai_response.get('success', True),
            'answer': ai_response.get('response', 'Désolé, je n\'ai pas pu traiter votre demande.'),
            'data': ai_response.get('metadata', {})
        }

        return JsonResponse(response)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'answer': f"Erreur lors du traitement de votre question : {str(e)}"
        })


@require_http_methods(["GET"])
def api_global_stats(request):
    """API pour récupérer les statistiques globales"""
    from django.db.models import Sum, Count, Q
    from apps.billing.models import PointEau
    from apps.organization.models import Ouvrage
    from apps.employees.models import Employe
    from apps.inventory.models import Stock
    from datetime import datetime, timedelta

    try:
        # Statistiques générales
        total_points_eau = PointEau.objects.count()
        total_ouvrages = Ouvrage.objects.count()
        total_employes = Employe.objects.filter(date_sortie__isnull=True).count()
        total_stock_value = Stock.objects.aggregate(total=Sum('valeur_stock'))['total'] or 0

        # Statistiques de la semaine dernière (pour les tendances)
        last_week = datetime.now() - timedelta(days=7)
        new_points_eau = PointEau.objects.filter(datebranchement__gte=last_week).count()

        # Points d'eau actifs vs inactifs
        active_points = PointEau.objects.filter(
            datebranchement__isnull=False,
            datearretbranchement__isnull=True
        ).count()
        inactive_points = total_points_eau - active_points

        response = {
            'success': True,
            'stats': {
                'total_points_eau': total_points_eau,
                'total_ouvrages': total_ouvrages,
                'total_employes': total_employes,
                'total_stock_value': float(total_stock_value),
                'active_points': active_points,
                'inactive_points': inactive_points,
                'new_points_eau_week': new_points_eau
            },
            'trends': {
                'points_eau': '+' + str(new_points_eau) if new_points_eau > 0 else '0',
                'ouvrages': '+0',  # TODO: Calculer la vraie tendance
                'employes': '+0'   # TODO: Calculer la vraie tendance
            }
        }

        return JsonResponse(response)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_week_plannings(request):
    """API pour récupérer les plannings de la semaine"""
    from apps.planning.models import Planning
    from datetime import datetime, timedelta

    try:
        # Définir la semaine courante (lundi Ã  dimanche)
        today = datetime.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # Récupérer les plannings de la semaine
        plannings = Planning.objects.filter(
            date_planning__gte=start_of_week,
            date_planning__lte=end_of_week
        ).select_related('ouvrage', 'ouvrage__commune').order_by('date_planning')

        # Formater les résultats
        plannings_data = []
        for planning in plannings:
            plannings_data.append({
                'id': str(planning.id),
                'date': planning.date_planning.strftime('%Y-%m-%d'),
                'date_display': planning.date_planning.strftime('%d/%m/%Y'),
                'day_name': planning.date_planning.strftime('%A'),
                'ouvrage': planning.ouvrage.nom if planning.ouvrage else 'Non défini',
                'commune': planning.ouvrage.commune.nom_commune if planning.ouvrage and planning.ouvrage.commune else 'N/A',
                'status': 'planifié'  # TODO: Ajouter un champ status au modèle
            })

        response = {
            'success': True,
            'week_range': {
                'start': start_of_week.strftime('%d/%m/%Y'),
                'end': end_of_week.strftime('%d/%m/%Y')
            },
            'plannings': plannings_data,
            'total': len(plannings_data)
        }

        return JsonResponse(response)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_unpaid_invoices(request):
    """API pour récupérer les factures impayées"""
    # TODO: Implémenter quand le modèle Facture sera créé
    # Pour l'instant, retourner des données simulées basées sur les points d'eau
    from apps.billing.models import PointEau

    try:
        # Simuler des factures impayées basées sur les points d'eau actifs
        points_eau = PointEau.objects.filter(
            datebranchement__isnull=False,
            datearretbranchement__isnull=True
        ).select_related('ouvrage', 'ouvrage__commune')[:20]

        invoices_data = []
        for idx, point in enumerate(points_eau, 1):
            # Simuler un montant impayé
            montant = float(point.tarifforfaitaire) if point.tarifforfaitaire else 5000.0

            invoices_data.append({
                'numero': f'F-2025-{idx:04d}',
                'client': point.nomabonne,
                'commune': point.ouvrage.commune.nom_commune if point.ouvrage and point.ouvrage.commune else 'N/A',
                'montant': montant,
                'date_facture': '01/10/2025',  # TODO: Calculer depuis la date de branchement
                'jours_retard': 15 + (idx * 2)  # Simuler des retards variés
            })

        response = {
            'success': True,
            'invoices': invoices_data,
            'total': len(invoices_data),
            'total_amount': sum(inv['montant'] for inv in invoices_data),
            'note': 'Données simulées - Ã€ remplacer par de vraies factures'
        }

        return JsonResponse(response)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)




@login_required
def search_global(request):
    """Page de recherche globale dans toutes les tables"""
    return render(request, 'core/search.html', {
        'title': 'Recherche globale'
    })


@login_required
@require_http_methods(["GET"])
def search_api(request):
    """API de recherche globale"""
    query = request.GET.get('q', '').strip()

    if not query or len(query) < 2:
        return JsonResponse({
            'results': [],
            'total': 0,
            'message': 'Veuillez saisir au moins 2 caractères'
        })

    results = []

    # Recherche dans les plannings
    try:
        plannings = Planning.objects.select_related(
            'employe', 'ouvrage', 'type_activite', 'fiche_poste'
        ).filter(
            Q(remarque__icontains=query) |
            Q(employe__nom__icontains=query) |
            Q(employe__prenom__icontains=query) |
            Q(employe__surnom__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query) |
            Q(type_activite__nomtype__icontains=query) |
            Q(fiche_poste__tache__icontains=query)
        )[:20]

        for planning in plannings:
            results.append({
                'type': 'planning',
                'type_display': 'Planning',
                'id': str(planning.id),
                'title': f"Planning {planning.date.strftime('%d/%m/%Y') if planning.date else 'Sans date'}",
                'subtitle': f"{planning.employe.nom_affichage if planning.employe else 'Sans employé'} - {planning.ouvrage.nom_ouvrage if planning.ouvrage else 'Sans ouvrage'}",
                'badge': 'Validé' if planning.estvalide else 'En attente',
                'badge_class': 'success' if planning.estvalide else 'warning',
                'icon': 'fa-calendar-alt',
                'details': {
                    'Date': planning.date.strftime('%d/%m/%Y') if planning.date else '-',
                    'Employé': planning.employe.nom_affichage if planning.employe else '-',
                    'Ouvrage': planning.ouvrage.nom_ouvrage if planning.ouvrage else '-',
                    'Type activité': planning.type_activite.nomtype if planning.type_activite else '-',
                    'Activité': planning.activite_display,
                    'Statut': 'Validé' if planning.estvalide else 'En attente',
                    'Remarque': planning.remarque or '-'
                }
            })
    except Exception as e:
        print(f"Erreur recherche plannings: {e}")

    # Recherche dans les employés
    try:
        employes = Employe.objects.select_related('poste').filter(
            Q(nom__icontains=query) |
            Q(prenom__icontains=query) |
            Q(surnom__icontains=query) |
            Q(mail__icontains=query) |
            Q(telephone__icontains=query)
        )[:20]

        for employe in employes:
            # Employe n'a pas de champ is_active propre : un employe est considere actif tant
            # qu'il n'a pas de date de debauchage (meme convention que search_detail et
            # views_reunions.participant_search_json).
            est_actif = employe.date_debauchage is None
            results.append({
                'type': 'employe',
                'type_display': 'Employé',
                'id': str(employe.id),
                'title': employe.nom_affichage,
                'subtitle': employe.poste.nom_poste if employe.poste_id and employe.poste else 'Employé',
                'contact': employe.telephone or employe.mail or '',
                'badge': 'Actif' if est_actif else 'Inactif',
                'badge_class': 'success' if est_actif else 'error',
                'icon': 'fa-user',
                'details': {
                    'Nom complet': employe.nom_affichage,
                    'Surnom': employe.surnom or '-',
                    'Email': employe.mail or '-',
                    'Téléphone': employe.telephone or '-',
                    'Statut': 'Actif' if est_actif else 'Inactif',
                }
            })
    except Exception as e:
        print(f"Erreur recherche employés: {e}")

    # Recherche dans les representantes des usagers
    try:
        from apps.usagers.models import RepresentantUsager

        representants = RepresentantUsager.objects.select_related(
            'village__fokontany__commune'
        ).filter(
            Q(nom__icontains=query) |
            Q(contact__icontains=query) |
            Q(village__nom_village__icontains=query)
        )[:20]

        for rep in representants:
            village_nom = rep.village.nom_village if rep.village else 'Village inconnu'
            results.append({
                'type': 'representant',
                'type_display': 'Représentante des usagers',
                'id': str(rep.id),
                'title': rep.nom or 'Sans nom',
                'subtitle': village_nom,
                'contact': rep.contact or '',
                'badge': 'Actif' if rep.est_actif else 'Inactif',
                'badge_class': 'success' if rep.est_actif else 'error',
                'icon': 'fa-user-tie',
                'details': {
                    'Nom': rep.nom or '-',
                    'Village': village_nom,
                    'Contact': rep.contact or '-',
                    'Statut': 'Actif' if rep.est_actif else 'Inactif',
                }
            })
    except Exception as e:
        print(f"Erreur recherche représentantes: {e}")

    # Recherche dans les autorites (maires, chefs fokontany, ...)
    try:
        from apps.usagers.models import Autorite

        autorites = Autorite.objects.select_related(
            'fokontany', 'commune', 'district', 'region'
        ).filter(
            Q(nom__icontains=query) |
            Q(fonction__icontains=query) |
            Q(contact__icontains=query) |
            Q(email__icontains=query)
        )[:20]

        for autorite in autorites:
            zone = autorite.zone_affichee or 'Zone non precisee'
            type_display = autorite.get_type_autorite_display() or 'Autorité'
            results.append({
                'type': 'autorite',
                'type_display': 'Autorité',
                'id': str(autorite.id),
                'title': autorite.nom,
                'subtitle': f"{type_display} - {zone}",
                'contact': autorite.contact or autorite.email or '',
                'badge': 'Actif' if autorite.actif else 'Inactif',
                'badge_class': 'success' if autorite.actif else 'error',
                'icon': 'fa-landmark',
                'details': {
                    'Nom': autorite.nom,
                    'Type': type_display,
                    'Fonction': autorite.fonction or '-',
                    'Zone': zone,
                    'Contact': autorite.contact or '-',
                    'Email': autorite.email or '-',
                    'Statut': 'Actif' if autorite.actif else 'Inactif',
                }
            })
    except Exception as e:
        print(f"Erreur recherche autorités: {e}")

    # Recherche dans les tiers (ONG, bailleurs, institutions, ...)
    try:
        from apps.usagers.models import TiersParticipant

        tiers_qs = TiersParticipant.objects.filter(
            Q(nom__icontains=query) |
            Q(organisme__icontains=query) |
            Q(fonction__icontains=query) |
            Q(contact__icontains=query) |
            Q(email__icontains=query)
        )[:20]

        for tiers in tiers_qs:
            type_display = tiers.get_type_tiers_display() or 'Tiers'
            results.append({
                'type': 'tiers',
                'type_display': 'Tiers',
                'id': str(tiers.id),
                'title': tiers.nom,
                'subtitle': f"{type_display}" + (f" - {tiers.organisme}" if tiers.organisme else ''),
                'contact': tiers.contact or tiers.email or '',
                'badge': 'Actif' if tiers.actif else 'Inactif',
                'badge_class': 'success' if tiers.actif else 'error',
                'icon': 'fa-handshake',
                'details': {
                    'Nom': tiers.nom,
                    'Type': type_display,
                    'Organisme': tiers.organisme or '-',
                    'Fonction': tiers.fonction or '-',
                    'Contact': tiers.contact or '-',
                    'Email': tiers.email or '-',
                    'Statut': 'Actif' if tiers.actif else 'Inactif',
                }
            })
    except Exception as e:
        print(f"Erreur recherche tiers: {e}")

    # Recherche dans les fournisseurs
    try:
        from apps.billing.models import Fournisseur

        fournisseurs = Fournisseur.objects.filter(
            Q(nom_fournisseur__icontains=query) |
            Q(telephone__icontains=query) |
            Q(email__icontains=query) |
            Q(numero_nif__icontains=query) |
            Q(code_tiers__icontains=query)
        )[:20]

        for fournisseur in fournisseurs:
            type_display = fournisseur.get_type_fournisseur_display() if fournisseur.type_fournisseur else 'Fournisseur'
            results.append({
                'type': 'fournisseur',
                'type_display': 'Fournisseur',
                'id': str(fournisseur.id),
                'title': fournisseur.nom_fournisseur,
                'subtitle': type_display,
                'contact': fournisseur.telephone or fournisseur.email or '',
                'badge': 'Actif' if fournisseur.actif else 'Inactif',
                'badge_class': 'success' if fournisseur.actif else 'error',
                'icon': 'fa-truck',
                'details': {
                    'Nom': fournisseur.nom_fournisseur,
                    'Type': type_display,
                    'Téléphone': fournisseur.telephone or '-',
                    'Email': fournisseur.email or '-',
                    'Code tiers': fournisseur.code_tiers or '-',
                    'Statut': 'Actif' if fournisseur.actif else 'Inactif',
                }
            })
    except Exception as e:
        print(f"Erreur recherche fournisseurs: {e}")

    # Recherche dans les villages
    try:
        villages = Village.objects.select_related(
            'fokontany__commune__district__region'
        ).filter(
            Q(nom_village__icontains=query) |
            Q(fokontany__nom_fokontany__icontains=query) |
            Q(fokontany__commune__nom_commune__icontains=query)
        )[:20]

        for village in villages:
            results.append({
                'type': 'village',
                'type_display': 'Village',
                'id': str(village.id),
                'title': village.nom_village,
                'subtitle': f"{village.fokontany.nom_fokontany if village.fokontany else ''} - {village.fokontany.commune.nom_commune if village.fokontany and village.fokontany.commune else ''}",
                'badge': 'Village',
                'badge_class': 'info',
                'icon': 'fa-home',
                'details': {
                    'Village': village.nom_village,
                    'Fokontany': village.fokontany.nom_fokontany if village.fokontany else '-',
                    'Commune': village.fokontany.commune.nom_commune if village.fokontany and village.fokontany.commune else '-',
                    'District': village.fokontany.commune.district.nom_district if village.fokontany and village.fokontany.commune and village.fokontany.commune.district else '-',
                    'Région': village.fokontany.commune.district.region.nom_region if village.fokontany and village.fokontany.commune and village.fokontany.commune.district and village.fokontany.commune.district.region else '-',
                }
            })
    except Exception as e:
        print(f"Erreur recherche villages: {e}")

    # Recherche dans les communes
    try:
        communes = Commune.objects.select_related('district__region').filter(
            Q(nom_commune__icontains=query) |
            Q(district__nom_district__icontains=query)
        )[:20]

        for commune in communes:
            results.append({
                'type': 'commune',
                'type_display': 'Commune',
                'id': str(commune.id),
                'title': commune.nom_commune,
                'subtitle': f"{commune.district.nom_district if commune.district else ''} - {commune.district.region.nom_region if commune.district and commune.district.region else ''}",
                'badge': 'Commune',
                'badge_class': 'secondary',
                'icon': 'fa-map-marker-alt',
                'details': {
                    'Commune': commune.nom_commune,
                    'District': commune.district.nom_district if commune.district else '-',
                    'Région': commune.district.region.nom_region if commune.district and commune.district.region else '-',
                }
            })
    except Exception as e:
        print(f"Erreur recherche communes: {e}")

    # Recherche dans les ouvrages
    try:
        ouvrages = Ouvrage.objects.filter(
            Q(nom_ouvrage__icontains=query) |
            Q(observation__icontains=query)
        )[:20]

        for ouvrage in ouvrages:
            # Afficher l'année de réalisation si disponible, sinon observation
            subtitle = f"Année: {ouvrage.annee_realisation}" if ouvrage.annee_realisation else (ouvrage.observation or 'Pas d\'information')

            # Chercher une photo depuis les points d'eau ou équipements liés
            photo_url = None
            try:
                # Essayer les points d'eau d'abord
                points_eau_with_photos = ouvrage.pointeau_set.filter(photos__isnull=False).first()
                if points_eau_with_photos and points_eau_with_photos.photos:
                    photo_url = points_eau_with_photos.photos.get_download_url()
                else:
                    # Sinon, essayer les équipements
                    equipements_with_photos = ouvrage.equipementconstitutif_set.filter(photos__isnull=False).first()
                    if equipements_with_photos and equipements_with_photos.photos:
                        photo_url = equipements_with_photos.photos.get_download_url()
            except Exception:
                pass  # Ignorer les erreurs de récupération de photo

            results.append({
                'type': 'ouvrage',
                'type_display': 'Ouvrage',
                'id': str(ouvrage.id),
                'title': ouvrage.nom_ouvrage,
                'subtitle': subtitle,
                'badge': 'Ouvrage',
                'badge_class': 'primary',
                'icon': 'fa-building',
                'photo_url': photo_url,
                'details': {
                    'Nom': ouvrage.nom_ouvrage,
                    'Année de réalisation': str(ouvrage.annee_realisation) if ouvrage.annee_realisation else '-',
                    'Observation': ouvrage.observation or '-',
                }
            })
    except Exception as e:
        print(f"Erreur recherche ouvrages: {e}")

    # Recherche dans les points d\'eau
    try:
        points_eau = PointEau.objects.select_related('type_point_eau', 'ouvrage').filter(
            Q(code_point_eau__icontains=query) |
            Q(type_point_eau__nom_type__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query) |
            Q(nomabonne__icontains=query) |
            Q(idxls__iexact=query)
        )[:20]

        for point in points_eau:
            # URL de la photo si elle existe
            photo_url = None
            try:
                if point.photos:
                    photo_url = point.photos.get_download_url()
            except Exception:
                pass  # Ignorer les erreurs de récupération de photo

            results.append({
                'type': 'point_eau',
                'type_display': 'Abonné (point d\'eau)',
                'id': str(point.id),
                'title': point.nomabonne or 'Sans nom',
                'subtitle': (
                    f"IDXLS {point.idxls or '-'} · "
                    f"{point.type_point_eau.nom_type if point.type_point_eau else 'Type inconnu'} - "
                    f"{point.ouvrage.nom_ouvrage if point.ouvrage else 'Ouvrage inconnu'}"
                ),
                # Les deux numeros s'il y en a deux (numeroteleph + contactabonne differents)
                'contact': ' · '.join(dict.fromkeys(
                    n for n in (point.numeroteleph, point.contactabonne) if n
                )),
                'badge': point.type_point_eau.nom_type if point.type_point_eau else 'Type inconnu',
                'badge_class': 'info',
                'icon': 'fa-tint',
                'photo_url': photo_url,
                'details': {
                    'Abonné': point.nomabonne or '-',
                    'IDXLS': point.idxls or '-',
                    'Téléphone': point.numeroteleph or point.contactabonne or '-',
                    'Type': point.type_point_eau.nom_type if point.type_point_eau else '-',
                    'Ouvrage': point.ouvrage.nom_ouvrage if point.ouvrage else '-',
                    'Tarif forfaitaire': f"{point.tarifforfaitaire} Ar" if point.tarifforfaitaire else '-',
                }
            })
    except Exception as e:
        print(f"Erreur recherche points d\'eau: {e}")

    # Recherche dans les équipements
    try:
        equipements = EquipementConstitutif.objects.select_related('ouvrage').filter(
            Q(nom__icontains=query) |
            Q(code_equipement__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query)
        )[:20]

        for equipement in equipements:
            # URL de la photo si elle existe
            photo_url = None
            try:
                if equipement.photos:
                    photo_url = equipement.photos.get_download_url()
            except Exception:
                pass  # Ignorer les erreurs de récupération de photo

            results.append({
                'type': 'equipement',
                'type_display': 'Equipement',
                'id': str(equipement.id),
                'title': equipement.nom,
                'subtitle': f"{equipement.ouvrage.nom_ouvrage if equipement.ouvrage else 'Ouvrage inconnu'}",
                'badge': equipement.code_equipement or 'Equipement',
                'badge_class': 'accent',
                'icon': 'fa-cogs',
                'photo_url': photo_url,
                'details': {
                    'Nom': equipement.nom,
                    'Code': equipement.code_equipement or '-',
                    'Ouvrage': equipement.ouvrage.nom_ouvrage if equipement.ouvrage else '-',
                }
            })
    except Exception as e:
        print(f"Erreur recherche équipements: {e}")

    # Recherche dans les désignations
    try:
        from apps.planning.models import Designation
        designations = Designation.objects.select_related('type_designation', 'photo_specimen').filter(
            Q(nom__icontains=query) |
            Q(description__icontains=query) |
            Q(code_materiel__icontains=query) |
            Q(type_designation__nom__icontains=query)
        )[:20]

        for designation in designations:
            # URL de la photo si elle existe
            photo_url = designation.photo_specimen.get_download_url() if designation.photo_specimen else None

            results.append({
                'type': 'designation',
                'type_display': 'Désignation',
                'id': str(designation.id),
                'title': designation.nom,
                'subtitle': f"{designation.type_designation.nom if designation.type_designation else 'Type inconnu'} - {designation.prix_unitaire or 0} Ar/{designation.unite or 'u'}",
                'badge': 'Actif' if designation.actif else 'Inactif',
                'badge_class': 'success' if designation.actif else 'ghost',
                'icon': 'fa-tag',
                'photo_url': photo_url,
                'details': {
                    'Nom': designation.nom,
                    'Description': designation.description or '-',
                    'Type': designation.type_designation.nom if designation.type_designation else '-',
                    'Prix unitaire': f"{designation.prix_unitaire} Ar" if designation.prix_unitaire else '-',
                    'Unité': designation.unite or '-',
                    'Code matériel': designation.code_materiel or '-',
                    'Statut': 'Actif' if designation.actif else 'Inactif',
                    'Photo': 'Oui' if photo_url else 'Non',
                }
            })
    except Exception as e:
        print(f"Erreur recherche désignations: {e}")

    # Recherche dans les modalités de gestion
    try:
        modalites = ModaliteGestion.objects.filter(
            Q(type_gestion__icontains=query)
        )[:20]

        for modalite in modalites:
            results.append({
                'type': 'modalite',
                'type_display': 'Modalité de gestion',
                'id': str(modalite.id),
                'title': modalite.type_gestion,
                'subtitle': 'Modalité de gestion',
                'badge': modalite.type_gestion,
                'badge_class': 'secondary',
                'icon': 'fa-clipboard-list',
                'details': {
                    'Type': modalite.type_gestion,
                }
            })
    except Exception as e:
        print(f"Erreur recherche modalités: {e}")

    # Recherche dans les cartes sociales
    try:
        cartes = CarteSociale.objects.filter(
            Q(nom_beneficiaire__icontains=query)
        )[:20]

        for carte in cartes:
            results.append({
                'type': 'carte_sociale',
                'type_display': 'Carte sociale',
                'id': str(carte.id),
                'title': carte.nom_beneficiaire or 'Carte sans nom',
                'subtitle': 'Carte sociale',
                'badge': 'Carte sociale',
                'badge_class': 'warning',
                'icon': 'fa-id-card',
                'details': {
                    'Nom bénéficiaire': carte.nom_beneficiaire or '-',
                }
            })
    except Exception as e:
        print(f"Erreur recherche cartes sociales: {e}")

    return JsonResponse({
        'results': results,
        'total': len(results),
        'query': query
    })


def _get_commune_authorities(commune):
    """
    Classe les autorites pertinentes pour une commune selon leur rattachement
    geographique le plus precis. Une fiche contenant toute la chaine ne doit
    jamais remonter comme autorite regionale ou de district si elle cible une
    commune ou un fokontany.
    """
    from apps.usagers.models_reunions import Autorite

    autorites = Autorite.objects.select_related(
        'region', 'district', 'commune', 'fokontany'
    )

    autorites_commune = list(
        autorites.filter(
            commune_id=commune.id,
            fokontany__isnull=True,
        ).order_by('nom')
    )
    autorites_fokontany = list(
        autorites.filter(
            fokontany__commune_id=commune.id,
        ).order_by('fokontany__nom_fokontany', 'nom')
    )

    autorites_district = []
    autorites_region = []
    if commune.district_id:
        autorites_district = list(
            autorites.filter(
                district_id=commune.district_id,
                commune__isnull=True,
                fokontany__isnull=True,
            ).order_by('nom')
        )
        if commune.district and commune.district.region_id:
            autorites_region = list(
                autorites.filter(
                    region_id=commune.district.region_id,
                    district__isnull=True,
                    commune__isnull=True,
                    fokontany__isnull=True,
                ).order_by('nom')
            )

    return {
        'commune': autorites_commune,
        'fokontany': autorites_fokontany,
        'district': autorites_district,
        'region': autorites_region,
    }


@login_required
def search_detail(request, entity_type, entity_id):
    """Page de détails d'une entité depuis la recherche globale"""
    from django.urls import NoReverseMatch, reverse

    try:
        reverse('notes:workspace')
        notes_namespace_available = True
    except NoReverseMatch:
        notes_namespace_available = False

    context = {
        'title': 'Détails',
        'entity_type': entity_type,
        'entity_id': entity_id,
        'entity': None,
        'related_data': {},
        'notes_namespace_available': notes_namespace_available,
    }

    try:
        if entity_type == 'village':
            from django.db.models import Sum
            from apps.geography.models import Parcelle
            # Planning est déjÃ  importé au niveau du module

            village = Village.objects.select_related(
                'fokontany__commune__district__region'
            ).prefetch_related('parcelles').get(id=entity_id)

            # Points d'eau du village via les parcelles
            points_eau = PointEau.objects.filter(
                parcelle__village=village
            ).select_related('type_point_eau', 'ouvrage')

            # Grouper les points d'eau par type avec comptage
            from apps.billing.models import TypePointEau
            points_par_type_stats = {}
            for type_point in TypePointEau.objects.all():
                count = points_eau.filter(type_point_eau=type_point).count()
                if count > 0:
                    points_par_type_stats[type_point.nom_type] = {
                        'count': count,
                        'type_id': type_point.id
                    }

            # Ouvrages liés au village via les points d'eau
            ouvrages = Ouvrage.objects.filter(
                pointeau__parcelle__village=village
            ).distinct()

            # Statistiques des ouvrages par type
            from apps.organization.models import TypeOuvrage
            ouvrages_par_type = {}
            for type_ouvrage in TypeOuvrage.objects.all():
                count = ouvrages.filter(type_ouvrage=type_ouvrage).count()
                if count > 0:
                    ouvrages_par_type[type_ouvrage.nom_type_ouvrage] = {
                        'count': count,
                        'type_id': type_ouvrage.id
                    }

            # Equipements constitutifs (via ouvrages du village)
            equipements = EquipementConstitutif.objects.filter(ouvrage__in=ouvrages)

            # Carte du village : village selectionne, villages voisins de la
            # meme commune, points d'eau et equipements relies au village.
            village_map_markers = []
            if village.latitude is not None and village.longitude is not None:
                village_map_markers.append({
                    'id': str(village.id),
                    'latitude': float(village.latitude),
                    'longitude': float(village.longitude),
                    'label': village.nom_village or 'Village sans nom',
                    'detail': village.fokontany.nom_fokontany if village.fokontany else '',
                    'kind': 'selected_village',
                    'url': reverse('core:search_detail', args=['village', str(village.id)]),
                })

            if village.fokontany and village.fokontany.commune_id:
                villages_voisins = Village.objects.filter(
                    fokontany__commune_id=village.fokontany.commune_id
                ).exclude(pk=village.pk)
            else:
                villages_voisins = Village.objects.none()

            for voisin in villages_voisins.values(
                'id', 'nom_village', 'latitude', 'longitude',
                'fokontany__nom_fokontany',
            ):
                if voisin['latitude'] is None or voisin['longitude'] is None:
                    continue
                village_map_markers.append({
                    'id': str(voisin['id']),
                    'latitude': float(voisin['latitude']),
                    'longitude': float(voisin['longitude']),
                    'label': voisin['nom_village'] or 'Village sans nom',
                    'detail': voisin['fokontany__nom_fokontany'] or '',
                    'kind': 'neighbor_village',
                    'url': reverse('core:search_detail', args=['village', str(voisin['id'])]),
                })

            for point_map in points_eau.values(
                'id', 'nomabonne', 'code_point_eau', 'latitude', 'longitude',
                'type_point_eau__nom_type',
            ):
                if point_map['latitude'] is None or point_map['longitude'] is None:
                    continue
                village_map_markers.append({
                    'id': str(point_map['id']),
                    'latitude': float(point_map['latitude']),
                    'longitude': float(point_map['longitude']),
                    'label': point_map['nomabonne'] or point_map['code_point_eau'] or "Point d'eau",
                    'detail': point_map['type_point_eau__nom_type'] or point_map['code_point_eau'] or "Point d'eau",
                    'kind': 'point_eau',
                    'url': reverse('core:search_detail', args=['point_eau', str(point_map['id'])]),
                })

            for equipement_map in equipements.values(
                'id', 'nom', 'latitude', 'longitude', 'type_equipement__nom_type',
            ):
                if equipement_map['latitude'] is None or equipement_map['longitude'] is None:
                    continue
                village_map_markers.append({
                    'id': str(equipement_map['id']),
                    'latitude': float(equipement_map['latitude']),
                    'longitude': float(equipement_map['longitude']),
                    'label': equipement_map['nom'] or 'Equipement sans nom',
                    'detail': equipement_map['type_equipement__nom_type'] or 'Equipement',
                    'kind': 'equipement',
                    'url': reverse('core:search_detail', args=['equipement', str(equipement_map['id'])]),
                })

            village_map_counts = {
                'selected_village': sum(
                    marker['kind'] == 'selected_village' for marker in village_map_markers
                ),
                'neighbor_villages': sum(
                    marker['kind'] == 'neighbor_village' for marker in village_map_markers
                ),
                'points_eau': sum(
                    marker['kind'] == 'point_eau' for marker in village_map_markers
                ),
                'equipements': sum(
                    marker['kind'] == 'equipement' for marker in village_map_markers
                ),
            }
            village_map_data = {
                'markers': village_map_markers,
                'counts': village_map_counts,
            }
            # Contours de la commune et du fokontany du village (importés des shapefiles), s'ils existent.
            try:
                from apps.geography.services.contours_communes import contours_village
                village_map_data['contours'] = {'type': 'FeatureCollection', 'features': contours_village(village)}
            except Exception:
                village_map_data['contours'] = {'type': 'FeatureCollection', 'features': []}

            # Modalités de gestion actives (via ouvrages)
            modalites_actives = ModaliteGestion.objects.filter(
                ouvrage__in=ouvrages,
                statut='actif'
            ).select_related('gestionnaire')

            # Répartition par organisation (gestionnaire)
            repartition_organisations = {}
            for modalite in modalites_actives:
                if modalite.gestionnaire:
                    org_nom = modalite.gestionnaire.nom_organisation
                    if org_nom not in repartition_organisations:
                        repartition_organisations[org_nom] = {
                            'ouvrages': set(),
                            'points_eau': 0,
                            'habitants_desservis': 0
                        }
                    repartition_organisations[org_nom]['ouvrages'].add(modalite.ouvrage.id)

            # Compter points d'eau et habitants par organisation
            for org_nom in repartition_organisations:
                org_ouvrages = [o_id for o_id in repartition_organisations[org_nom]['ouvrages']]
                org_points = PointEau.objects.filter(
                    ouvrage__id__in=org_ouvrages,
                    parcelle__village=village
                )
                repartition_organisations[org_nom]['points_eau'] = org_points.count()

                # Habitants desservis (parcelles liées Ã  ces points d'eau)
                habitants_desservis = Parcelle.objects.filter(
                    pointeau__in=org_points,
                    village=village
                ).aggregate(total=Sum('nombre_habitants'))['total'] or 0
                repartition_organisations[org_nom]['habitants_desservis'] = habitants_desservis
                repartition_organisations[org_nom]['ouvrages'] = len(repartition_organisations[org_nom]['ouvrages'])

            # Employés qui ont des positions GPS dans ce village
            employes_count = Employe.objects.filter(
                positions_gps__village_proche=village
            ).distinct().count()

            # Plannings liés au village (via ouvrage et points d'eau du village)
            plannings_count = Planning.objects.filter(
                ouvrage__in=ouvrages
            ).count()

            # Calculer la population totale via les parcelles
            population_data = village.parcelles.aggregate(
                total_habitants=Sum('nombre_habitants'),
                total_menages=Sum('nombre_menages')
            )
            population_totale = population_data['total_habitants'] or 0
            menages_totaux = population_data['total_menages'] or 0

            # Habitants desservis (parcelles avec point d'eau)
            habitants_desservis = Parcelle.objects.filter(
                village=village,
                pointeau__isnull=False
            ).aggregate(total=Sum('nombre_habitants'))['total'] or 0

            context['entity'] = {
                'type_display': 'Village',
                'nom': village.nom_village,
                'fokontany': village.fokontany.nom_fokontany if village.fokontany else '-',
                'commune': village.fokontany.commune.nom_commune if village.fokontany and village.fokontany.commune else '-',
                'district': village.fokontany.commune.district.nom_district if village.fokontany and village.fokontany.commune and village.fokontany.commune.district else '-',
                'region': village.fokontany.commune.district.region.nom_region if village.fokontany and village.fokontany.commune and village.fokontany.commune.district and village.fokontany.commune.district.region else '-',
                'population': f'{population_totale:,}'.replace(',', ' ') + ' habitants' if population_totale > 0 else '-',
                'menages': f'{menages_totaux:,}'.replace(',', ' ') + ' ménages' if menages_totaux > 0 else '-',
                'latitude': village.latitude or '-',
                'longitude': village.longitude or '-',
            }

            context['related_data'] = {
                'parcelles_count': village.parcelles.count(),
                'employes_count': employes_count,
                'points_eau_count': points_eau.count(),
                'points_par_type_stats': points_par_type_stats,
                'ouvrages': ouvrages,
                'ouvrages_total': ouvrages.count(),
                'ouvrages_par_type': ouvrages_par_type,
                'equipements_total': equipements.count(),
                'village_map_data': village_map_data,
                'modalites_actives': modalites_actives,
                'repartition_organisations': repartition_organisations,
                'plannings_count': plannings_count,
                'population_totale': population_totale,
                'menages_totaux': menages_totaux,
                'habitants_desservis': habitants_desservis,
            }

        elif entity_type == 'ouvrage':
            from django.core.paginator import Paginator
            from django.http import HttpResponseForbidden
            from datetime import datetime

            ouvrage = Ouvrage.objects.select_related(
                'type_ouvrage'
            ).prefetch_related(
                'equipements_constitutifs', 'compteurs_tete', 'dossiers_techniques'
            ).get(id=entity_id)

            # Vérifier si l'utilisateur est un client et si l'ouvrage lui appartient
            if hasattr(request.user, 'client') and request.user.client:
                # Client : vérifier qu'il accède Ã  SON ouvrage
                client_ouvrage = request.user.client.ouvrage
                if client_ouvrage and client_ouvrage.id != ouvrage.id:
                    return HttpResponseForbidden("Vous n'avez pas accès Ã  cet ouvrage.")
            elif hasattr(request.user, 'employe') and request.user.employe and not request.user.is_superuser:
                from apps.employees.permissions import has_admin_access, est_responsable_actif_ouvrage
                if not has_admin_access(request.user) and not est_responsable_actif_ouvrage(request.user.employe, ouvrage.id):
                    return HttpResponseForbidden("Vous n'avez pas acces a cet ouvrage.")

            # Compteurs de tÃªte liés Ã  l'ouvrage
            compteurs = ouvrage.compteurs_tete.all()

            # Modalités de gestion
            modalites = ouvrage.modalites_gestion.all()
            modalites_actives = modalites.filter(statut='actif')

            # Tarifs volumétriques actifs avec tranches
            from apps.billing.models import TarifVolumetrique
            from django.utils import timezone
            today = timezone.now().date()
            tarifs_actifs = TarifVolumetrique.objects.filter(
                ouvrage=ouvrage,
                actif=True,
                datedebuttarif__lte=today
            ).filter(
                Q(datefintarif__isnull=True) | Q(datefintarif__gte=today)
            ).select_related('type_point_eau').prefetch_related('tranches_volumetriques')

            # Plannings liés Ã  l'ouvrage
            plannings_count = ouvrage.plannings.count()

            # Activités récentes réalisées (via Planning)
            activites_recentes_all = Planning.objects.filter(
                ouvrage=ouvrage,
                statut='termine'
            ).select_related(
                'employe',
                'fiche_poste',
                'type_activite'
            ).order_by('-date')

            # Pagination pour les activités récentes
            page_activites = request.GET.get('page_activites', 1)
            paginator_activites = Paginator(activites_recentes_all, 10)
            activites_recentes_page = paginator_activites.get_page(page_activites)

            # Points d'eau liés (via compteurs de tÃªte)
            points_eau_all = PointEau.objects.filter(ouvrage=ouvrage).select_related(
                'type_point_eau',
                'parcelle__village__fokontany__commune',
            )

            # Pagination pour les points d'eau
            page_points = request.GET.get('page_points', 1)
            paginator_points = Paginator(points_eau_all, 10)
            points_eau_page = paginator_points.get_page(page_points)

            # Equipements constitutifs avec pagination
            equipements_all = ouvrage.equipements_constitutifs.select_related('type_equipement')

            # Carte commune : equipements, points d'eau, villages et liaisons.
            from apps.organization.views import _ouvrage_entity_map_data
            ouvrage_map_data = _ouvrage_entity_map_data(
                ouvrage,
                points_eau_all,
                'point_eau',
                avec_contours=True,
            )

            # Pagination pour les équipements
            page_equipements = request.GET.get('page_equipements', 1)
            paginator_equipements = Paginator(equipements_all, 10)
            equipements_page = paginator_equipements.get_page(page_equipements)

            context['entity'] = {
                'type_display': 'Ouvrage',
                'nom': ouvrage.nom_ouvrage,
                'type': ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else '-',
                'annee_realisation': ouvrage.annee_realisation or '-',
                'annee_realisation_avant': ouvrage.annee_realisation_avant or '-',
                'intervenant': ouvrage.intervenant or '-',
                'saisonnier': 'Oui' if ouvrage.saisonnier else 'Non' if ouvrage.saisonnier is not None else '-',
                'observation': ouvrage.observation or '-',
            }

            # ========== ETAT DE L'OUVRAGE (WORKFLOW REPARATIONS) ==========
            from apps.planning.models import PlanningDetail, Designation, Activite
            from decimal import Decimal
            from django.core.serializers.json import DjangoJSONEncoder
            import pytz
            import re
            import json
            import statistics as stats_module

            # Année pour les analyses (année courante par défaut)
            annee_analyse = int(request.GET.get('annee_analyse', datetime.now().year))
            tz_madagascar = pytz.timezone('Indian/Antananarivo')

            # Calculer l'état de l'ouvrage basé sur les réparations
            etat_ouvrage = None
            historique_reparations = []

            # Récupérer les activités de réparation/réhabilitation/panne (compatibilité avec nouveau système FichePoste)
            from apps.planning.repair_classification import (
                get_planning_repair_classification,
                get_repair_fiches_queryset,
            )

            # Recherche dans l'ancien modèle Activite
            activites_reparation_ids = list(Activite.objects.filter(
                Q(nom__icontains='réparation') |
                Q(nom__icontains='reparation') |
                Q(nom__icontains='réhabilitation') |
                Q(nom__icontains='rehabilitation') |
                Q(nom__icontains='panne')
            ).values_list('id', flat=True))

            # Recherche dans le nouveau modèle FichePoste
            fiches_reparation_ids = list(
                get_repair_fiches_queryset().values_list('id', flat=True)
            )

            if activites_reparation_ids or fiches_reparation_ids:
                # L'historique part du Planning lui-meme. PlanningDetail est
                # optionnel : une reparation avec seulement une cible, une
                # remarque ou des photos doit rester visible.
                plannings_reparations = _get_ouvrage_repair_plannings(
                    ouvrage,
                    fiches_reparation_ids,
                    activites_reparation_ids,
                )

                # Récupérer les détails de planning pour cet ouvrage via FichePoste ou ActivitePoste
                details_reparations = PlanningDetail.objects.filter(
                    Q(planning__ouvrage=ouvrage) |
                    Q(point_eau__ouvrage=ouvrage) |
                    Q(equipement_constitutif__ouvrage=ouvrage)
                ).filter(
                    Q(planning__fiche_poste_id__in=fiches_reparation_ids) |
                    Q(planning__fiche_poste__activites_postes__activite_id__in=activites_reparation_ids) |
                    Q(planning__remarque__startswith='[Saisie depuis la fiche ouvrage]')
                ).select_related(
                    'planning',
                    'planning__fiche_poste',
                    'planning__type_activite',
                    'planning__employe',
                    'point_eau',
                    'equipement_constitutif',
                ).order_by('-planning__date').distinct()

                # Historique complet, toutes années confondues, dédupliqué par planning.
                historique_par_planning = {}
                for planning in plannings_reparations:
                    if _exclude_from_repair_history(planning.activite_display):
                        continue
                    planning_key = str(planning.id)
                    classification = get_planning_repair_classification(planning)
                    family_labels = {
                        'reparation': 'Réparation / entretien',
                        'rehabilitation': 'Réhabilitation',
                        'panne': 'Panne',
                    }
                    historique_par_planning[planning_key] = {
                        'id': planning_key,
                        'date': planning.date,
                        'activite': planning.activite_display,
                        'famille': family_labels.get(classification['family'], 'Intervention'),
                        'employe': planning.employe.nom_affichage if planning.employe else 'Non affecté',
                        'remarque': planning.remarque or '',
                        'statut': planning.get_statut_display() if planning.statut else 'Non défini',
                        'statut_code': planning.statut or '',
                        'photos': _planning_photos(planning.photo),
                        'cibles': [],
                    }
                    for detail in planning.details.all():
                        target = None
                        if detail.point_eau:
                            target = f"Point d'eau : {detail.point_eau.code_point_eau or detail.point_eau.nomabonne or detail.point_eau.id}"
                        elif detail.equipement_constitutif:
                            target = f"Équipement : {detail.equipement_constitutif.nom or detail.equipement_constitutif.id}"
                        if target and target not in historique_par_planning[planning_key]['cibles']:
                            historique_par_planning[planning_key]['cibles'].append(target)

                historique_reparations = list(historique_par_planning.values())

                # Analyser les réparations et stocker les détails
                reparations_passe = {}
                reparations_futur = {}
                rehabilitations_passe = {}
                rehabilitations_futur = {}
                pannes_passe = {}
                pannes_futur = {}
                durees = []
                today = timezone.now().date()

                for detail in details_reparations:
                    if detail.planning and detail.planning.date:
                        if _exclude_from_repair_history(detail.planning.activite_display):
                            continue
                        date_aware = detail.planning.date
                        if date_aware.tzinfo:
                            date_madagascar = date_aware.astimezone(tz_madagascar)
                        else:
                            date_madagascar = tz_madagascar.localize(date_aware)

                        date_obj = date_madagascar.date()

                        # Filtrer par année d'analyse
                        if date_obj.year == annee_analyse:
                            classification = get_planning_repair_classification(detail.planning)
                            is_passe = date_obj < today
                            planning_id = detail.planning.id

                            # Préparer les détails de l'intervention
                            intervention_detail = {
                                'id': str(planning_id),  # Convertir UUID en string
                                'date': date_obj.strftime('%d/%m/%Y'),
                                'activite': detail.planning.activite_display,
                                'employe': detail.planning.employe.nom_affichage if detail.planning.employe else '-',
                                'remarque': detail.planning.remarque or '-',
                                'statut': 'Terminé' if detail.planning.statut == 'termine' else 'En cours',
                                'point_eau': detail.point_eau.code_point_eau if detail.point_eau else None,
                                'equipement': detail.equipement_constitutif.nom if detail.equipement_constitutif else None,
                                'photos_count': _planning_photo_count(detail.planning.photo),
                            }

                            # Classifier l'activité
                            if classification['is_panne']:
                                if is_passe:
                                    pannes_passe[planning_id] = intervention_detail
                                else:
                                    pannes_futur[planning_id] = intervention_detail

                            if classification['family'] == 'rehabilitation':
                                if is_passe:
                                    rehabilitations_passe[planning_id] = intervention_detail
                                else:
                                    rehabilitations_futur[planning_id] = intervention_detail
                            elif classification['family'] == 'reparation':
                                if is_passe:
                                    reparations_passe[planning_id] = intervention_detail
                                else:
                                    reparations_futur[planning_id] = intervention_detail

                            # Calculer la durée
                            if detail.planning.datesignalementactivite:
                                date_signalement_raw = detail.planning.datesignalementactivite
                                if hasattr(date_signalement_raw, 'date'):
                                    date_signalement = date_signalement_raw.date()
                                else:
                                    date_signalement = date_signalement_raw

                                if date_signalement <= date_obj:
                                    duree_jours = (date_obj - date_signalement).days
                                    if duree_jours > 0:
                                        durees.append(duree_jours)

                # CALCUL DU STATUT (7 niveaux par ordre de priorité)
                if pannes_passe:
                    statut = 'reparation_panne_effectuee'
                    statut_label = 'Réparation panne effectuée'
                    statut_badge = 'success'
                    statut_icon = 'check-circle'
                elif rehabilitations_passe:
                    statut = 'rehabilitation_effectuee'
                    statut_label = 'Réhabilitation effectuée'
                    statut_badge = 'info'
                    statut_icon = 'tools'
                elif reparations_passe:
                    statut = 'reparation_effectuee'
                    statut_label = 'Réparation effectuée'
                    statut_badge = 'primary'
                    statut_icon = 'wrench'
                elif pannes_futur:
                    statut = 'panne_prevue'
                    statut_label = 'Panne Ã  réparer'
                    statut_badge = 'error'
                    statut_icon = 'exclamation-triangle'
                elif rehabilitations_futur:
                    statut = 'rehabilitation_prevue'
                    statut_label = 'Réhabilitation prévue'
                    statut_badge = 'warning'
                    statut_icon = 'calendar-check'
                elif reparations_futur:
                    statut = 'reparation_prevue'
                    statut_label = 'Réparation prévue'
                    statut_badge = 'ghost'
                    statut_icon = 'calendar'
                else:
                    statut = 'sans_reparation'
                    statut_label = 'Sans réparation'
                    statut_badge = 'success'
                    statut_icon = 'check-double'

                # CALCUL DU GRADING (5 niveaux par ordre de priorité)
                if not reparations_futur and not rehabilitations_futur and not pannes_futur:
                    grading = 'A'
                    grading_label = 'A'
                    grading_badge = 'success'
                elif rehabilitations_futur and pannes_futur:
                    grading = 'D_panne'
                    grading_label = 'D Panne'
                    grading_badge = 'error'
                elif rehabilitations_futur and not pannes_futur:
                    grading = 'D'
                    grading_label = 'D'
                    grading_badge = 'error'
                elif reparations_futur and pannes_futur:
                    grading = 'B_panne'
                    grading_label = 'B Panne'
                    grading_badge = 'warning'
                elif reparations_futur and not pannes_futur:
                    grading = 'B'
                    grading_label = 'B'
                    grading_badge = 'warning'
                else:
                    grading = 'C'
                    grading_label = 'C'
                    grading_badge = 'info'

                # Calculer statistiques de durée
                duree_moyenne = sum(durees) / len(durees) if durees else 0
                duree_mediane = stats_module.median(durees) if durees else 0

                # Sérialiser les détails en JSON pour le template
                import json
                details_reparations_passe_json = json.dumps(list(reparations_passe.values()))
                details_reparations_futur_json = json.dumps(list(reparations_futur.values()))
                details_rehabilitations_passe_json = json.dumps(list(rehabilitations_passe.values()))
                details_rehabilitations_futur_json = json.dumps(list(rehabilitations_futur.values()))
                details_pannes_passe_json = json.dumps(list(pannes_passe.values()))
                details_pannes_futur_json = json.dumps(list(pannes_futur.values()))

                etat_ouvrage = {
                    'statut': statut,
                    'statut_label': statut_label,
                    'statut_badge': statut_badge,
                    'statut_icon': statut_icon,
                    'grading': grading,
                    'grading_label': grading_label,
                    'grading_badge': grading_badge,
                    'nb_reparations_passe': len(reparations_passe),
                    'nb_reparations_futur': len(reparations_futur),
                    'nb_rehabilitations_passe': len(rehabilitations_passe),
                    'nb_rehabilitations_futur': len(rehabilitations_futur),
                    'nb_pannes_passe': len(pannes_passe),
                    'nb_pannes_futur': len(pannes_futur),
                    'duree_moyenne': duree_moyenne,
                    'duree_mediane': duree_mediane,
                    'nb_interventions': len(durees),
                    # Détails des interventions pour le modal (JSON)
                    'details_reparations_passe': details_reparations_passe_json,
                    'details_reparations_futur': details_reparations_futur_json,
                    'details_rehabilitations_passe': details_rehabilitations_passe_json,
                    'details_rehabilitations_futur': details_rehabilitations_futur_json,
                    'details_pannes_passe': details_pannes_passe_json,
                    'details_pannes_futur': details_pannes_futur_json,
                }

            historique_reparations_page = Paginator(
                historique_reparations,
                8,
            ).get_page(request.GET.get('historique_page', 1))
            historique_reparations_page_range = historique_reparations_page.paginator.get_elided_page_range(
                historique_reparations_page.number,
                on_each_side=2,
                on_ends=1,
            )

            # ========== ANALYSES DE CONSOMMATION ET PAIEMENT ==========
            # Déterminer la modalité de paiement active de l'ouvrage
            modalite_active = modalites_actives.first() if modalites_actives.exists() else None
            type_modalite = modalite_active.modalitepaiement if modalite_active else None

            # Initialiser les données d'analyse
            analyse_consommation = None
            analyse_paiement_forfait = None
            analyse_paiement_volume = None
            mois_labels = (
                'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
            )

            # ========== ANALYSE CONSOMMATION (pour paiements au volume) ==========
            if type_modalite in ['au_volume', 'mixte']:
                # Récupérer les points d'eau de l'ouvrage
                points_eau_ouvrage = points_eau_all

                # Récupérer les relevés de l'année
                from apps.billing.models import Releve
                releves = Releve.objects.filter(
                    point_eau__in=points_eau_ouvrage
                ).select_related('point_eau__type_point_eau')

                # Filtrer par année avec conversion timezone
                releves_annee = []
                for releve in releves:
                    if releve.datereleve and releve.datereleve.year == annee_analyse:
                        volume = float(releve.volume_facture) if releve.volume_facture else 0
                        if volume > 0:
                            releves_annee.append(releve)

                # Calculer les statistiques de consommation
                if releves_annee:
                    volume_total = sum(float(r.volume_facture) if r.volume_facture else 0 for r in releves_annee)
                    nb_releves = len(releves_annee)
                    volume_moyen = volume_total / nb_releves if nb_releves > 0 else 0

                    # Consommation mensuelle
                    from collections import defaultdict
                    volumes_par_mois = defaultdict(float)
                    for r in releves_annee:
                        mois = r.datereleve.month
                        volumes_par_mois[mois] += float(r.volume_facture) if r.volume_facture else 0

                    consommation_mensuelle = [
                        {'mois': i, 'volume': volumes_par_mois.get(i, 0)}
                        for i in range(1, 13)
                    ]

                    # Convertir en JSON pour le template
                    import json
                    consommation_mensuelle_json = json.dumps(consommation_mensuelle)

                    analyse_consommation = {
                        'volume_total': volume_total,
                        'nb_releves': nb_releves,
                        'volume_moyen': volume_moyen,
                        'consommation_mensuelle': consommation_mensuelle,
                        'consommation_mensuelle_json': consommation_mensuelle_json,
                        'nb_points_eau': points_eau_ouvrage.count(),
                    }

            # ========== ANALYSE PAIEMENT FORFAITAIRE ==========
            if type_modalite in ['forfaitaire', 'mixte']:
                from apps.billing.models import PaiementForfaitaire

                # Points d'eau avec tarif forfaitaire
                points_eau_forfait = points_eau_all.filter(tarifforfaitaire__isnull=False)

                # Statistiques par statut
                nb_tout_paye = 0
                nb_partiellement_paye = 0
                nb_non_paye = 0
                montant_prevu_total = Decimal('0.00')
                montant_paye_total = Decimal('0.00')
                forfait_par_mois = {
                    mois: {
                        'nb_factures': 0,
                        'nb_paiements': 0,
                        'montant_facture': Decimal('0.00'),
                        'montant_paye': Decimal('0.00'),
                    }
                    for mois in range(1, 13)
                }

                for pe in points_eau_forfait:
                    tarif = tarif_pour_annee(pe, annee_analyse)
                    montant_prevu_annuel = tarif * 4  # 4 trimestres
                    montant_prevu_total += montant_prevu_annuel

                    # Récupérer les paiements forfaitaires de l'année
                    paiements_annee = PaiementForfaitaire.objects.filter(
                        point_eau=pe,
                        date_facture__year=annee_analyse
                    )

                    # Calculer le montant payé pour ce point d'eau
                    montant_paye_pe = Decimal('0.00')
                    for paiement in paiements_annee:
                        quantite = int(paiement.quantite) if paiement.quantite else 0
                        if paiement.montant is not None:
                            montant = Decimal(str(paiement.montant))
                        else:
                            montant = Decimal(quantite) * tarif
                        mois_facture = paiement.date_facture.month
                        detail_mois = forfait_par_mois[mois_facture]
                        detail_mois['nb_factures'] += 1
                        detail_mois['montant_facture'] += montant
                        if paiement.est_paye:
                            montant_paye_pe += montant
                            detail_mois['nb_paiements'] += 1
                            detail_mois['montant_paye'] += montant

                    montant_paye_total += montant_paye_pe

                    # Déterminer le statut
                    if montant_prevu_annuel > 0 and montant_paye_pe >= montant_prevu_annuel:
                        nb_tout_paye += 1
                    elif montant_paye_pe > 0:
                        nb_partiellement_paye += 1
                    else:
                        nb_non_paye += 1

                taux_recouvrement = (float(montant_paye_total) / float(montant_prevu_total) * 100) if montant_prevu_total > 0 else 0
                details_mensuels_forfait = []
                for mois in range(1, 13):
                    detail = forfait_par_mois[mois]
                    facture = detail['montant_facture']
                    paye = detail['montant_paye']
                    if facture <= 0:
                        continue
                    taux = (float(paye) / float(facture) * 100) if facture > 0 else 0
                    if paye >= facture:
                        statut = 'paye'
                    elif paye > 0:
                        statut = 'partiel'
                    else:
                        statut = 'non_paye'
                    details_mensuels_forfait.append({
                        'mois': mois,
                        'mois_label': mois_labels[mois - 1],
                        'nb_factures': detail['nb_factures'],
                        'nb_paiements': detail['nb_paiements'],
                        'montant_facture': facture,
                        'montant_paye': paye,
                        'reste': max(facture - paye, Decimal('0.00')),
                        'taux': taux,
                        'statut': statut,
                    })

                analyse_paiement_forfait = {
                    'nb_points_eau': points_eau_forfait.count(),
                    'montant_prevu': montant_prevu_total,
                    'montant_paye': montant_paye_total,
                    'taux_recouvrement': taux_recouvrement,
                    'nb_tout_paye': nb_tout_paye,
                    'nb_partiellement_paye': nb_partiellement_paye,
                    'nb_non_paye': nb_non_paye,
                    'details_mensuels': details_mensuels_forfait,
                }

            # ========== ANALYSE PAIEMENT VOLUMETRIQUE ==========
            if type_modalite in ['au_volume', 'mixte']:
                from apps.billing.models import Releve
                from apps.accounting.models import BaseDiameX
                from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
                from apps.accounting.views_verification_ouvrages import diviser_paiement_volume_multi
                from apps.accounting.views import (
                    _build_coupure_periods_by_point,
                    _is_releve_non_recouvrable,
                )

                # Montant facturé: logique identique au dashboard volume (mois de facturation = relevé + 1 mois)
                releves_factures = list(Releve.objects.filter(
                    point_eau__in=points_eau_all,
                    montant__isnull=False,
                    montant__gt=0
                ).exclude(
                    remarque__icontains='coupé'
                ).select_related('point_eau'))

                # Les factures de points coupés restent disponibles pour le
                # pointage, mais sortent du prévu tant qu'elles sont non pointées.
                point_ids_factures = {
                    str(releve.point_eau_id)
                    for releve in releves_factures
                    if releve.point_eau_id
                }
                periodes_coupure = _build_coupure_periods_by_point(point_ids_factures)

                releves_factures_annee = []
                montant_facture_total = Decimal('0.00')
                montant_non_recouvrable_total = Decimal('0.00')
                nb_non_recouvrables_total = 0
                montant_paye_volume_total = Decimal('0.00')
                volume_par_mois = {
                    mois: {
                        'nb_factures': 0,
                        'montant_facture': Decimal('0.00'),
                        'montant_paye': Decimal('0.00'),
                        'nb_non_recouvrables': 0,
                        'montant_non_recouvrable': Decimal('0.00'),
                    }
                    for mois in range(1, 13)
                }

                for releve in releves_factures:
                    if not releve.datereleve:
                        continue
                    annee_facture = releve.datereleve.year + 1 if releve.datereleve.month == 12 else releve.datereleve.year
                    if annee_facture != annee_analyse:
                        continue
                    mois_facture = 1 if releve.datereleve.month == 12 else releve.datereleve.month + 1
                    montant_releve = Decimal(str(releve.montant))
                    if _is_releve_non_recouvrable(releve, periodes_coupure):
                        montant_non_recouvrable_total += montant_releve
                        nb_non_recouvrables_total += 1
                        volume_par_mois[mois_facture]['nb_non_recouvrables'] += 1
                        volume_par_mois[mois_facture]['montant_non_recouvrable'] += montant_releve
                        continue
                    montant_facture_total += montant_releve
                    releves_factures_annee.append(releve)
                    volume_par_mois[mois_facture]['nb_factures'] += 1
                    volume_par_mois[mois_facture]['montant_facture'] += montant_releve

                # Montant payé: logique DiameX du dashboard volume (compte 707401 + parsing du libellé)
                diamex_707401 = BaseDiameX.objects.filter(compte_code='707401')
                ouvrage_id_str = str(ouvrage.id)

                for entry in diamex_707401:
                    segments = []
                    if entry.description and ';' in entry.description:
                        segments = diviser_paiement_volume_multi(
                            entry.description,
                            entry.compte_code,
                            entry.montant_in if entry.montant_in else 0
                        )

                    if segments:
                        for segment in segments:
                            extraction = segment.get('extraction') or {}
                            ouvrage_obj = extraction.get('ouvrage_obj')
                            if (
                                ouvrage_obj
                                and str(ouvrage_obj.id) == ouvrage_id_str
                                and extraction.get('mois')
                                and extraction.get('annee') == annee_analyse
                            ):
                                montant_segment = Decimal(str(segment.get('montant') or 0))
                                mois_paiement = int(extraction.get('mois'))
                                montant_paye_volume_total += montant_segment
                                if 1 <= mois_paiement <= 12:
                                    volume_par_mois[mois_paiement]['montant_paye'] += montant_segment
                    else:
                        extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
                        ouvrage_obj = extraction.get('ouvrage_obj')
                        if (
                            ouvrage_obj
                            and str(ouvrage_obj.id) == ouvrage_id_str
                            and extraction.get('mois')
                            and extraction.get('annee') == annee_analyse
                        ):
                            montant_entry = Decimal(str(entry.montant_in or 0))
                            mois_paiement = int(extraction.get('mois'))
                            montant_paye_volume_total += montant_entry
                            if 1 <= mois_paiement <= 12:
                                volume_par_mois[mois_paiement]['montant_paye'] += montant_entry

                taux_paiement_volume = (float(montant_paye_volume_total) / float(montant_facture_total) * 100) if montant_facture_total > 0 else 0
                details_mensuels_volume = []
                for mois in range(1, 13):
                    detail = volume_par_mois[mois]
                    facture = detail['montant_facture']
                    paye = detail['montant_paye']
                    montant_non_recouvrable = detail['montant_non_recouvrable']
                    if facture <= 0 and montant_non_recouvrable <= 0:
                        continue
                    taux = (float(paye) / float(facture) * 100) if facture > 0 else 0
                    if facture <= 0 and montant_non_recouvrable > 0:
                        statut = 'hors_recouvrement'
                    elif paye >= facture:
                        statut = 'paye'
                    elif paye > 0:
                        statut = 'partiel'
                    else:
                        statut = 'non_paye'
                    details_mensuels_volume.append({
                        'mois': mois,
                        'mois_label': mois_labels[mois - 1],
                        'nb_factures': detail['nb_factures'],
                        'montant_facture': facture,
                        'montant_paye': paye,
                        'reste': max(facture - paye, Decimal('0.00')),
                        'taux': taux,
                        'statut': statut,
                        'nb_non_recouvrables': detail['nb_non_recouvrables'],
                        'montant_non_recouvrable': montant_non_recouvrable,
                    })

                # Séparer les mois clôturés du mois actuellement en cours.
                aujourd_hui = timezone.localdate()
                if annee_analyse < aujourd_hui.year:
                    mois_passes_ids = list(range(1, 13))
                    mois_courant_id = None
                elif annee_analyse == aujourd_hui.year:
                    mois_passes_ids = list(range(1, aujourd_hui.month))
                    mois_courant_id = aujourd_hui.month
                else:
                    mois_passes_ids = []
                    mois_courant_id = None

                def _resume_recouvrement_volume(mois_ids):
                    facture = sum(
                        (volume_par_mois[mois]['montant_facture'] for mois in mois_ids),
                        Decimal('0.00'),
                    )
                    paye = sum(
                        (volume_par_mois[mois]['montant_paye'] for mois in mois_ids),
                        Decimal('0.00'),
                    )
                    nb_factures = sum(volume_par_mois[mois]['nb_factures'] for mois in mois_ids)
                    nb_non_recouvrables = sum(volume_par_mois[mois]['nb_non_recouvrables'] for mois in mois_ids)
                    montant_non_recouvrable = sum(
                        (volume_par_mois[mois]['montant_non_recouvrable'] for mois in mois_ids),
                        Decimal('0.00'),
                    )
                    taux = (float(paye) / float(facture) * 100) if facture > 0 else 0
                    return {
                        'montant_facture': facture,
                        'montant_paye': paye,
                        'reste': max(facture - paye, Decimal('0.00')),
                        'nb_factures': nb_factures,
                        'taux_recouvrement': taux,
                        'nb_non_recouvrables': nb_non_recouvrables,
                        'montant_non_recouvrable': montant_non_recouvrable,
                    }

                resume_mois_passes = _resume_recouvrement_volume(mois_passes_ids)
                if mois_passes_ids:
                    resume_mois_passes['label'] = (
                        f"Janvier à {mois_labels[mois_passes_ids[-1] - 1]} {annee_analyse}"
                    )
                else:
                    resume_mois_passes['label'] = f"Aucun mois clôturé en {annee_analyse}"

                resume_mois_courant = None
                if mois_courant_id:
                    resume_mois_courant = _resume_recouvrement_volume([mois_courant_id])
                    resume_mois_courant['label'] = f"{mois_labels[mois_courant_id - 1]} {annee_analyse}"

                analyse_paiement_volume = {
                    'nb_factures': len(releves_factures_annee),
                    'nb_non_recouvrables': nb_non_recouvrables_total,
                    'montant_non_recouvrable': montant_non_recouvrable_total,
                    'montant_facture': montant_facture_total,
                    'montant_paye': montant_paye_volume_total,
                    'taux_paiement': taux_paiement_volume,
                    'details_mensuels': details_mensuels_volume,
                    'mois_passes': resume_mois_passes,
                    'mois_courant': resume_mois_courant,
                }

            # ========== ANALYSE DES PIÃˆCES DE RECHANGE ==========
            analyse_pieces = None
            from apps.planning.models import BonLivraison
            from collections import defaultdict

            # Récupérer les PlanningDetails avec pièces (concerne_livraison=True)
            pieces_planning = PlanningDetail.objects.filter(
                Q(planning__ouvrage=ouvrage) |
                Q(point_eau__ouvrage=ouvrage) |
                Q(equipement_constitutif__ouvrage=ouvrage),
                designation__concerne_livraison=True,
                designation__actif=True
            ).select_related('designation', 'designation__type_designation', 'planning')

            # Récupérer les BonLivraison avec pièces
            pieces_livraison = BonLivraison.objects.filter(
                Q(planning__ouvrage=ouvrage) |
                Q(point_eau__ouvrage=ouvrage) |
                Q(equipement__ouvrage=ouvrage),
                designation__concerne_livraison=True,
                designation__actif=True
            ).select_related('designation', 'designation__type_designation')

            # Agréger les données par pièce
            pieces_usage = defaultdict(lambda: {
                'quantite': 0,
                'montant': 0,
                'nb_utilisations': 0
            })

            # Comptabiliser les PlanningDetails
            for detail in pieces_planning:
                # Compat: certains contextes utilisent `quantity` (modèle),
                # d'autres peuvent encore envoyer `quantite` (legacy).
                quantite_detail = getattr(detail, 'quantity', None)
                if quantite_detail is None:
                    quantite_detail = getattr(detail, 'quantite', None)

                if detail.designation_id and quantite_detail:
                    key = detail.designation_id
                    pieces_usage[key]['nom'] = detail.designation.nom
                    pieces_usage[key]['type'] = detail.designation.type_designation.nom if detail.designation.type_designation else 'N/A'
                    pieces_usage[key]['quantite'] += float(quantite_detail)
                    pieces_usage[key]['montant'] += float(detail.montant or 0)
                    pieces_usage[key]['nb_utilisations'] += 1

            # Comptabiliser les BonLivraison
            for bl in pieces_livraison:
                if bl.designation_id and bl.quantite:
                    key = bl.designation_id
                    pieces_usage[key]['nom'] = bl.designation.nom
                    pieces_usage[key]['type'] = bl.designation.type_designation.nom if bl.designation.type_designation else 'N/A'
                    pieces_usage[key]['quantite'] += float(bl.quantite)
                    prix_unitaire = float(bl.designation.prix_unitaire or 0)
                    pieces_usage[key]['montant'] += float(bl.quantite) * prix_unitaire
                    pieces_usage[key]['nb_utilisations'] += 1

            # Trier par quantité décroissante et prendre le top 10
            pieces_list = [
                {
                    'designation_id': str(k),
                    'nom': v['nom'],
                    'type': v['type'],
                    'quantite': v['quantite'],
                    'montant': v['montant'],
                    'nb_utilisations': v['nb_utilisations']
                }
                for k, v in pieces_usage.items()
            ]
            top_pieces = sorted(pieces_list, key=lambda x: x['quantite'], reverse=True)[:10]

            # Statistiques globales des pièces
            if pieces_list:
                analyse_pieces = {
                    'total_quantite': sum(p['quantite'] for p in pieces_list),
                    'total_montant': sum(p['montant'] for p in pieces_list),
                    'nb_pieces_differentes': len(pieces_list),
                    'nb_utilisations': sum(p['nb_utilisations'] for p in pieces_list),
                    'top_pieces': top_pieces,
                    'top_pieces_json': json.dumps(top_pieces, cls=DjangoJSONEncoder, ensure_ascii=False),
                }

            context['related_data'] = {
                'points_eau_count': points_eau_all.count(),
                'equipements_count': ouvrage.equipements_constitutifs.count(),
                'compteurs_count': compteurs.count(),
                'modalites_count': modalites.count(),
                'modalites_actives': modalites_actives,
                'tarifs_actifs': tarifs_actifs,
                'activites_recentes_page': activites_recentes_page,
                'plannings_count': plannings_count,
                'points_eau_page': points_eau_page,
                'equipements_page': equipements_page,
                'repair_entry_points': points_eau_all.order_by('code_point_eau'),
                'repair_entry_equipements': equipements_all.order_by('nom'),
                'repair_entry_activities': get_repair_fiches_queryset().order_by('tache'),
                'can_add_repair_entry': not bool(getattr(request.user, 'client', None)) or request.user.is_staff,
                'ouvrage_map_data': ouvrage_map_data,
                'dossiers_techniques': ouvrage.dossiers_techniques.all(),
                'dossiers_techniques_count': ouvrage.dossiers_techniques.count(),
                # Etat de l'ouvrage
                'etat_ouvrage': etat_ouvrage,
                'historique_reparations': historique_reparations_page,
                'historique_reparations_page_range': historique_reparations_page_range,
                'historique_reparations_open': 'historique_page' in request.GET,
                # Analyses ajoutées
                'type_modalite': type_modalite,
                'annee_analyse': annee_analyse,
                'analyse_consommation': analyse_consommation,
                'analyse_paiement_forfait': analyse_paiement_forfait,
                'analyse_paiement_volume': analyse_paiement_volume,
                # Analyse des pièces de rechange
                'analyse_pieces': analyse_pieces,
            }

        elif entity_type == 'employe':
            employe = Employe.objects.select_related('base', 'poste').get(id=entity_id)

            # Plannings de l'employé
            plannings = employe.plannings.select_related('ouvrage', 'fiche_poste', 'type_activite').all()
            plannings_valides = plannings.filter(estvalide=True).count()
            plannings_non_valides = plannings.filter(estvalide=False).count()

            # Ouvrages sur lesquels l'employé a travaillé
            ouvrages = Ouvrage.objects.filter(
                plannings__employe=employe
            ).distinct()

            # Récupérer la signature/photo si disponible
            photo_url = None
            if employe.signature and isinstance(employe.signature, list) and len(employe.signature) > 0:
                first_photo = employe.signature[0]
                if isinstance(first_photo, dict) and 'data' in first_photo:
                    photo_url = first_photo['data']

            # Déterminer si l'employé est actif (pas de date de débauchage)
            est_actif = employe.date_debauchage is None

            context['entity'] = {
                'type_display': 'Employé',
                'nom': employe.nom_affichage,
                'nom_complet': f"{employe.nom} {employe.prenom or ''}",
                'surnom': employe.surnom or '-',
                'email': employe.mail or '-',
                'telephone': employe.telephone or '-',
                'poste': employe.poste.nom_poste if employe.poste else '-',
                'base': employe.base.nom_base if employe.base else '-',
                'statut': 'Actif' if est_actif else 'Inactif',
                'photo_url': photo_url,
            }

            context['related_data'] = {
                'plannings_total': plannings.count(),
                'plannings_valides': plannings_valides,
                'plannings_non_valides': plannings_non_valides,
                'ouvrages_count': ouvrages.count(),
                'ouvrages': ouvrages[:10],
                'plannings_recents': plannings.order_by('-date')[:10],
            }

        elif entity_type == 'representant':
            from apps.usagers.models import RepresentantUsager

            representant = RepresentantUsager.objects.select_related(
                'village__fokontany__commune__district__region'
            ).get(id=entity_id)

            village = representant.village
            avis_qs = representant.avis.select_related('reunion').order_by('-date_avis')
            participations = representant.participations_reunions.select_related('reunion').order_by('-reunion__date_reunion')

            context['entity'] = {
                'type_display': 'Représentante des usagers',
                'nom': representant.nom or 'Sans nom',
                'village': village.nom_village if village else '-',
                'fokontany': village.fokontany.nom_fokontany if village and village.fokontany else '-',
                'commune': village.fokontany.commune.nom_commune if village and village.fokontany and village.fokontany.commune else '-',
                'contact': representant.contact or '-',
                'date_debut': representant.date_debut.strftime('%d/%m/%Y') if representant.date_debut else '-',
                'date_fin': representant.date_fin.strftime('%d/%m/%Y') if representant.date_fin else '-',
                'statut': 'Actif' if representant.est_actif else 'Inactif',
                'observation': representant.observation or '-',
            }

            context['related_data'] = {
                'avis_total': avis_qs.count(),
                'avis_recents': avis_qs[:10],
                'participations_total': participations.count(),
                'participations_recentes': participations[:10],
            }

        elif entity_type == 'autorite':
            from apps.usagers.models import Autorite

            autorite = Autorite.objects.select_related('fokontany', 'commune', 'district', 'region').get(id=entity_id)
            participations = autorite.participations_reunions.select_related('reunion').order_by('-reunion__date_reunion')

            context['entity'] = {
                'type_display': 'Autorité',
                'nom': autorite.nom,
                'type': autorite.get_type_autorite_display() or '-',
                'fonction': autorite.fonction or '-',
                'zone': autorite.zone_affichee or '-',
                'contact': autorite.contact or '-',
                'email': autorite.email or '-',
                'statut': 'Actif' if autorite.actif else 'Inactif',
                'observation': autorite.observation or '-',
            }

            context['related_data'] = {
                'participations_total': participations.count(),
                'participations_recentes': participations[:10],
            }

        elif entity_type == 'tiers':
            from apps.usagers.models import TiersParticipant

            tiers = TiersParticipant.objects.get(id=entity_id)
            participations = tiers.participations_reunions.select_related('reunion').order_by('-reunion__date_reunion')

            context['entity'] = {
                'type_display': 'Tiers',
                'nom': tiers.nom,
                'type': tiers.get_type_tiers_display() or '-',
                'organisme': tiers.organisme or '-',
                'fonction': tiers.fonction or '-',
                'contact': tiers.contact or '-',
                'email': tiers.email or '-',
                'statut': 'Actif' if tiers.actif else 'Inactif',
                'observation': tiers.observation or '-',
            }

            context['related_data'] = {
                'participations_total': participations.count(),
                'participations_recentes': participations[:10],
            }

        elif entity_type == 'fournisseur':
            from apps.billing.models import Fournisseur

            fournisseur = Fournisseur.objects.select_related('adresse_fournisseur').get(id=entity_id)
            adresse = fournisseur.adresse_fournisseur.adresse if fournisseur.adresse_fournisseur_id else (fournisseur.adresse or '-')
            type_display = fournisseur.get_type_fournisseur_display() if fournisseur.type_fournisseur else '-'

            context['entity'] = {
                'type_display': 'Fournisseur',
                'nom': fournisseur.nom_fournisseur,
                'type': type_display,
                'telephone': fournisseur.telephone or '-',
                'email': fournisseur.email or '-',
                'adresse': adresse,
                'nif_ou_isi': fournisseur.get_nif_ou_isi_display() if fournisseur.nif_ou_isi else '-',
                'numero_nif': fournisseur.numero_nif or '-',
                'numero_stat': fournisseur.numero_stat or '-',
                'code_tiers': fournisseur.code_tiers or '-',
                'tacheron': 'Oui' if fournisseur.tacheron else 'Non',
                'prestataire': 'Oui' if fournisseur.prestation else 'Non',
                'statut': 'Actif' if fournisseur.actif else 'Inactif',
            }

        elif entity_type == 'point_eau':
            from django.http import HttpResponseForbidden
            from datetime import datetime

            point = PointEau.objects.select_related(
                'type_point_eau', 'ouvrage', 'parcelle', 'compteur_tete'
            ).get(id=entity_id)

            # Vérifier si l'utilisateur est un client et si le point d'eau lui appartient
            if hasattr(request.user, 'client') and request.user.client:
                # Client : vérifier qu'il accède Ã  SON point d'eau
                if request.user.client.point_eau_id != point.id:
                    return HttpResponseForbidden("Vous n'avez pas accès Ã  ce point d'eau.")
            elif hasattr(request.user, 'employe') and request.user.employe and not request.user.is_superuser:
                from apps.employees.permissions import has_admin_access, est_responsable_actif_ouvrage
                if not has_admin_access(request.user):
                    if not point.ouvrage_id or not est_responsable_actif_ouvrage(request.user.employe, point.ouvrage_id):
                        return HttpResponseForbidden("Vous n'avez pas acces a ce point d'eau.")

            # Récupérer la première photo si disponible
            photo_url = None
            if point.photos and isinstance(point.photos, list) and len(point.photos) > 0:
                first_photo = point.photos[0]
                if isinstance(first_photo, dict) and 'data' in first_photo:
                    photo_data = str(first_photo.get('data') or '')
                    if photo_data.startswith('data:'):
                        photo_url = photo_data
                    elif photo_data:
                        content_type = first_photo.get('content_type') or 'image/jpeg'
                        photo_url = f"data:{content_type};base64,{photo_data}"

            context['entity'] = {
                'type_display': 'Point d\'eau',
                'code': point.code_point_eau,
                'nom_abonne': point.nomabonne or '-',
                'type': point.type_point_eau.nom_type if point.type_point_eau else '-',
                'type_abonne': point.typeabonne or '-',
                'ouvrage': point.ouvrage.nom_ouvrage if point.ouvrage else '-',
                'parcelle': str(point.parcelle) if point.parcelle else '-',
                'tarif_forfaitaire': f"{point.tarifforfaitaire} Ar" if point.tarifforfaitaire else '-',
                'date_branchement': point.datebranchement.strftime('%d/%m/%Y') if point.datebranchement else '-',
                'latitude': point.latitude if point.latitude is not None else '-',
                'longitude': point.longitude if point.longitude is not None else '-',
                'photo_url': photo_url,
            }

            # ========== ANALYSES DE CONSOMMATION ET PAIEMENT POUR POINT D'EAU ==========
            from apps.planning.models import PlanningDetail, Designation
            from decimal import Decimal
            import pytz
            import json

            # Année pour les analyses (année courante par défaut)
            annee_analyse = int(request.GET.get('annee_analyse', datetime.now().year))
            tz_madagascar = pytz.timezone('Indian/Antananarivo')

            # Déterminer la modalité de paiement via l'ouvrage
            modalite_active = None
            type_modalite = None
            if point.ouvrage:
                modalite_active = point.ouvrage.modalites_gestion.filter(date_fin__isnull=True).first()
                type_modalite = modalite_active.modalitepaiement if modalite_active else None

            # Initialiser les données d'analyse
            analyse_consommation_pe = None
            analyse_paiement_forfait_pe = None
            analyse_paiement_volume_pe = None

            # ========== ANALYSE CONSOMMATION (pour paiements au volume) ==========
            if type_modalite in ['au_volume', 'mixte']:
                from apps.billing.models import Releve

                # Récupérer les relevés de l'année pour ce point d'eau
                releves = Releve.objects.filter(point_eau=point)

                # Filtrer par année avec conversion timezone
                releves_annee = []
                for releve in releves:
                    if releve.datereleve and releve.datereleve.year == annee_analyse:
                        volume = float(releve.volume_facture) if releve.volume_facture else 0
                        if volume > 0:
                            releves_annee.append(releve)

                # Calculer les statistiques de consommation
                if releves_annee:
                    volume_total = sum(float(r.volume_facture) if r.volume_facture else 0 for r in releves_annee)
                    nb_releves = len(releves_annee)
                    volume_moyen = volume_total / nb_releves if nb_releves > 0 else 0

                    # Consommation mensuelle
                    from collections import defaultdict
                    volumes_par_mois = defaultdict(float)
                    for r in releves_annee:
                        mois = r.datereleve.month
                        volumes_par_mois[mois] += float(r.volume_facture) if r.volume_facture else 0

                    consommation_mensuelle = [
                        {'mois': i, 'volume': volumes_par_mois.get(i, 0)}
                        for i in range(1, 13)
                    ]

                    consommation_mensuelle_json = json.dumps(consommation_mensuelle)

                    analyse_consommation_pe = {
                        'volume_total': volume_total,
                        'nb_releves': nb_releves,
                        'volume_moyen': volume_moyen,
                        'consommation_mensuelle': consommation_mensuelle,
                        'consommation_mensuelle_json': consommation_mensuelle_json,
                    }

            # ========== ANALYSE PAIEMENT FORFAITAIRE ==========
            if type_modalite in ['forfaitaire', 'mixte'] and point.tarifforfaitaire:
                from apps.billing.models import PaiementForfaitaire

                tarif = tarif_pour_annee(point, annee_analyse)
                montant_prevu_annuel = tarif * 4  # 4 trimestres

                # Récupérer les paiements forfaitaires de l'année
                paiements_annee = PaiementForfaitaire.objects.filter(
                    point_eau=point,
                    date_facture__year=annee_analyse
                )

                # Calculer les trimestres payés
                trimestres = {
                    'T1': {'paye': 0, 'non_paye': 0, 'mois': [1, 2, 3]},
                    'T2': {'paye': 0, 'non_paye': 0, 'mois': [4, 5, 6]},
                    'T3': {'paye': 0, 'non_paye': 0, 'mois': [7, 8, 9]},
                    'T4': {'paye': 0, 'non_paye': 0, 'mois': [10, 11, 12]},
                }

                montant_paye = Decimal('0.00')
                montant_non_paye = Decimal('0.00')

                for paiement in paiements_annee:
                    if not paiement.date_facture:
                        continue

                    mois = paiement.date_facture.month
                    quantite = int(paiement.quantite) if paiement.quantite else 0
                    montant_val = Decimal(str(paiement.montant)) if paiement.montant else (Decimal(quantite) * tarif)

                    for trimestre, data in trimestres.items():
                        if mois in data['mois']:
                            if paiement.est_paye:
                                data['paye'] += quantite
                                montant_paye += montant_val
                            else:
                                data['non_paye'] += quantite
                                montant_non_paye += montant_val
                            break

                qte_payee = sum(t['paye'] for t in trimestres.values())
                qte_non_payee = sum(t['non_paye'] for t in trimestres.values())

                taux_recouvrement = (float(montant_paye) / float(montant_prevu_annuel) * 100) if montant_prevu_annuel > 0 else 0

                # Déterminer le statut
                if montant_prevu_annuel > 0 and montant_paye >= montant_prevu_annuel:
                    statut_paiement = 'Tout payé'
                    statut_badge = 'success'
                elif montant_paye > 0:
                    statut_paiement = 'Partiellement payé'
                    statut_badge = 'warning'
                else:
                    statut_paiement = 'Non payé'
                    statut_badge = 'error'

                analyse_paiement_forfait_pe = {
                    'tarif_trimestre': tarif,
                    'montant_prevu': montant_prevu_annuel,
                    'montant_paye': montant_paye,
                    'montant_non_paye': montant_non_paye,
                    'taux_recouvrement': taux_recouvrement,
                    'qte_payee': qte_payee,
                    'qte_non_payee': qte_non_payee,
                    'trimestres': trimestres,
                    'statut_paiement': statut_paiement,
                    'statut_badge': statut_badge,
                }

            # ========== ANALYSE PAIEMENT VOLUMETRIQUE ==========
            if type_modalite in ['au_volume', 'mixte']:
                from apps.billing.models import Releve

                # Cohérence avec dashboard volume: année de facturation = mois du relevé + 1
                releves_factures = Releve.objects.filter(
                    point_eau=point,
                    montant__isnull=False,
                    montant__gt=0
                ).exclude(
                    remarque__icontains='coupé'
                )

                montant_facture_total = Decimal('0.00')
                montant_paye_volume_total = Decimal('0.00')
                nb_factures = 0

                for releve in releves_factures:
                    if not releve.datereleve:
                        continue
                    annee_facture = releve.datereleve.year + 1 if releve.datereleve.month == 12 else releve.datereleve.year
                    if annee_facture != annee_analyse:
                        continue

                    montant_facture_total += Decimal(str(releve.montant))
                    nb_factures += 1

                    if releve.numeroDiameX and str(releve.numeroDiameX).strip():
                        montant_paye_volume_total += Decimal(str(releve.montant))

                taux_paiement_volume = (float(montant_paye_volume_total) / float(montant_facture_total) * 100) if montant_facture_total > 0 else 0

                analyse_paiement_volume_pe = {
                    'nb_factures': nb_factures,
                    'montant_facture': montant_facture_total,
                    'montant_paye': montant_paye_volume_total,
                    'taux_paiement': taux_paiement_volume,
                }

            # ========== HISTORIQUE COMPLET DES RELEVES ==========
            from apps.billing.models import Releve

            # Récupérer tous les relevés du point d'eau
            historique_releves = []
            releves_qs = Releve.objects.filter(point_eau=point).order_by('-datereleve')

            for releve in releves_qs:
                montant = Decimal(str(releve.montant)) if releve.montant else Decimal('0.00')
                est_paye = bool(releve.numeroDiameX and releve.numeroDiameX.strip())

                historique_releves.append({
                    'id': str(releve.id),
                    'date': releve.datereleve.strftime('%d/%m/%Y') if releve.datereleve else '-',
                    'date_iso': releve.datereleve.strftime('%Y-%m-%d') if releve.datereleve else None,
                    'ancien_index': float(releve.ancienindex) if releve.ancienindex else 0,
                    'nouvel_index': float(releve.nouvelindex) if releve.nouvelindex else 0,
                    'consommation': float(releve.consommation) if releve.consommation else 0,
                    'volume_non_facture': float(releve.volume_non_facture) if releve.volume_non_facture else 0,
                    'volume_facture': float(releve.volume_facture) if releve.volume_facture else 0,
                    'montant': float(montant),
                    'montant_display': f"{montant:,.0f}".replace(',', ' ') + ' Ar' if montant > 0 else '-',
                    'est_paye': est_paye,
                    'numero_diamex': releve.numeroDiameX or '',
                    'base_diamex': releve.baseDiameX or '',
                    'facture_imprimee': releve.facture_imprimee,
                    'date_impression': releve.date_impression.strftime('%d/%m/%Y %H:%M') if releve.date_impression else None,
                })

            # ========== FACTURES IMPAYEES ==========
            factures_impayees = []
            total_impaye = Decimal('0.00')

            # Vérifier si l'utilisateur est un client lié Ã  ce point d'eau
            is_client_point_eau = False
            if hasattr(request.user, 'client') and request.user.client and request.user.client.point_eau_id == point.id:
                is_client_point_eau = True

            # Récupérer les factures impayées pour ce point d'eau
            factures_impayees_qs = Releve.objects.filter(
                point_eau=point,
                montant__isnull=False,
                facture_imprimee=True,
                numeroDiameX__isnull=True  # Non payé
            ).order_by('-datereleve')

            for facture in factures_impayees_qs:
                montant = Decimal(str(facture.montant)) if facture.montant else Decimal('0.00')
                total_impaye += montant
                factures_impayees.append({
                    'releve_id': str(facture.id),  # Corrigé: 'id' â†’ 'releve_id' pour correspondre au template
                    'date': facture.datereleve.strftime('%d/%m/%Y') if facture.datereleve else '-',
                    'montant': float(montant),
                    'montant_display': f"{montant:,.0f}".replace(',', ' ') + ' Ar',
                    'volume_facture': float(facture.volume_facture) if facture.volume_facture else 0,
                    'ancien_index': float(facture.ancienindex) if facture.ancienindex else 0,
                    'nouvel_index': float(facture.nouvelindex) if facture.nouvelindex else 0,
                })

            # ========== SUIVI REPARATIONS (AU NIVEAU OUVRAGE) ==========
            reparations_ouvrage = []
            if point.ouvrage:
                from apps.planning.models import ActivitePoste
                from apps.planning.views_reparations import get_repair_activities
                from apps.messaging.models import Conversation
                from django.urls import reverse

                repair_activity_ids = list(
                    get_repair_activities().values_list('id', flat=True)
                )
                repair_fiche_ids = list(
                    ActivitePoste.objects.filter(
                        activite_id__in=repair_activity_ids,
                        fiche_poste__isnull=False
                    ).values_list('fiche_poste_id', flat=True).distinct()
                )

                if repair_fiche_ids:
                    repairs_qs = Planning.objects.filter(
                        ouvrage=point.ouvrage,
                        fiche_poste_id__in=repair_fiche_ids
                    ).select_related(
                        'employe',
                        'fiche_poste'
                    ).order_by('-date')[:150]

                    for rep in repairs_qs:
                        if rep.estvalide:
                            statut_label = 'Terminee'
                            statut_badge = 'success'
                        elif rep.statut == 'annule':
                            statut_label = 'Annulee'
                            statut_badge = 'ghost'
                        elif rep.statut == 'reporte':
                            statut_label = 'Reportee'
                            statut_badge = 'warning'
                        else:
                            statut_label = 'En cours'
                            statut_badge = 'info'

                        conv = Conversation.objects.filter(
                            type='group',
                            description__startswith=f"repair_planning:{rep.id}"
                        ).first()

                        reparations_ouvrage.append({
                            'planning_id': str(rep.id),
                            'date': rep.date.strftime('%d/%m/%Y') if rep.date else '-',
                            'activite': rep.activite_display or '-',
                            'employe': rep.employe.nom_affichage if rep.employe else '-',
                            'statut_label': statut_label,
                            'statut_badge': statut_badge,
                            'remarque': rep.remarque or '-',
                            'signale_par_client': '[Signalement client]' in (rep.remarque or ''),
                            'conversation_id': conv.id if conv else None,
                            'conversation_url': reverse('messaging:conversation_detail', kwargs={'conversation_id': conv.id}) if conv else None,
                        })

            context['related_data'] = {
                'compteur': point.compteur_tete if hasattr(point, 'compteur_tete') and point.compteur_tete else None,
                'nombre_menages': point.nombre_menages_consommateurs or 0,
                'nombre_consommateurs': point.nombre_consommateurs or 0,
                # Analyses ajoutées
                'type_modalite': type_modalite,
                'annee_analyse': annee_analyse,
                'analyse_consommation': analyse_consommation_pe,
                'analyse_paiement_forfait': analyse_paiement_forfait_pe,
                'analyse_paiement_volume': analyse_paiement_volume_pe,
                # Historique des relevés
                'historique_releves': historique_releves,
                # Factures impayées (pour clients)
                'is_client_point_eau': is_client_point_eau,
                'factures_impayees': factures_impayees,
                'total_impaye': float(total_impaye),
                'total_impaye_display': f"{total_impaye:,.0f}".replace(',', ' ') + ' Ar',
                # Réparations (vision ouvrage)
                'can_signaler_reparation': bool(point.ouvrage_id),
                'reparations_ouvrage': reparations_ouvrage,
                'reparations_ouvrage_total': len(reparations_ouvrage),
            }

        elif entity_type == 'planning':
            planning = Planning.objects.select_related(
                'employe', 'ouvrage', 'type_activite', 'fiche_poste'
            ).get(id=entity_id)

            context['entity'] = {
                'type_display': 'Planning',
                'date': planning.date.strftime('%d/%m/%Y') if planning.date else '-',
                'employe': planning.employe.nom_affichage if planning.employe else '-',
                'ouvrage': planning.ouvrage.nom_ouvrage if planning.ouvrage else '-',
                'type_activite': planning.type_activite.nomtype if planning.type_activite else '-',
                'activite': planning.activite_display,
                'statut': 'Validé' if planning.estvalide else 'En attente',
                'remarque': planning.remarque or '-',
            }

            context['related_data'] = {
                'employe_obj': planning.employe,
                'ouvrage_obj': planning.ouvrage,
            }

        elif entity_type == 'equipement':
            equipement = EquipementConstitutif.objects.select_related(
                'ouvrage', 'type_equipement'
            ).get(id=entity_id)

            # Récupérer la photo si disponible
            photo_url = None
            if equipement.photos and isinstance(equipement.photos, list) and len(equipement.photos) > 0:
                first_photo = equipement.photos[0]
                if isinstance(first_photo, dict) and 'data' in first_photo:
                    photo_url = first_photo['data']

            context['entity'] = {
                'type_display': 'Equipement constitutif',
                'nom': equipement.nom,
                'code': equipement.code_equipement or '-',
                'type': equipement.type_equipement.nom_type if equipement.type_equipement else '-',
                'ouvrage': equipement.ouvrage.nom_ouvrage if equipement.ouvrage else '-',
                'description': equipement.description or '-',
                'statut': equipement.statut or '-',
                'date_installation': equipement.date_installation.strftime('%d/%m/%Y') if equipement.date_installation else '-',
                'derniere_maintenance': equipement.derniere_maintenance.strftime('%d/%m/%Y') if equipement.derniere_maintenance else '-',
                'latitude': equipement.latitude or '-',
                'longitude': equipement.longitude or '-',
                'photo_url': photo_url,
            }

            context['related_data'] = {
                'ouvrage_obj': equipement.ouvrage,
            }

        elif entity_type == 'commune':
            from django.core.paginator import Paginator
            from django.db.models import Sum
            from apps.geography.models import Parcelle

            commune = Commune.objects.select_related(
                'district__region'
            ).prefetch_related('fokontanys').get(id=entity_id)

            # Villages de la commune via les fokontany
            villages = Village.objects.filter(fokontany__commune=commune)

            # Carte de tous les villages de la commune (la liste affichee reste paginee).
            villages_total = villages.count()
            villages_map_markers = []
            for village_map in villages.values(
                'id',
                'nom_village',
                'latitude',
                'longitude',
                'fokontany__nom_fokontany',
            ):
                if village_map['latitude'] is None or village_map['longitude'] is None:
                    continue
                villages_map_markers.append({
                    'id': str(village_map['id']),
                    'latitude': float(village_map['latitude']),
                    'longitude': float(village_map['longitude']),
                    'label': village_map['nom_village'] or 'Village sans nom',
                    'detail': village_map['fokontany__nom_fokontany'] or 'Fokontany non renseigne',
                    'url': reverse('core:search_detail', args=['village', str(village_map['id'])]),
                })

            commune_map_data = {
                'markers': villages_map_markers,
                'commune_polygons': {
                    'type': 'FeatureCollection',
                    'features': [],
                },
                'counts': {
                    'total': villages_total,
                    'geolocalises': len(villages_map_markers),
                    'sans_gps': villages_total - len(villages_map_markers),
                    'communes_avec_polygone': 0,
                },
            }

            # Les limites communales sont reconstituees par union des polygones
            # des fokontany. On charge aussi les communes voisines du district
            # afin de distinguer clairement la commune selectionnee.
            try:
                import json
                from django.db import connection

                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT
                            c.id,
                            c.nom_commune,
                            ST_AsGeoJSON(
                                ST_Transform(
                                    ST_UnaryUnion(
                                        ST_Collect(
                                            ST_MakeValid(ST_SetSRID(fs.geom, 32738))
                                        )
                                    ),
                                    4326
                                )
                            ) AS geojson
                        FROM communes c
                        INNER JOIN fokontanys f ON f.commune_id = c.id
                        INNER JOIN fokontany_shp fs
                            ON LOWER(TRIM(f.nom_fokontany)) = LOWER(TRIM(fs.fokontany))
                        WHERE c.district_id = %s
                          AND fs.geom IS NOT NULL
                        GROUP BY c.id, c.nom_commune
                        ORDER BY c.nom_commune
                    """, [str(commune.district_id)])

                    commune_polygon_features = []
                    for commune_id, commune_nom, geometry_json in cursor.fetchall():
                        if not geometry_json:
                            continue
                        commune_polygon_features.append({
                            'type': 'Feature',
                            'properties': {
                                'id': str(commune_id),
                                'nom': commune_nom,
                                'selected': str(commune_id) == str(commune.id),
                            },
                            'geometry': json.loads(geometry_json),
                        })

                commune_map_data['commune_polygons']['features'] = commune_polygon_features
                commune_map_data['counts']['communes_avec_polygone'] = len(commune_polygon_features)
                commune_map_data['counts']['polygone_selectionne'] = any(
                    feature['properties']['selected']
                    for feature in commune_polygon_features
                )
            except Exception:
                # La carte des villages reste disponible si la table spatiale
                # n'est pas installee dans un environnement donne.
                commune_map_data['counts']['polygone_selectionne'] = False

            # Sans PostGIS (ex. production) : contours importés des shapefiles (ContourAdmin).
            if not commune_map_data['counts'].get('polygone_selectionne'):
                try:
                    from apps.geography.services.contours_communes import polygones_commune
                    contour_features = polygones_commune(commune)
                except Exception:
                    contour_features = []
                if contour_features:
                    commune_map_data['commune_polygons']['features'] = contour_features
                    commune_map_data['counts']['communes_avec_polygone'] = len(contour_features)
                    commune_map_data['counts']['polygone_selectionne'] = True

            # Pagination pour les villages
            page_number = request.GET.get('page', 1)
            paginator = Paginator(villages, 10)
            villages_page = paginator.get_page(page_number)

            # Points d'eau de la commune (via parcelle -> village -> fokontany -> commune)
            # SEULEMENT les points d'eau actifs (règle partagée : branchés, non coupés ni abandonnés)
            from apps.billing.points_eau_statut import q_actif
            points_eau = PointEau.objects.filter(
                q_actif(),
                parcelle__village__fokontany__commune=commune,
            )

            # Ouvrages de la commune (via points d'eau)
            # EXCLURE les types: AEPG extension, Potentiel, Travaux en cours
            ouvrages = Ouvrage.objects.filter(
                pointeau__parcelle__village__fokontany__commune=commune
            ).exclude(
                type_ouvrage__nom_type_ouvrage__in=['AEPG extension', 'Potentiel', 'Travaux en cours']
            ).distinct()

            # Statistiques des ouvrages par type
            from apps.organization.models import TypeOuvrage
            ouvrages_par_type = {}
            for type_ouvrage in TypeOuvrage.objects.all():
                # Ne pas compter les types exclus
                if type_ouvrage.nom_type_ouvrage not in ['AEPG extension', 'Potentiel', 'Travaux en cours']:
                    count = ouvrages.filter(type_ouvrage=type_ouvrage).count()
                    if count > 0:
                        ouvrages_par_type[type_ouvrage.nom_type_ouvrage] = {
                            'count': count,
                            'type_id': type_ouvrage.id
                        }

            # Points d'eau par type
            from apps.billing.models import TypePointEau
            points_par_type = {}
            for type_point in TypePointEau.objects.all():
                count = points_eau.filter(type_point_eau=type_point).count()
                if count > 0:
                    points_par_type[type_point.nom_type] = {
                        'count': count,
                        'type_id': type_point.id
                    }

            # Equipements constitutifs (via ouvrages de la commune)
            equipements = EquipementConstitutif.objects.filter(ouvrage__in=ouvrages)

            # Modalités de gestion actives (via ouvrages de la commune)
            modalites_actives = ModaliteGestion.objects.filter(
                ouvrage__in=ouvrages,
                statut='actif'
            ).select_related('gestionnaire')

            # Répartition par organisation (gestionnaire)
            repartition_organisations = {}
            for modalite in modalites_actives:
                if modalite.gestionnaire:
                    org_nom = modalite.gestionnaire.nom_organisation
                    if org_nom not in repartition_organisations:
                        repartition_organisations[org_nom] = {
                            'ouvrages': set(),
                            'points_eau': 0,
                            'habitants_desservis': 0
                        }
                    repartition_organisations[org_nom]['ouvrages'].add(modalite.ouvrage.id)

            # Compter points d'eau et habitants par organisation
            for org_nom in repartition_organisations:
                org_ouvrages = [o_id for o_id in repartition_organisations[org_nom]['ouvrages']]
                # Seulement les points d'eau actifs (branchés, non coupés ni abandonnés)
                org_points = PointEau.objects.filter(
                    q_actif(),
                    ouvrage__id__in=org_ouvrages,
                )
                repartition_organisations[org_nom]['points_eau'] = org_points.count()

                # Habitants desservis (parcelles liées Ã  ces points d'eau actifs)
                # distinct : une parcelle desservie par plusieurs points n'est comptée qu'une fois
                habitants_desservis = Parcelle.objects.filter(
                    pointeau__in=org_points
                ).distinct().aggregate(total=Sum('nombre_habitants'))['total'] or 0
                repartition_organisations[org_nom]['habitants_desservis'] = habitants_desservis
                repartition_organisations[org_nom]['ouvrages'] = len(repartition_organisations[org_nom]['ouvrages'])

            # Population totale et ménages (via villages)
            parcelles_commune = Parcelle.objects.filter(village__fokontany__commune=commune)
            population_data = parcelles_commune.aggregate(
                total_habitants=Sum('nombre_habitants'),
                total_menages=Sum('nombre_menages')
            )
            population_totale = population_data['total_habitants'] or 0
            menages_totaux = population_data['total_menages'] or 0

            # Habitants desservis (parcelles avec un point d'eau ACTIF : branché, non coupé)
            habitants_desservis = Parcelle.objects.filter(
                q_actif('pointeau__'),
                village__fokontany__commune=commune,
            ).distinct().aggregate(total=Sum('nombre_habitants'))['total'] or 0

            # ========== STATISTIQUES GRADINGS REPARATIONS ==========
            from apps.planning.grading import get_gradings_statistics
            ouvrage_ids_grading = list(ouvrages.values_list('id', flat=True))
            stats_grading_raw = get_gradings_statistics(ouvrage_ids_grading, date_reference=None)

            # Transformer pour le template (ajouter _count et _percentage)
            total_grading = stats_grading_raw.get('total', 0)
            stats_grading = {
                'A_count': stats_grading_raw.get('A', 0),
                'A_percentage': int((stats_grading_raw.get('A', 0) / total_grading * 100) if total_grading > 0 else 0),
                'B_count': stats_grading_raw.get('B', 0),
                'B_percentage': int((stats_grading_raw.get('B', 0) / total_grading * 100) if total_grading > 0 else 0),
                'B_PANNE_count': stats_grading_raw.get('B_PANNE', 0),
                'B_PANNE_percentage': int((stats_grading_raw.get('B_PANNE', 0) / total_grading * 100) if total_grading > 0 else 0),
                'D_count': stats_grading_raw.get('D', 0),
                'D_percentage': int((stats_grading_raw.get('D', 0) / total_grading * 100) if total_grading > 0 else 0),
                'D_PANNE_count': stats_grading_raw.get('D_PANNE', 0),
                'D_PANNE_percentage': int((stats_grading_raw.get('D_PANNE', 0) / total_grading * 100) if total_grading > 0 else 0),
                'total_ouvrages': total_grading,
            }

            # ========== STATISTIQUES PAIEMENTS FORFAITAIRES ==========
            # Ouvrages avec modalité forfaitaire ou mixte
            ouvrages_forfaitaires_ids = ModaliteGestion.objects.filter(
                date_fin__isnull=True,
                modalitepaiement__in=['forfaitaire', 'mixte'],
                ouvrage__pointeau__parcelle__village__fokontany__commune=commune
            ).values_list('ouvrage_id', flat=True).distinct()

            # Points d'eau forfaitaires de la commune
            points_forfaitaires = PointEau.objects.filter(
                tarifforfaitaire__isnull=False,
                ouvrage_id__in=ouvrages_forfaitaires_ids,
                parcelle__village__fokontany__commune=commune,
                datebranchement__isnull=False  # Seulement actifs
            )

            # Calculer montants prévus et payés
            from apps.billing.models import PaiementForfaitaire
            from datetime import datetime

            montant_prevu_forfait = 0
            montant_paye_forfait = 0

            # Montant prevu = somme des tarifs forfaitaires x 4 trimestres
            try:
                annee_prevu = int(request.GET.get('annee_forfait') or datetime.now().year)
            except (TypeError, ValueError):
                annee_prevu = datetime.now().year
            for point in points_forfaitaires:
                if point.tarifforfaitaire:
                    montant_prevu_forfait += float(tarif_pour_annee(point, annee_prevu)) * 4

            # Montant paye (annee selectionnee)
            annee_forfait_raw = request.GET.get('annee_forfait', '')
            try:
                annee_forfait = int(annee_forfait_raw) if annee_forfait_raw else datetime.now().year
            except (TypeError, ValueError):
                annee_forfait = datetime.now().year

            paiements_forfait_base = PaiementForfaitaire.objects.filter(
                point_eau__ouvrage_id__in=ouvrages_forfaitaires_ids,
                point_eau__parcelle__village__fokontany__commune=commune,
                date_facture__isnull=False
            )
            annees_disponibles = list(
                paiements_forfait_base.values_list('date_facture__year', flat=True)
                .distinct()
                .order_by('date_facture__year')
            )
            if not annees_disponibles:
                annees_disponibles = [annee_forfait]
            if annee_forfait not in annees_disponibles:
                annee_forfait = annees_disponibles[-1]

            paiements_forfait = paiements_forfait_base.filter(
                date_facture__year=annee_forfait
            )
            montant_paye_forfait = float(
                paiements_forfait.filter(
                    Q(paye=True) | (Q(numeroDiameX__isnull=False) & ~Q(numeroDiameX__exact=''))
                ).aggregate(total=Sum('montant'))['total'] or 0
            )

            taux_recouvrement_forfait = int((montant_paye_forfait / montant_prevu_forfait * 100) if montant_prevu_forfait > 0 else 0)

            stats_forfait = {
                'nb_points_eau': points_forfaitaires.count(),
                'nb_ouvrages': len(ouvrages_forfaitaires_ids),
                'montant_prevu': montant_prevu_forfait,
                'montant_paye': montant_paye_forfait,
                'taux_recouvrement': taux_recouvrement_forfait,
                'annee': annee_forfait,
                'annees_disponibles': annees_disponibles,
            }

            # ========== STATISTIQUES PAIEMENTS AU VOLUME ==========
            # Ouvrages avec modalité au volume
            ouvrages_volume_ids = ModaliteGestion.objects.filter(
                date_fin__isnull=True,
                modalitepaiement='au_volume',
                ouvrage__pointeau__parcelle__village__fokontany__commune=commune
            ).values_list('ouvrage_id', flat=True).distinct()

            # Points d'eau volumétriques de la commune
            points_volume = PointEau.objects.filter(
                ouvrage_id__in=ouvrages_volume_ids,
                parcelle__village__fokontany__commune=commune,
                datebranchement__isnull=False  # Seulement actifs
            )

            stats_volume = {
                'nb_points_eau': points_volume.count(),
                'nb_ouvrages': len(ouvrages_volume_ids)
            }

            # ========== AUTORITÉS RATTACHÉES ==========
            # Referentiel Autorite (Maire, Chef Fokontany, ...) vit dans apps.usagers (import
            # local pour eviter toute dependance circulaire entre apps.core et apps.usagers).
            # On remonte 3 niveaux : autorites rattachees directement Ã  la commune, celles
            # rattachees Ã  un de ses fokontany, et celles rattachees au district/region
            # englobants (affichees separement pour ne pas laisser croire qu'elles sont
            # propres Ã  la commune).
            autorites_par_niveau = _get_commune_authorities(commune)
            autorites_commune = autorites_par_niveau['commune']
            autorites_fokontany = autorites_par_niveau['fokontany']
            autorites_district = autorites_par_niveau['district']
            autorites_region = autorites_par_niveau['region']

            context['entity'] = {
                'type_display': 'Commune',
                'nom': commune.nom_commune,
                'district': commune.district.nom_district if commune.district else '-',
                'region': commune.district.region.nom_region if commune.district and commune.district.region else '-',
            }

            context['related_data'] = {
                'fokontany_count': commune.fokontanys.count(),
                'villages_count': villages_total,
                'villages_page': villages_page,
                'commune_map_data': commune_map_data,
                'ouvrages_total': ouvrages.count(),
                'ouvrages_par_type': ouvrages_par_type,
                'points_eau_total': points_eau.count(),
                'points_par_type': points_par_type,
                'equipements_total': equipements.count(),
                'modalites_actives': modalites_actives,
                'repartition_organisations': repartition_organisations,
                'population_totale': population_totale,
                'menages_totaux': menages_totaux,
                'habitants_desservis': habitants_desservis,
                # Nouvelles statistiques
                'stats_grading': stats_grading,
                'stats_forfait': stats_forfait,
                'stats_volume': stats_volume,
                # Autorites rattachees
                'autorites_commune': autorites_commune,
                'autorites_fokontany': autorites_fokontany,
                'autorites_district': autorites_district,
                'autorites_region': autorites_region,
                'autorites_total': len(autorites_commune) + len(autorites_fokontany) + len(autorites_district) + len(autorites_region),
            }

        elif entity_type == 'modalite':
            modalite = ModaliteGestion.objects.prefetch_related('ouvrage').get(id=entity_id)

            context['entity'] = {
                'type_display': 'Modalité de gestion',
                'type': modalite.type_gestion,
                'statut': modalite.statut or '-',
                'date_debut': modalite.date_debut.strftime('%d/%m/%Y') if modalite.date_debut else '-',
                'date_fin': modalite.date_fin.strftime('%d/%m/%Y') if modalite.date_fin else '-',
            }

            context['related_data'] = {
                'ouvrage': modalite.ouvrage if hasattr(modalite, 'ouvrage') else None,
            }

        elif entity_type == 'carte_sociale':
            from apps.billing.models import ConsoCarteSociale
            from django.db.models import Sum, Count
            from decimal import Decimal

            carte = CarteSociale.objects.select_related('ouvrage', 'point_eau').get(id=entity_id)

            # Récupérer les consommations de la carte sociale
            consommations = ConsoCarteSociale.objects.filter(
                carte_sociale=carte
            ).select_related('releve', 'releve__point_eau').order_by('-date', '-created_at')

            # Statistiques de consommation
            stats_conso = consommations.aggregate(
                total_bidons=Sum('quantite_bidons'),
                total_volume=Sum('volume_total'),
                total_paye=Sum('montant_paye'),
                nombre_consos=Count('id')
            )

            # Consommations avec paiement DiameX (payées)
            consos_payees = consommations.filter(numeroDiameX__isnull=False)

            # Consommations en attente de paiement
            consos_impayees = consommations.filter(numeroDiameX__isnull=True)

            context['entity'] = {
                'type_display': 'Carte sociale',
                'nom': carte.nom_beneficiaire or '-',
                'numero': carte.numero_carte or '-',
                'nombre_habitants': carte.nombre_habitants or '-',
                'date_creation': carte.date_creation.strftime('%d/%m/%Y') if carte.date_creation else '-',
                'date_expiration': carte.date_expiration.strftime('%d/%m/%Y') if carte.date_expiration else '-',
                'statut': carte.statut or '-',
                'photo_url': None,  # Les cartes sociales n'ont pas de photo dans le modèle actuel
            }

            context['related_data'] = {
                'ouvrage': carte.ouvrage if carte.ouvrage else None,
                'point_eau': carte.point_eau if carte.point_eau else None,
                'consommations': consommations[:20],  # 20 dernières consommations
                'consommations_payees': consos_payees[:10],
                'consommations_impayees': consos_impayees[:10],
                'stats_consommation': {
                    'total_bidons': int(stats_conso['total_bidons'] or 0),
                    'total_volume': float(stats_conso['total_volume'] or 0),
                    'total_paye': float(stats_conso['total_paye'] or Decimal('0')),
                    'nombre_consommations': stats_conso['nombre_consos'],
                    'nombre_payees': consos_payees.count(),
                    'nombre_impayees': consos_impayees.count(),
                },
            }

        elif entity_type == 'designation':
            from apps.planning.models import Designation
            designation = Designation.objects.select_related(
                'type_designation', 'poste_acheteur'
            ).get(id=entity_id)

            # Photo spécimen - récupérer la première photo si disponible
            photo_url = None
            if designation.photo_specimen and isinstance(designation.photo_specimen, list) and len(designation.photo_specimen) > 0:
                first_photo = designation.photo_specimen[0]
                if isinstance(first_photo, dict) and 'data' in first_photo:
                    photo_url = first_photo['data']

            # Comptes liés
            from apps.planning.models import DesignationCompte
            comptes_lies = DesignationCompte.objects.filter(
                designation=designation
            ).select_related('compte')

            # Types d'activités liés
            from apps.planning.models import DesignationTypeActivite
            types_activites = DesignationTypeActivite.objects.filter(
                designation=designation
            ).select_related('type_activite')

            context['entity'] = {
                'type_display': 'Désignation',
                'nom': designation.nom,
                'description': designation.description or '-',
                'type': designation.type_designation.nom if designation.type_designation else '-',
                'prix_unitaire': f"{designation.prix_unitaire} Ar" if designation.prix_unitaire else '-',
                'unite': designation.unite or '-',
                'code_materiel': designation.code_materiel or '-',
                'poids_unitaire': f"{designation.poids_unitaire} kg" if designation.poids_unitaire else '-',
                'seuil_minimum': designation.seuil_minimum or '-',
                'prestation': 'Oui' if designation.prestation else 'Non',
                'statut': 'Actif' if designation.actif else 'Inactif',
                'date_prix': designation.date_prix.strftime('%d/%m/%Y') if designation.date_prix else '-',
                'poste_acheteur': designation.poste_acheteur.nom_poste if designation.poste_acheteur else '-',
                'type_avance_caissiere': designation.type_avance_caissiere or '-',
                'photo_url': photo_url,
            }

            context['related_data'] = {
                'comptes_count': comptes_lies.count(),
                'comptes_lies': comptes_lies,
                'types_activites_count': types_activites.count(),
                'types_activites': types_activites,
            }

    except Exception as e:
        context['error'] = f"Erreur lors du chargement des détails: {str(e)}"

    # Personnes : bloc "Coordonnees" editable sur place + donnees liees complementaires.
    # Best-effort : un echec ici ne doit jamais empecher l'affichage de la fiche.
    if context.get('entity') and not context.get('error'):
        try:
            from apps.core.views_personnes import complements_detail, contexte_coordonnees
            context['coordonnees'] = contexte_coordonnees(request, entity_type, entity_id)
            if entity_type in ('fournisseur', 'employe'):
                complements = complements_detail(request, entity_type, entity_id)
                related = dict(context.get('related_data') or {})
                related.update({'complements': complements})
                context['related_data'] = related
        except Exception:
            pass

    return render(request, 'core/search_detail.html', context)


@login_required
@require_http_methods(["POST"])
def signaler_reparation_point_eau(request, point_id):
    """
    Crée un signalement de réparation au niveau ouvrage depuis la page détail point d'eau.
    Le signalement alimente le workflow réparation (planning + conversation).
    """
    from decimal import Decimal
    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect
    from django.urls import reverse
    from apps.planning.models import Planning, PlanningDetail, Designation, ActivitePoste
    from apps.planning.views_reparations import get_repair_activities
    from apps.messaging.repair_sync import ensure_repair_conversation
    from apps.messaging.models import Message

    point = get_object_or_404(
        PointEau.objects.select_related('ouvrage'),
        id=point_id
    )

    # Si c'est un client, il ne peut signaler que pour son propre point d'eau
    if hasattr(request.user, 'client') and request.user.client:
        if request.user.client.point_eau_id != point.id:
            messages.error(request, "Vous n'avez pas acces a ce point d'eau.")
            return redirect('core:search_detail', entity_type='point_eau', entity_id=str(point.id))

    if not point.ouvrage:
        messages.error(request, "Impossible de signaler: ce point d'eau n'est pas rattache a un ouvrage.")
        return redirect('core:search_detail', entity_type='point_eau', entity_id=str(point.id))

    description = (request.POST.get('description') or '').strip()
    urgence = (request.POST.get('urgence') or 'normale').strip().lower()
    if urgence not in {'normale', 'urgente', 'critique'}:
        urgence = 'normale'

    if not description:
        messages.error(request, "Veuillez decrire la reparation a effectuer.")
        return redirect('core:search_detail', entity_type='point_eau', entity_id=str(point.id))

    repair_activity_ids = list(get_repair_activities().values_list('id', flat=True))
    activites_postes = ActivitePoste.objects.filter(
        activite_id__in=repair_activity_ids,
        fiche_poste__isnull=False
    ).select_related('activite', 'activite__type_activite', 'fiche_poste')

    # Priorité aux activités contenant "panne" pour un signalement client
    selected_ap = (
        activites_postes.filter(activite__nom__icontains='panne').first()
        or activites_postes.first()
    )

    if not selected_ap:
        messages.error(request, "Aucune activite de reparation n'est configuree (fiche de poste manquante).")
        return redirect('core:search_detail', entity_type='point_eau', entity_id=str(point.id))

    designation = Designation.objects.filter(actif=True).order_by('nom').first()
    if not designation:
        messages.error(request, "Aucune designation active n'est disponible pour creer le signalement.")
        return redirect('core:search_detail', entity_type='point_eau', entity_id=str(point.id))

    client = getattr(request.user, 'client', None)
    declarant = client.nom_complet if client else request.user.get_username()
    actor_employe = getattr(request.user, 'employe', None)

    remarque = (
        f"[Signalement client] Urgence: {urgence}\n"
        f"Point d'eau: {point.code_point_eau or point.nomabonne or point.id}\n"
        f"Declarant: {declarant}\n"
        f"Description: {description}"
    )

    planning = Planning.objects.create(
        date=timezone.now(),
        datesignalementactivite=timezone.now(),
        estvalide=False,
        statut='en_cours',
        remarque=remarque,
        employe=actor_employe,
        type_activite=selected_ap.activite.type_activite if selected_ap.activite else None,
        fiche_poste=selected_ap.fiche_poste,
        ouvrage=point.ouvrage
    )

    PlanningDetail.objects.create(
        planning=planning,
        designation=designation,
        quantity=1,
        pu=Decimal('0.00'),
        montant=Decimal('0.00'),
        point_eau=point
    )

    conv = ensure_repair_conversation(planning, actor=actor_employe, notify=True)
    if conv:
        Message.objects.create(
            conversation=conv,
            type='system',
            expediteur=None,
            contenu=(
                f"Nouveau signalement client - Ouvrage: {point.ouvrage.nom_ouvrage}\n"
                f"Point d'eau: {point.code_point_eau or point.nomabonne}\n"
                f"Urgence: {urgence}\n"
                f"Description: {description}"
            )
        )

    messages.success(
        request,
        "Signalement envoye. Il est maintenant dans le workflow reparations et dans Conversations."
    )
    return redirect('core:search_detail', entity_type='point_eau', entity_id=str(point.id))


@require_http_methods(["GET"])
def api_ouvrages_by_modalite(request):
    """API pour récupérer les ouvrages par modalité de paiement avec filtres géographiques"""
    from apps.employees.permissions import filter_queryset_by_permissions
    from django.db.models.functions import ExtractYear

    modalite_type = request.GET.get('modalite', '')
    region_id = request.GET.get('region_id')
    district_id = request.GET.get('district_id')
    commune_id = request.GET.get('commune_id')
    fokontany_id = request.GET.get('fokontany_id')
    village_id = request.GET.get('village_id')
    organisation_id = request.GET.get('organisation_id')
    annee = request.GET.get('annee')
    type_label_raw = request.GET.get('type_label')
    type_label = _normalize_dashboard_ouvrage_type_label(type_label_raw) if type_label_raw else ''

    MODALITE_DISPLAY = {
        'forfaitaire': 'Forfaitaire',
        'au_volume': 'Au volume',
        'mixte': 'Mixte',
        'cotisation_annuelle': 'Cotisation annuelle',
        'sans_modalite': 'Sans modalité',
    }

    if modalite_type not in MODALITE_DISPLAY:
        return JsonResponse({
            'success': False,
            'error': f'Modalité invalide. Utilisez: {", ".join(MODALITE_DISPLAY.keys())}'
        }, status=400)

    try:
        points_eau_qs = filter_queryset_by_permissions(PointEau.objects.all(), request.user)
        ouvrages_qs = filter_queryset_by_permissions(
            Ouvrage.objects.filter(pointeau__isnull=False),
            request.user
        ).distinct()
        gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)

        if organisation_id and organisation_id != 'all':
            if gestionnaire_ids is not None and organisation_id not in {str(_id) for _id in gestionnaire_ids}:
                ouvrages_qs = ouvrages_qs.none()
                points_eau_qs = points_eau_qs.none()
            else:
                ouvrages_qs = filter_ouvrages_by_gestionnaire_period(
                    ouvrages_qs,
                    organisation_id,
                    annee,
                )
                points_eau_qs = points_eau_qs.filter(
                    ouvrage_id__in=ouvrages_qs.values_list('id', flat=True)
                )
        elif gestionnaire_ids is not None:
            if gestionnaire_ids:
                ouvrages_qs = filter_ouvrages_by_gestionnaire_period(
                    ouvrages_qs,
                    gestionnaire_ids,
                    annee,
                )
                points_eau_qs = points_eau_qs.filter(
                    ouvrage_id__in=ouvrages_qs.values_list('id', flat=True)
                )
            else:
                ouvrages_qs = ouvrages_qs.none()
                points_eau_qs = points_eau_qs.none()

        if annee:
            try:
                annee_int = int(annee)
                ouvrages_qs = ouvrages_qs.filter(
                    Q(annee_realisation__lte=annee_int) |
                    Q(annee_realisation__isnull=True, annee_realisation_avant__lte=annee_int)
                )
                from apps.billing.points_eau_statut import filtrer_points_annee
                points_eau_qs = filtrer_points_annee(points_eau_qs, annee_int)
            except (TypeError, ValueError):
                pass

        if village_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village_id=village_id)
            ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village_id=village_id).distinct()
        elif fokontany_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany_id=fokontany_id)
            ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village__fokontany_id=fokontany_id).distinct()
        elif commune_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany__commune_id=commune_id)
            ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village__fokontany__commune_id=commune_id).distinct()
        elif district_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany__commune__district_id=district_id)
            ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village__fokontany__commune__district_id=district_id).distinct()
        elif region_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany__commune__district__region_id=region_id)
            ouvrages_qs = ouvrages_qs.filter(
                pointeau__parcelle__village__fokontany__commune__district__region_id=region_id
            ).distinct()

        ouvrages_qs = ouvrages_qs.exclude(
            Q(type_ouvrage__nom_type_ouvrage__icontains='suspend') |
            Q(type_ouvrage__nom_type_ouvrage__icontains='potentiel')
        ).distinct()
        points_eau_qs = points_eau_qs.filter(
            ouvrage_id__in=ouvrages_qs.values_list('id', flat=True)
        )
        # Même périmètre que les tuiles « Ouvrages par modalité » : points actifs uniquement
        from hydria.views import _classer_coupes_point_ids
        coupes_ids, abandonnes_ids = _classer_coupes_point_ids(points_eau_qs, annee=annee)
        points_eau_qs = points_eau_qs.filter(datebranchement__isnull=False)
        if coupes_ids or abandonnes_ids:
            points_eau_qs = points_eau_qs.exclude(id__in=coupes_ids | abandonnes_ids)

        payment_scope = build_payment_modality_scope(points_eau_qs, annee=annee)
        ouvrages_ids_finaux = payment_scope['ouvrage_ids'][modalite_type]
        ouvrages = ouvrages_qs.filter(
            id__in=ouvrages_ids_finaux
        ).select_related('type_ouvrage').order_by('nom_ouvrage')

        modalites_info_qs = filter_modalites_by_gestionnaire_period(
            ModaliteGestion.objects.filter(ouvrage_id__in=ouvrages_ids_finaux),
            organisation_id if organisation_id and organisation_id != 'all' else gestionnaire_ids,
            annee,
        ).select_related('gestionnaire')

        modalites_by_ouvrage = {}
        for modalite in modalites_info_qs.order_by('ouvrage_id'):
            modalites_by_ouvrage.setdefault(modalite.ouvrage_id, modalite)

        ouvrages_data = []
        for ouvrage in ouvrages:
            ouvrage_type_group = _normalize_dashboard_ouvrage_type_label(
                ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else None
            )
            if type_label and ouvrage_type_group != type_label:
                continue

            modalite_info = modalites_by_ouvrage.get(ouvrage.id)
            ouvrages_data.append({
                'id': str(ouvrage.id),
                'nom': ouvrage.nom_ouvrage,
                'type_ouvrage': ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else '-',
                'type_ouvrage_groupe': ouvrage_type_group,
                'annee_realisation': ouvrage.annee_realisation or '-',
                'modalite_paiement': MODALITE_DISPLAY.get(modalite_type, modalite_type),
                'type_gestion': modalite_info.get_type_gestion_display() if modalite_info else '-',
                'nb_points_eau': points_eau_qs.filter(ouvrage=ouvrage).count(),
                'gestionnaire': modalite_info.gestionnaire.nom_organisation if modalite_info and modalite_info.gestionnaire else '-',
            })

        return JsonResponse({
            'success': True,
            'modalite': modalite_type,
            'modalite_display': MODALITE_DISPLAY.get(modalite_type, modalite_type),
            'ouvrages': ouvrages_data,
            'total': len(ouvrages_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_points_eau_by_modalite(request):
    """API pour récupérer les points d'eau par modalité de paiement avec filtres géographiques"""
    from apps.employees.permissions import filter_queryset_by_permissions
    from django.db.models.functions import ExtractYear

    modalite_type = request.GET.get('modalite', '')
    point_usage = (request.GET.get('point_usage', '') or '').strip().lower()
    region_id = request.GET.get('region_id')
    district_id = request.GET.get('district_id')
    commune_id = request.GET.get('commune_id')
    fokontany_id = request.GET.get('fokontany_id')
    village_id = request.GET.get('village_id')
    organisation_id = request.GET.get('organisation_id')
    annee = request.GET.get('annee')
    type_label_raw = request.GET.get('type_label')
    type_label = _normalize_dashboard_point_type_label(type_label_raw) if type_label_raw else ''

    MODALITE_DISPLAY = {
        'forfaitaire': 'Forfaitaire',
        'au_volume': 'Au volume',
        'mixte': 'Mixte',
        'cotisation_annuelle': 'Cotisation annuelle',
        'sans_modalite': 'Sans modalité',
    }

    if modalite_type not in MODALITE_DISPLAY:
        return JsonResponse({
            'success': False,
            'error': f'Modalité invalide. Utilisez: {", ".join(MODALITE_DISPLAY.keys())}'
        }, status=400)

    if point_usage not in {'', 'prive', 'public'}:
        return JsonResponse({
            'success': False,
            'error': 'Type de point invalide. Utilisez: prive ou public'
        }, status=400)

    try:
        points_eau_qs = filter_queryset_by_permissions(PointEau.objects.all(), request.user)
        ouvrages_qs = filter_queryset_by_permissions(
            Ouvrage.objects.filter(pointeau__isnull=False),
            request.user
        ).distinct()
        gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)

        if organisation_id and organisation_id != 'all':
            if gestionnaire_ids is not None and organisation_id not in {str(_id) for _id in gestionnaire_ids}:
                ouvrages_qs = ouvrages_qs.none()
                points_eau_qs = points_eau_qs.none()
            else:
                ouvrages_qs = filter_ouvrages_by_gestionnaire_period(
                    ouvrages_qs,
                    organisation_id,
                    annee,
                )
                points_eau_qs = points_eau_qs.filter(
                    ouvrage_id__in=ouvrages_qs.values_list('id', flat=True)
                )
        elif gestionnaire_ids is not None:
            if gestionnaire_ids:
                ouvrages_qs = filter_ouvrages_by_gestionnaire_period(
                    ouvrages_qs,
                    gestionnaire_ids,
                    annee,
                )
                points_eau_qs = points_eau_qs.filter(
                    ouvrage_id__in=ouvrages_qs.values_list('id', flat=True)
                )
            else:
                ouvrages_qs = ouvrages_qs.none()
                points_eau_qs = points_eau_qs.none()

        if annee:
            try:
                annee_int = int(annee)
                ouvrages_qs = ouvrages_qs.filter(
                    Q(annee_realisation__lte=annee_int) |
                    Q(annee_realisation__isnull=True, annee_realisation_avant__lte=annee_int)
                )
                from apps.billing.points_eau_statut import filtrer_points_annee
                points_eau_qs = filtrer_points_annee(points_eau_qs, annee_int)
            except (TypeError, ValueError):
                pass

        if village_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village_id=village_id)
            ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village_id=village_id).distinct()
        elif fokontany_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany_id=fokontany_id)
            ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village__fokontany_id=fokontany_id).distinct()
        elif commune_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany__commune_id=commune_id)
            ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village__fokontany__commune_id=commune_id).distinct()
        elif district_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany__commune__district_id=district_id)
            ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village__fokontany__commune__district_id=district_id).distinct()
        elif region_id:
            points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany__commune__district__region_id=region_id)
            ouvrages_qs = ouvrages_qs.filter(
                pointeau__parcelle__village__fokontany__commune__district__region_id=region_id
            ).distinct()

        ouvrages_qs = ouvrages_qs.exclude(
            Q(type_ouvrage__nom_type_ouvrage__icontains='suspend') |
            Q(type_ouvrage__nom_type_ouvrage__icontains='potentiel')
        ).distinct()
        points_eau_qs = points_eau_qs.filter(
            ouvrage_id__in=ouvrages_qs.values_list('id', flat=True)
        )
        # Même périmètre que les tuiles du dashboard : branchés, ni coupés ni abandonnés
        from hydria.views import _classer_coupes_point_ids
        coupes_ids, abandonnes_ids = _classer_coupes_point_ids(points_eau_qs, annee=annee)
        points_eau_qs = points_eau_qs.filter(datebranchement__isnull=False)
        if coupes_ids or abandonnes_ids:
            points_eau_qs = points_eau_qs.exclude(id__in=coupes_ids | abandonnes_ids)

        payment_breakdown = build_point_usage_modality_breakdown(points_eau_qs, annee=annee)
        payment_scope = payment_breakdown['payment_scope']
        selected_point_ids = set(payment_scope['point_ids'][modalite_type])
        if point_usage:
            selected_point_ids &= payment_breakdown['usage_point_ids'][point_usage]

        points_eau = points_eau_qs.filter(
            id__in=selected_point_ids
        ).annotate(
            type_point_eau_calcule=_dashboard_point_type_case()
        ).select_related('type_point_eau', 'ouvrage', 'parcelle__village__fokontany__commune')

        if type_label:
            points_eau = points_eau.filter(type_point_eau_calcule=type_label)

        points_data = []
        for point in points_eau:
            points_data.append({
                'id': str(point.id),
                'code': point.code_point_eau or '-',
                'nom_abonne': point.nomabonne,
                'type': point.type_point_eau_calcule or 'Sans type',
                'type_brut': point.type_point_eau.nom_type if point.type_point_eau else '-',
                'type_point_eau_id': str(point.type_point_eau_id) if point.type_point_eau_id else '',
                'typeabonne': (point.typeabonne or '').strip().lower(),
                'est_institutionnel': bool(point.estbranchementinstitutionnel),
                'ouvrage': point.ouvrage.nom_ouvrage if point.ouvrage else '-',
                'village': point.parcelle.village.nom_village if point.parcelle and point.parcelle.village else '-',
                'commune': point.parcelle.village.fokontany.commune.nom_commune if point.parcelle and point.parcelle.village and point.parcelle.village.fokontany and point.parcelle.village.fokontany.commune else '-',
                'tarif_forfaitaire': float(point.tarifforfaitaire) if point.tarifforfaitaire else None,
                'actif': point.is_active,
                'date_branchement': point.datebranchement.strftime('%d/%m/%Y') if point.datebranchement else '-',
            })

        return JsonResponse({
            'success': True,
            'modalite': modalite_type,
            'modalite_display': MODALITE_DISPLAY.get(modalite_type, modalite_type),
            'point_usage': point_usage,
            'points_eau': points_data,
            'total': len(points_data),
            # Liste des types pour le modal de modification (dashboard)
            'types_point_eau': [
                {'id': str(t_id), 'nom': t_nom}
                for t_id, t_nom in TypePointEau.objects.filter(actif=True).order_by('nom_type').values_list('id', 'nom_type')
            ],
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

