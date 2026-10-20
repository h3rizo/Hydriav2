from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q, F, OuterRef, Subquery, Case, When, Value, IntegerField
from django.db.models.functions import Coalesce, Trim
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from .tarifs_forfaitaires import tarif_plein
import json
import pytz

from .models import PointEau, CompteurTete, Releve, TypePointEau, ModaliteGestion
from django.core.exceptions import ValidationError as DjangoValidationError
from .points_eau_statut import (
    STATUT_ABANDONNE, STATUT_ACTIF, STATUT_COUPE, STATUT_SANS_DATE, q_abandonne, q_actif,
    q_coupe, q_sans_date, statut_expression,
)
from apps.geography.models import Region, District, Commune
from apps.organization.models import Organisation, Ouvrage
from apps.core.models import FiltreSauvegarde

# Clé des filtres enregistrés de la page Points d'eau consolidés
PAGE_KEY_FILTRES_POINTS_EAU = 'points_eau_consolides'
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
from apps.employees.permissions import filter_queryset_by_permissions
from apps.employees.models import Employe, EmployeOuvrages, HierarchieEmploye


TARIF_FORFAITAIRE_NON_APPLICABLE_TYPES = {'bp', 'bi volume', 'kiosque'}  # « bi volume » : ancien type fusionné dans BP


def _tarif_forfaitaire_is_applicable(type_point_eau):
    type_name = getattr(type_point_eau, 'nom_type', '') or ''
    return type_name.strip().casefold() not in TARIF_FORFAITAIRE_NON_APPLICABLE_TYPES


def _point_eau_updated_by_label(point_eau):
    employe = getattr(point_eau, 'updated_by', None)
    if not employe:
        return ''
    return (
        getattr(employe, 'nom_affichage', '')
        or getattr(employe, 'nom_employe', '')
        or getattr(getattr(employe, 'user', None), 'username', '')
    )


@login_required
def billing_dashboard(request):
    context = {
        'title': 'Facturation',
        'total_clients': PointEau.objects.filter(datebranchement__isnull=False).count(),
        'total_compteurs': CompteurTete.objects.count(),
    }
    return render(request, 'billing/dashboard.html', context)


@login_required
def clients_list(request):
    clients = PointEau.objects.all().order_by('nomabonne')[:500]
    return render(request, 'billing/clients_list.html', {
        'title': 'Clients',
        'clients': clients,
    })


@login_required
def client_detail(request, pk):
    client = get_object_or_404(PointEau, pk=pk)
    return render(request, 'billing/client_detail.html', {
        'title': f'Detail - {client.nomabonne}',
        'client': client,
    })


@login_required
def compteurs_list(request):
    return redirect('organization:compteurs_releves_list')


def consolidated_points_eau(request):
    """Page consolid?e des points d'eau avec tri par r?cence, sans regroupement."""
    search_query = request.GET.get('search', '').strip()
    region_filter = request.GET.get('region', '')
    district_filter = request.GET.get('district', '')
    # Une ou plusieurs communes (filtre enregistré « 13 communes », etc.)
    commune_ids_filter = [
        value for value in request.GET.getlist('commune') if value and value not in ('all', '__multi__')
    ]
    commune_filter = commune_ids_filter[0] if len(commune_ids_filter) == 1 else (
        'multi' if commune_ids_filter else request.GET.get('commune', '')
    )
    organisation_filter = request.GET.get('organisation', '')
    ouvrage_filter = request.GET.get('ouvrage', '')
    annee_filter = request.GET.get('annee', '')
    branchement_du = request.GET.get('branchement_du', '').strip()
    branchement_au = request.GET.get('branchement_au', '').strip()
    employe_filter = request.GET.get('employe', '')
    type_point_eau_filter = request.GET.get('type_point_eau', 'all')
    tarifforfaitaire_filter = request.GET.get('tarifforfaitaire', 'all')
    missing_filter = request.GET.get('missing', 'all')
    statut_filter = request.GET.get('statut', 'all')
    # all | particulier | boutique | vide (kiosques sans type d'abonné = anomalie à corriger)
    type_abonne_filter = request.GET.get('type_abonne', 'all').strip().lower()
    print_mode = request.GET.get('print') == '1'
    result_parameters = {
        'load', 'page', 'search', 'search_columns', 'region', 'district',
        'commune', 'ouvrage', 'annee', 'branchement_du', 'branchement_au',
        'employe', 'type_point_eau', 'statut', 'organisation',
        'tarifforfaitaire', 'missing', 'print', 'export', 'type_abonne',
    }
    results_loaded = print_mode or any(
        parameter in request.GET for parameter in result_parameters
    )

    ouvrages_ids = None
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            ouvrages_ids = ModaliteGestion.objects.filter(
                date_fin__isnull=True,
                gestionnaire_id__in=gestionnaire_ids
            ).values_list('ouvrage_id', flat=True).distinct()
        else:
            ouvrages_ids = []

    points_eau = PointEau.objects.select_related(
        'parcelle__village__fokontany__commune__district__region',
        'ouvrage',
        'type_point_eau',
        'updated_by__user'
    )

    if ouvrages_ids is not None:
        points_eau = points_eau.filter(ouvrage_id__in=ouvrages_ids)

    points_eau = filter_queryset_by_permissions(points_eau, request.user)
    points_eau_scope = points_eau

    types_point_eau = TypePointEau.objects.filter(
        id__in=points_eau_scope.values('type_point_eau_id')
    ).order_by('nom_type')
    non_applicable_type_ids = [
        type_point.id for type_point in types_point_eau
        if not _tarif_forfaitaire_is_applicable(type_point)
    ]

    tarifforfaitaire_values = points_eau_scope.exclude(
        tarifforfaitaire__isnull=True
    ).exclude(
        type_point_eau_id__in=non_applicable_type_ids
    ).values_list('tarifforfaitaire', flat=True).distinct().order_by('tarifforfaitaire')
    tarifforfaitaire_options = []
    for tarif in tarifforfaitaire_values:
        tarif_float = float(tarif)
        if tarif_float.is_integer():
            tarif_label = f"{int(tarif_float):,}".replace(',', ' ')
        else:
            tarif_label = f"{tarif_float:,.2f}".replace(',', ' ').rstrip('0').rstrip('.')
        tarifforfaitaire_options.append({
            'value': str(tarif_float),
            'label': f"{tarif_label} Ar",
        })

    today = timezone.localdate()
    active_responsibilities = EmployeOuvrages.objects.filter(
        employe__date_debauchage__isnull=True,
        ouvrage_id__in=points_eau_scope.values('ouvrage_id'),
        date_debut__lte=today,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=today)
    )
    employes = Employe.objects.filter(
        date_debauchage__isnull=True,
        id__in=active_responsibilities.values('employe_id'),
    ).select_related('base', 'poste').order_by(
        'base__nom_base', 'poste__nom_poste', 'surnom', 'nom'
    )

    # Build grouped structure for dropdown: Base → Poste → employees
    _base_dict = {}
    for emp in employes:
        base_nom = emp.base.nom_base if emp.base else 'Sans base'
        poste_nom = emp.poste.nom_poste if emp.poste else 'Sans poste'
        if base_nom not in _base_dict:
            _base_dict[base_nom] = {}
        if poste_nom not in _base_dict[base_nom]:
            _base_dict[base_nom][poste_nom] = []
        _base_dict[base_nom][poste_nom].append(emp)
    employes_grouped = []
    for base_nom, postes in _base_dict.items():
        base_group = {'base': base_nom, 'postes': []}
        for poste_nom, emps in postes.items():
            base_group['postes'].append({'poste': poste_nom, 'employes': emps})
        employes_grouped.append(base_group)

    # Organisation gestionnaire de la dernière modalité de gestion active
    # (date_fin vide) de l'ouvrage du point d'eau.
    gestionnaire_actif_subquery = ModaliteGestion.objects.filter(
        ouvrage_id=OuterRef('ouvrage_id'),
        date_fin__isnull=True,
    ).order_by('-date_debut').values('gestionnaire_id')[:1]
    organisations = Organisation.objects.filter(
        id__in=points_eau_scope.annotate(
            gestionnaire_actif_id=Subquery(gestionnaire_actif_subquery)
        ).order_by().values('gestionnaire_actif_id')
    ).order_by('nom_organisation')

    search_columns = request.GET.getlist('search_columns')
    if not search_columns:
        search_columns = ['ouvrage', 'point_eau']

    if search_query:
        search_filters = Q()
        if 'region' in search_columns:
            search_filters |= Q(parcelle__village__fokontany__commune__district__region__nom_region__icontains=search_query)
        if 'district' in search_columns:
            search_filters |= Q(parcelle__village__fokontany__commune__district__nom_district__icontains=search_query)
        if 'commune' in search_columns:
            search_filters |= Q(parcelle__village__fokontany__commune__nom_commune__icontains=search_query)
        if 'ouvrage' in search_columns:
            search_filters |= Q(ouvrage__nom_ouvrage__icontains=search_query)
        if 'point_eau' in search_columns:
            search_filters |= Q(nomabonne__icontains=search_query)
        if search_filters:
            points_eau = points_eau.filter(search_filters)

    if region_filter and region_filter != 'all':
        points_eau = points_eau.filter(parcelle__village__fokontany__commune__district__region_id=region_filter)
    if district_filter and district_filter != 'all':
        points_eau = points_eau.filter(parcelle__village__fokontany__commune__district_id=district_filter)
    if commune_ids_filter:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune_id__in=commune_ids_filter)
    if ouvrage_filter and ouvrage_filter != 'all':
        points_eau = points_eau.filter(ouvrage_id=ouvrage_filter)
    if organisation_filter and organisation_filter != 'all':
        points_eau = points_eau.annotate(
            gestionnaire_actif_id=Subquery(gestionnaire_actif_subquery)
        ).filter(gestionnaire_actif_id=organisation_filter)
    if annee_filter == 'sans_date':
        points_eau = points_eau.filter(datebranchement__isnull=True)
    elif annee_filter and annee_filter != 'all':
        points_eau = points_eau.filter(datebranchement__year=annee_filter)
    # Plage de dates de branchement (bornes incluses, jours Madagascar) :
    # on compare à des datetimes aware plutôt qu'à __date pour éviter la
    # conversion de fuseau côté SQL et garder l'index utilisable.
    tz_madagascar = pytz.timezone('Indian/Antananarivo')
    branchement_range_active = False
    try:
        if branchement_du:
            debut = tz_madagascar.localize(datetime.strptime(branchement_du, '%Y-%m-%d'))
            points_eau = points_eau.filter(datebranchement__gte=debut)
            branchement_range_active = True
    except ValueError:
        branchement_du = ''
    try:
        if branchement_au:
            fin = tz_madagascar.localize(datetime.strptime(branchement_au, '%Y-%m-%d')) + timedelta(days=1)
            points_eau = points_eau.filter(datebranchement__lt=fin)
            branchement_range_active = True
    except ValueError:
        branchement_au = ''
    if type_point_eau_filter and type_point_eau_filter != 'all':
        points_eau = points_eau.filter(type_point_eau_id=type_point_eau_filter)
    if type_abonne_filter == 'vide':
        points_eau = points_eau.filter(
            Q(type_point_eau__nom_type__icontains='kiosque')
            & (Q(typeabonne__isnull=True) | Q(typeabonne__regex=r'^\s*$'))
        )
    elif type_abonne_filter in ('particulier', 'boutique'):
        points_eau = points_eau.filter(typeabonne__iexact=type_abonne_filter)
    else:
        type_abonne_filter = 'all'
    if tarifforfaitaire_filter == 'sans_tarif':
        points_eau = points_eau.filter(tarifforfaitaire__isnull=True)
    elif tarifforfaitaire_filter and tarifforfaitaire_filter != 'all':
        try:
            points_eau = points_eau.filter(tarifforfaitaire=float(tarifforfaitaire_filter))
        except (TypeError, ValueError):
            tarifforfaitaire_filter = 'all'
    if employe_filter and employe_filter != 'all':
        # Include the selected employee AND all their current active subordinates
        subordinate_ids = list(HierarchieEmploye.objects.filter(
            superieur_id=employe_filter,
            date_debut__lte=today,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=today)
        ).values_list('employe_id', flat=True))
        employe_ids = [employe_filter] + subordinate_ids
        employee_ouvrage_ids = EmployeOuvrages.objects.filter(
            employe_id__in=employe_ids,
            employe__date_debauchage__isnull=True,
            date_debut__lte=today,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=today)
        ).values('ouvrage_id')
        points_eau = points_eau.filter(ouvrage_id__in=employee_ouvrage_ids)

    if statut_filter == STATUT_ACTIF:
        points_eau = points_eau.filter(q_actif())
    elif statut_filter == STATUT_COUPE:
        points_eau = points_eau.filter(q_coupe())
    elif statut_filter == STATUT_ABANDONNE:
        points_eau = points_eau.filter(q_abandonne())
    elif statut_filter == STATUT_SANS_DATE:
        points_eau = points_eau.filter(q_sans_date())
    else:
        statut_filter = 'all'

    effective_missing_filter = missing_filter
    if print_mode and effective_missing_filter == 'all':
        effective_missing_filter = 'gps_or_name'

    points_eau = points_eau.annotate(nom_abonne_trimmed=Trim('nomabonne'))
    missing_gps = Q(latitude__isnull=True) | Q(longitude__isnull=True)
    missing_name = (
        Q(nomabonne__isnull=True)
        | Q(nom_abonne_trimmed='')
        | Q(nom_abonne_trimmed__regex=r'^\d+$')
    )
    if effective_missing_filter == 'gps':
        points_eau = points_eau.filter(missing_gps)
    elif effective_missing_filter == 'name':
        points_eau = points_eau.filter(missing_name)
    elif effective_missing_filter == 'gps_and_name':
        points_eau = points_eau.filter(missing_gps).filter(missing_name)
    elif effective_missing_filter == 'gps_or_name':
        points_eau = points_eau.filter(missing_gps | missing_name)

    # The first visit only prepares the filter choices. Expensive annotations,
    # aggregates and row hydration start after an explicit load/search action.
    if not results_loaded:
        points_eau = points_eau.none()

    modalite_active_subquery = ModaliteGestion.objects.filter(
        ouvrage_id=OuterRef('ouvrage_id'),
        date_fin__isnull=True,
    ).order_by('-date_debut').values('modalitepaiement')[:1]

    points_eau = points_eau.annotate(
        recent_activity=Coalesce('updatedat', 'createdat', 'datebranchement'),
        modalite_paiement_code=Subquery(modalite_active_subquery),
        statut_branchement=statut_expression(),
    )
    if branchement_range_active:
        # Liste des branchements de la période : ordre chronologique
        points_eau = points_eau.order_by('datebranchement', 'ouvrage__nom_ouvrage', 'nomabonne')
    else:
        # Les points sans date de branchement sont mis à part, en fin de liste
        points_eau = points_eau.annotate(
            sans_date_rang=Case(When(datebranchement__isnull=True, then=Value(1)), default=Value(0), output_field=IntegerField()),
        ).order_by(
            'sans_date_rang',
            F('recent_activity').desc(nulls_last=True),
            F('datebranchement').desc(nulls_last=True),
            '-id',
        )

    stats = points_eau.aggregate(
        total=Count('id'),
        actifs=Count('id', filter=q_actif()),
        coupes=Count('id', filter=q_coupe()),
        abandonnes=Count('id', filter=q_abandonne()),
        sans_date=Count('id', filter=q_sans_date()),
        avec_gps=Count('id', filter=Q(latitude__isnull=False, longitude__isnull=False)),
        avec_photos=Count('id', filter=Q(photos__isnull=False) & ~Q(photos=[])),
    )
    # total_points_eau = lignes listées (pagination) ; seuls les actifs comptent
    # comme points d'eau existants, coupés et sans date sont affichés à part.
    total_points_eau = stats['total']
    points_eau_actifs = stats['actifs']
    points_eau_coupes = stats['coupes']
    points_eau_abandonnes = stats['abandonnes']
    points_eau_sans_date = stats['sans_date']
    points_eau_avec_gps = stats['avec_gps']
    points_eau_sans_gps = total_points_eau - points_eau_avec_gps
    points_eau_avec_photos = stats['avec_photos']
    points_eau_sans_photos = total_points_eau - points_eau_avec_photos
    ouvrages_distincts = points_eau.values('ouvrage').distinct().count()

    # Répartition par type : points d'eau existants (actifs) uniquement
    types_stats = points_eau.filter(q_actif()).order_by().values(
        'type_point_eau__nom_type'
    ).annotate(count=Count('id')).order_by('-count')

    # Kiosques actifs par type d'abonné ; « vide » = anomalie (type d'abonné obligatoire pour un kiosque)
    kiosque_abonnes_counts = {'particulier': 0, 'boutique': 0, 'vide': 0}
    for row in points_eau.filter(
        q_actif(), type_point_eau__nom_type__icontains='kiosque'
    ).order_by().values('typeabonne').annotate(count=Count('id')):
        cle = (row['typeabonne'] or '').strip().lower()
        kiosque_abonnes_counts[cle if cle in ('particulier', 'boutique') else 'vide'] += row['count']
    kiosque_abonnes_stats = [
        {'cle': 'particulier', 'libelle': 'Particuliers', 'count': kiosque_abonnes_counts['particulier'], 'anomalie': False},
        {'cle': 'boutique', 'libelle': 'Boutiques', 'count': kiosque_abonnes_counts['boutique'], 'anomalie': False},
        {'cle': 'vide', 'libelle': "Type d'abonné manquant", 'count': kiosque_abonnes_counts['vide'], 'anomalie': True},
    ]
    kiosques_total = sum(kiosque_abonnes_counts.values())

    def build_parcelle_display(point_eau):
        parcelle = point_eau.parcelle
        if not parcelle:
            return 'Non renseignee'
        village = ''
        commune = ''
        if parcelle.village:
            village = parcelle.village.nom_village or ''
            if parcelle.village.fokontany and parcelle.village.fokontany.commune:
                commune = parcelle.village.fokontany.commune.nom_commune or ''
        location_parts = [part for part in [village, commune] if part]
        location_suffix = f" ({', '.join(location_parts)})" if location_parts else ''
        return f"{parcelle.reference_parcelle or 'Non renseignee'}{location_suffix}"

    if print_mode:
        # Trier par Commune puis Ouvrage pour permettre le regroupement dans le template imprimable
        printable_points = list(points_eau.order_by(
            'parcelle__village__fokontany__commune__nom_commune',
            'ouvrage__nom_ouvrage',
            'nomabonne',
        ))
        printable_ouvrages_count = len({
            point.ouvrage_id for point in printable_points if point.ouvrage_id
        })

        def build_parcelle_display_print(point_eau):
            """Comme build_parcelle_display, mais sans repeter la commune (deja affichee en en-tete de groupe)."""
            parcelle = point_eau.parcelle
            if not parcelle:
                return 'Non renseignee'
            village = parcelle.village.nom_village if parcelle.village and parcelle.village.nom_village else ''
            location_suffix = f" ({village})" if village else ''
            return f"{parcelle.reference_parcelle or 'Non renseignee'}{location_suffix}"

        # Regrouper sequentiellement (la liste est deja triee par commune puis ouvrage)
        commune_groups = []
        current_commune_nom = object()  # sentinelle pour forcer la creation du premier groupe
        current_commune_group = None
        current_ouvrage_nom = object()
        current_ouvrage_group = None

        for row_index, point in enumerate(printable_points, start=1):
            point.print_index = row_index
            point.parcelle_display = build_parcelle_display_print(point)
            subscriber_name = (point.nomabonne or '').strip()
            point.nom_abonne_incomplet = not subscriber_name or subscriber_name.isdigit()

            commune_obj = None
            if point.parcelle and point.parcelle.village and point.parcelle.village.fokontany:
                commune_obj = point.parcelle.village.fokontany.commune
            commune_nom = commune_obj.nom_commune if commune_obj and commune_obj.nom_commune else 'Commune non renseignée'
            ouvrage_nom = point.ouvrage.nom_ouvrage if point.ouvrage else 'Sans ouvrage'

            if commune_nom != current_commune_nom:
                current_commune_nom = commune_nom
                current_commune_group = {'nom_commune': commune_nom, 'ouvrages': [], 'count': 0}
                commune_groups.append(current_commune_group)
                current_ouvrage_nom = object()  # forcer un nouveau groupe ouvrage pour la nouvelle commune

            if ouvrage_nom != current_ouvrage_nom:
                current_ouvrage_nom = ouvrage_nom
                current_ouvrage_group = {'nom_ouvrage': ouvrage_nom, 'points': []}
                current_commune_group['ouvrages'].append(current_ouvrage_group)

            current_ouvrage_group['points'].append(point)
            current_commune_group['count'] += 1

        missing_labels = {
            'gps': 'sans coordonnees GPS',
            'name': 'sans nom abonne',
            'gps_and_name': 'sans GPS et sans nom abonne',
            'gps_or_name': 'sans GPS et/ou sans nom abonne',
        }
        employe_label = 'Tous les employés'
        if employe_filter and employe_filter != 'all':
            selected_employe = Employe.objects.filter(id=employe_filter).first()
            employe_label = selected_employe.nom_affichage if selected_employe else 'Employé non trouvé'

        commune_label = 'Toutes les communes'
        if commune_ids_filter:
            noms_communes = sorted(Commune.objects.filter(
                id__in=commune_ids_filter
            ).values_list('nom_commune', flat=True))
            commune_label = ', '.join(noms_communes) or 'Commune non trouvée'

        return render(request, 'billing/consolidated_points_eau_print.html', {
            'points_eau': printable_points,
            'commune_groups': commune_groups,
            'missing_label': missing_labels.get(effective_missing_filter, "points d'eau"),
            'employe_label': employe_label,
            'commune_label': commune_label,
            'ouvrages_count': printable_ouvrages_count,
            'points_eau_count': len(printable_points),
            'generated_at': timezone.localtime(),
        })

    # Répartition des branchements par commune (groupée région > district)
    # et par type de point d'eau, sur le jeu filtré complet (pas seulement la page).
    # Les points sans date de branchement ne sont pas des branchements : exclus.
    commune_path = 'parcelle__village__fokontany__commune'
    repartition_rows = points_eau.exclude(q_sans_date()).order_by().values(
        f'{commune_path}__district__region__nom_region',
        f'{commune_path}__district__nom_district',
        f'{commune_path}_id',
        f'{commune_path}__nom_commune',
        'ouvrage_id',
        'ouvrage__nom_ouvrage',
        'type_point_eau__nom_type',
        'statut_branchement',
    ).annotate(n=Count('id'))
    repartition_branchements = [
        {
            'region': row[f'{commune_path}__district__region__nom_region'] or 'Région non renseignée',
            'district': row[f'{commune_path}__district__nom_district'] or 'District non renseigné',
            'commune_id': str(row[f'{commune_path}_id'] or ''),
            'commune': row[f'{commune_path}__nom_commune'] or 'Commune non renseignée',
            'ouvrage_id': str(row['ouvrage_id'] or ''),
            'ouvrage': row['ouvrage__nom_ouvrage'] or 'Sans ouvrage',
            'type': row['type_point_eau__nom_type'] or 'Type non défini',
            'statut': row['statut_branchement'],
            'n': row['n'],
        }
        for row in repartition_rows
    ]

    if request.GET.get('export') == 'repartition':
        from .repartition_export import export_repartition_excel
        filtres = []
        if annee_filter == 'sans_date':
            filtres.append('sans date de branchement')
        elif annee_filter and annee_filter != 'all':
            filtres.append(f'année {annee_filter}')
        if branchement_du or branchement_au:
            fmt_date = lambda d: datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m/%Y')
            filtres.append(
                f"branchés du {fmt_date(branchement_du) if branchement_du else '…'}"
                f" au {fmt_date(branchement_au) if branchement_au else '…'}"
            )
        selected_statuts = [
            s for s in request.GET.getlist('statuts')
            if s in (STATUT_ACTIF, STATUT_COUPE, STATUT_ABANDONNE)
        ]
        if selected_statuts == [STATUT_ACTIF]:
            filtres.append('actifs uniquement')
        elif selected_statuts == [STATUT_COUPE]:
            filtres.append('coupés uniquement')
        elif selected_statuts == [STATUT_ABANDONNE]:
            filtres.append('abandonnés uniquement')
        return export_repartition_excel(
            [row for row in repartition_branchements
             if not selected_statuts or row['statut'] in selected_statuts],
            selected_types=request.GET.getlist('types'),
            filtres_description=', '.join(filtres),
        )

    paginator = Paginator(points_eau, 24)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    points_eau_list = list(page_obj.object_list)
    modalite_labels = dict(ModaliteGestion.MODALITE_PAIEMENT_CHOICES)

    for pe in points_eau_list:
        pe.modalite_paiement = modalite_labels.get(pe.modalite_paiement_code, 'Non définie')
        pe.updated_by_display = _point_eau_updated_by_label(pe)
        if pe.photos is None:
            pe.photos = []
        pe.parcelle_display = build_parcelle_display(pe)

    page_obj.object_list = points_eau_list

    points_eau_json = []
    for pe in points_eau_list:
        photos_count = len(pe.photos) if isinstance(pe.photos, list) else 0
        updated_at_value = pe.updatedat or pe.createdat or pe.datebranchement
        points_eau_json.append({
            'id': str(pe.id),
            'idxls': pe.idxls or '',
            'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'Non d?fini',
            'nom_abonne': pe.nomabonne,
            'type_label': pe.type_point_eau.nom_type if pe.type_point_eau else '-',
            'est_institutionnel': bool(pe.estbranchementinstitutionnel),
            'type_abonne': (pe.typeabonne or '').strip().lower(),
            'type_abonne_manquant': bool(
                pe.type_point_eau and 'kiosque' in (pe.type_point_eau.nom_type or '').lower()
                and not (pe.typeabonne or '').strip()
            ),
            'tarifforfaitaire_applicable': _tarif_forfaitaire_is_applicable(pe.type_point_eau),
            'parcelle_display': pe.parcelle_display,
            'actif': pe.statut_branchement == STATUT_ACTIF,
            'statut': pe.statut_branchement,
            'telephone': pe.numeroteleph or '',
            'date_branchement': pe.datebranchement.strftime('%d/%m/%Y') if pe.datebranchement else '',
            'date_branchement_input': pe.datebranchement.strftime('%Y-%m-%d') if pe.datebranchement else '',
            'besoin_cloture': bool(pe.besoin_en_cloture),
            'has_gps': bool(pe.latitude and pe.longitude),
            'photos_count': photos_count,
            'photos': pe.photos if isinstance(pe.photos, list) else [],
            'code_point_eau': pe.code_point_eau or '',
            'latitude': pe.latitude if pe.latitude is not None else '',
            'longitude': pe.longitude if pe.longitude is not None else '',
            'tarifforfaitaire': pe.tarifforfaitaire if pe.tarifforfaitaire is not None else '',
            'pourcentage_tarif': _pourcentage_json(pe.pourcentage_tarif),
            'modalite_paiement': getattr(pe, 'modalite_paiement', '') or '',
            'updated_at': updated_at_value.isoformat() if updated_at_value else '',
            'updated_by': pe.updated_by_display,
        })

    pagination_params = request.GET.copy()
    pagination_params.pop('page', None)
    pagination_query = pagination_params.urlencode()

    if ouvrages_ids is not None:
        regions_ids = points_eau_scope.order_by().values_list('parcelle__village__fokontany__commune__district__region_id', flat=True).distinct()
        districts_ids = points_eau_scope.order_by().values_list('parcelle__village__fokontany__commune__district_id', flat=True).distinct()
        communes_ids = points_eau_scope.order_by().values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()
        regions = Region.objects.filter(id__in=regions_ids).order_by('nom_region')
        districts = District.objects.filter(id__in=districts_ids).order_by('nom_district')
        communes = Commune.objects.filter(id__in=communes_ids).order_by('nom_commune')
        ouvrages = Ouvrage.objects.filter(id__in=ouvrages_ids).order_by('nom_ouvrage')
    else:
        regions = Region.objects.all().order_by('nom_region')
        districts = District.objects.all().order_by('nom_district')
        communes = Commune.objects.all().order_by('nom_commune')
        ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    annees = [
        a.year
        for a in points_eau_scope.filter(datebranchement__isnull=False).dates(
            'datebranchement', 'year', order='DESC'
        )
    ]

    context = {
        'page_obj': page_obj,
        'points_eau': page_obj,
        'search_query': search_query,
        'region_filter': region_filter,
        'district_filter': district_filter,
        'commune_filter': commune_filter,
        'commune_ids_filter': commune_ids_filter,
        'organisation_filter': organisation_filter,
        'organisations': organisations,
        'filtres_sauvegardes_data': [
            {'id': str(f.id), 'nom': f.nom, 'parametres': f.parametres}
            for f in FiltreSauvegarde.objects.filter(page_key=PAGE_KEY_FILTRES_POINTS_EAU).order_by('nom')
        ],
        'filtres_sauvegardes_page_key': PAGE_KEY_FILTRES_POINTS_EAU,
        'ouvrage_filter': ouvrage_filter,
        'annee_filter': annee_filter,
        'branchement_du': branchement_du,
        'branchement_au': branchement_au,
        'employe_filter': employe_filter,
        'type_point_eau_filter': type_point_eau_filter,
        'tarifforfaitaire_filter': tarifforfaitaire_filter,
        'type_abonne_filter': type_abonne_filter,
        'kiosque_abonnes_stats': kiosque_abonnes_stats,
        'kiosques_total': kiosques_total,
        'missing_filter': missing_filter,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'employes': employes,
        'employes_grouped': employes_grouped,
        'types_point_eau': types_point_eau,
        'tarifforfaitaire_options': tarifforfaitaire_options,
        'annees': annees,
        'total_points_eau': total_points_eau,
        'points_eau_actifs': points_eau_actifs,
        'points_eau_coupes': points_eau_coupes,
        'points_eau_abandonnes': points_eau_abandonnes,
        'points_eau_sans_date': points_eau_sans_date,
        'statut_filter': statut_filter,
        'points_eau_avec_gps': points_eau_avec_gps,
        'points_eau_sans_gps': points_eau_sans_gps,
        'points_eau_avec_photos': points_eau_avec_photos,
        'points_eau_sans_photos': points_eau_sans_photos,
        'ouvrages_distincts': ouvrages_distincts,
        'search_columns': search_columns,
        'types_stats': types_stats,
        'points_eau_json': json.dumps(points_eau_json, cls=DjangoJSONEncoder),
        # Liste complète pour le modal d'édition (types_point_eau est limité au périmètre filtré)
        'types_point_eau_modal': TypePointEau.objects.filter(actif=True).order_by('nom_type'),
        'repartition_branchements': repartition_branchements,
        'pagination_query': pagination_query,
        'page_start_index': page_obj.start_index() if total_points_eau else 0,
        'current_employe_id': getattr(getattr(request.user, 'employe', None), 'id', ''),
        'results_loaded': results_loaded,
    }
    return render(request, 'billing/consolidated_points_eau.html', context)


@login_required
def point_eau_details_api(request, point_eau_id):
    try:
        point_eau = PointEau.objects.select_related('type_point_eau', 'parcelle', 'parcelle__village', 'parcelle__village__fokontany', 'parcelle__village__fokontany__commune', 'updated_by').get(id=point_eau_id)
        type_point_eau_data = None
        if point_eau.type_point_eau:
            type_point_eau_data = {'id': str(point_eau.type_point_eau.id), 'nom_type': point_eau.type_point_eau.nom_type}
        parcelle_data = None
        if point_eau.parcelle:
            village_nom = point_eau.parcelle.village.nom_village if point_eau.parcelle.village else 'N/A'
            commune_nom = ''
            if point_eau.parcelle.village and point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune:
                commune_nom = point_eau.parcelle.village.fokontany.commune.nom_commune
            parcelle_data = {'id': str(point_eau.parcelle.id), 'reference_parcelle': point_eau.parcelle.reference_parcelle or 'N/A', 'village_nom': village_nom, 'commune_nom': commune_nom, 'display_text': f"{point_eau.parcelle.reference_parcelle or 'N/A'} - {village_nom}"}
        return JsonResponse({
            'success': True,
            'type_point_eau': type_point_eau_data,
            'typeabonne': point_eau.typeabonne,
            'est_institutionnel': bool(point_eau.estbranchementinstitutionnel),
            'parcelle': parcelle_data,
            'latitude': point_eau.latitude,
            'longitude': point_eau.longitude,
            'photos': point_eau.photos if isinstance(point_eau.photos, list) else [],
            'tarifforfaitaire': format(Decimal(str(point_eau.tarifforfaitaire)), '.2f') if point_eau.tarifforfaitaire is not None else '',
            'pourcentage_tarif': _pourcentage_json(point_eau.pourcentage_tarif),
            'tarif_plein': float(tarif_plein(point_eau.type_point_eau_id) or 0) or None,
            'tarifforfaitaire_applicable': _tarif_forfaitaire_is_applicable(point_eau.type_point_eau),
            'updated_at': point_eau.updatedat.isoformat() if point_eau.updatedat else '',
            'updated_by': _point_eau_updated_by_label(point_eau),
        })
    except PointEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': "Point d'eau introuvable"}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _pourcentage_json(valeur):
    """Pourcentage sans zéros inutiles (100.0000 -> 100), ou '' si absent."""
    if valeur is None:
        return ''
    return format(valeur.normalize(), 'f')


def _appliquer_pourcentage_post(point_eau, post):
    """Applique le pourcentage du formulaire. Vide = tarif vidé aussi (montant et % sont liés)."""
    if 'pourcentage_tarif' not in post:
        return False
    brut = (post.get('pourcentage_tarif') or '').strip().replace(',', '.')
    if not brut:
        point_eau.tarifforfaitaire = None
        point_eau.pourcentage_tarif = None
        return True
    try:
        valeur = Decimal(brut)
    except InvalidOperation:
        return False
    if valeur < 0:
        return False
    point_eau.pourcentage_tarif = valeur.quantize(Decimal('0.0001'))
    return True


def _post_bool(value):
    return str(value or '').strip().lower() in ('1', 'true', 'on', 'oui')


def _institutionnel_refuse(type_point_eau, institutionnel):
    """Message d'erreur si le branchement institutionnel est coché pour un type autre que BP, BF ou PMH."""
    if not institutionnel or not type_point_eau:
        return None
    if (type_point_eau.nom_type or '').strip().lower() in ('bp', 'bf', 'pmh'):
        return None
    return "Le branchement institutionnel n'est autorisé que pour les types BP, BF ou PMH."


@login_required
def update_point_eau_type_api(request, point_eau_id):
    """Modifie uniquement le type de point d'eau et le type d'abonné (modal du dashboard).

    Endpoint dédié : ``update_point_eau_api`` réécrit aussi « besoin de clôture » (case à cocher
    absente = faux), ce qui effacerait l'info lors d'une modification partielle.
    Règles : type d'abonné obligatoire pour un kiosque (particulier / boutique), vidé sinon ;
    tarif forfaitaire vidé si le nouveau type ne l'admet pas (BP, kiosque).
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)
    employe = getattr(request.user, 'employe', None)
    if not employe and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Réservé aux employés'}, status=403)
    try:
        point_eau = PointEau.objects.select_related('type_point_eau').get(id=point_eau_id)
    except (PointEau.DoesNotExist, DjangoValidationError, ValueError):
        return JsonResponse({'success': False, 'error': "Point d'eau introuvable"}, status=404)

    type_id = request.POST.get('type_point_eau', '').strip()
    if not type_id:
        return JsonResponse({'success': False, 'error': "Le type de point d'eau est obligatoire"}, status=400)
    try:
        nouveau_type = TypePointEau.objects.get(id=type_id)
    except (TypePointEau.DoesNotExist, DjangoValidationError, ValueError):
        return JsonResponse({'success': False, 'error': "Type de point d'eau invalide"}, status=400)

    typeabonne = request.POST.get('typeabonne', '').strip().lower()
    if (nouveau_type.nom_type or '').strip().lower() == 'kiosque':
        if typeabonne not in ('particulier', 'boutique'):
            return JsonResponse({
                'success': False,
                'error': "Le type d'abonné est obligatoire pour un kiosque (Particulier ou Boutique)",
            }, status=400)
    else:
        typeabonne = None

    point_eau.type_point_eau = nouveau_type
    point_eau.typeabonne = typeabonne
    champs = ['type_point_eau', 'typeabonne', 'updatedat']
    if 'estbranchementinstitutionnel' in request.POST:
        institutionnel = _post_bool(request.POST.get('estbranchementinstitutionnel'))
        erreur = _institutionnel_refuse(nouveau_type, institutionnel)
        if erreur:
            return JsonResponse({'success': False, 'error': erreur}, status=400)
        point_eau.estbranchementinstitutionnel = institutionnel
        champs.append('estbranchementinstitutionnel')
    if not _tarif_forfaitaire_is_applicable(nouveau_type) and point_eau.tarifforfaitaire is not None:
        point_eau.tarifforfaitaire = None
        champs.append('tarifforfaitaire')
    if employe:
        point_eau.updated_by = employe
        champs.append('updated_by')
    point_eau.updatedat = timezone.now()
    point_eau.save(update_fields=champs)
    return JsonResponse({
        'success': True,
        'type_point_eau': nouveau_type.nom_type,
        'typeabonne': point_eau.typeabonne or '',
        'tarif_vide': 'tarifforfaitaire' in champs,
    })


@login_required
def update_point_eau_api(request, point_eau_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'M?thode non autoris?e'}, status=405)
    try:
        point_eau = PointEau.objects.select_related('type_point_eau').get(id=point_eau_id)
        # Le type est appliqué en premier : tarif forfaitaire et type d'abonné en dépendent
        new_type_id = request.POST.get('type_point_eau', '').strip()
        if new_type_id:
            try:
                point_eau.type_point_eau = TypePointEau.objects.get(id=new_type_id)
            except (TypePointEau.DoesNotExist, ValueError, DjangoValidationError):
                return JsonResponse({'success': False, 'error': "Type de point d'eau invalide"}, status=400)
        if 'code_point_eau' in request.POST:
            point_eau.code_point_eau = request.POST.get('code_point_eau', '').strip() or None
        if 'nomabonne' in request.POST:
            point_eau.nomabonne = request.POST.get('nomabonne', '').strip()
        if 'idxls' in request.POST:
            point_eau.idxls = request.POST.get('idxls', '').strip() or None
        if 'numeroteleph' in request.POST:
            point_eau.numeroteleph = request.POST.get('numeroteleph', '')
        if 'datebranchement' in request.POST and request.POST.get('datebranchement'):
            try:
                point_eau.datebranchement = datetime.strptime(request.POST.get('datebranchement'), '%Y-%m-%d').date()
            except ValueError:
                pass
        if 'latitude' in request.POST and request.POST.get('latitude'):
            point_eau.latitude = float(request.POST.get('latitude'))
        if 'longitude' in request.POST and request.POST.get('longitude'):
            point_eau.longitude = float(request.POST.get('longitude'))
        point_eau.besoin_en_cloture = request.POST.get('besoin_en_cloture') == 'on'
        if 'estbranchementinstitutionnel' in request.POST:
            institutionnel = _post_bool(request.POST.get('estbranchementinstitutionnel'))
            erreur = _institutionnel_refuse(point_eau.type_point_eau, institutionnel)
            if erreur:
                return JsonResponse({'success': False, 'error': erreur}, status=400)
            point_eau.estbranchementinstitutionnel = institutionnel
        if not _tarif_forfaitaire_is_applicable(point_eau.type_point_eau):
            point_eau.tarifforfaitaire = None
        elif _appliquer_pourcentage_post(point_eau, request.POST):
            pass
        elif 'tarifforfaitaire' in request.POST:
            tarif_value = request.POST.get('tarifforfaitaire', '').strip()
            if tarif_value:
                try:
                    point_eau.tarifforfaitaire = float(tarif_value)
                except ValueError:
                    pass
            else:
                point_eau.tarifforfaitaire = None
        if 'typeabonne' in request.POST:
            typeabonne_value = request.POST.get('typeabonne', '').strip()
            type_pe_nom = point_eau.type_point_eau.nom_type.lower() if point_eau.type_point_eau else ''
            if type_pe_nom == 'kiosque':
                if typeabonne_value in ['particulier', 'boutique']:
                    point_eau.typeabonne = typeabonne_value
                else:
                    return JsonResponse({'success': False, 'error': "Le type d'abonn? est obligatoire pour un Kiosque (Particulier ou Boutique)"}, status=400)
            else:
                point_eau.typeabonne = None
        if 'parcelle_id' in request.POST:
            parcelle_id = request.POST.get('parcelle_id', '').strip()
            if parcelle_id:
                from apps.geography.models import Parcelle
                try:
                    point_eau.parcelle = Parcelle.objects.get(id=parcelle_id)
                except (Parcelle.DoesNotExist, ValueError):
                    pass
            else:
                point_eau.parcelle = None
        if hasattr(request.user, 'employe') and request.user.employe:
            point_eau.updated_by = request.user.employe
        point_eau.updatedat = timezone.now()
        if request.FILES.getlist('photos'):
            import base64
            photos_data = point_eau.photos if point_eau.photos else []
            if not isinstance(photos_data, list):
                photos_data = []
            for photo in request.FILES.getlist('photos'):
                photo_content = photo.read()
                photo_base64 = base64.b64encode(photo_content).decode('utf-8')
                photos_data.append({'filename': photo.name, 'size': photo.size, 'content_type': photo.content_type, 'data': photo_base64, 'uploaded_at': datetime.now().isoformat()})
            point_eau.photos = photos_data
        point_eau.save()
        return JsonResponse({
            'success': True,
            'message': "Point d'eau mis à jour avec succès",
            'updated_at': point_eau.updatedat.isoformat(),
            'updated_by': _point_eau_updated_by_label(point_eau),
        })
    except PointEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': "Point d'eau introuvable"}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def typepointeau_list(request):
    types = TypePointEau.objects.all().order_by('nom_type')
    return render(request, 'billing/typepointeau_list.html', {
        'title': "Types de points d'eau",
        'types': types,
    })


@login_required
def typepointeau_create(request):
    if request.method == 'POST':
        nom_type = request.POST.get('nom_type', '').strip()
        description = request.POST.get('description', '').strip()
        if not nom_type:
            messages.error(request, 'Le nom du type est obligatoire.')
        elif TypePointEau.objects.filter(nom_type__iexact=nom_type).exists():
            messages.error(request, 'Un type de point d’eau porte déjà ce nom.')
        else:
            created = TypePointEau.objects.create(
                nom_type=nom_type,
                description=description or None,
                actif=True,
            )
            messages.success(request, f'Le type « {created.nom_type} » a été créé.')
            return redirect('billing:typepointeau_list')
    return render(request, 'billing/typepointeau_form.html', {
        'title': "Nouveau type de point d'eau",
        'type_point_eau': None,
    })


@login_required
def typepointeau_detail(request, pk):
    type_point_eau = get_object_or_404(TypePointEau, pk=pk)
    points_eau = PointEau.objects.filter(type_point_eau=type_point_eau).select_related(
        'ouvrage'
    ).order_by('nomabonne')
    return render(request, 'billing/typepointeau_detail.html', {
        'title': type_point_eau.nom_type,
        'type_point_eau': type_point_eau,
        'points_eau': points_eau,
    })


@login_required
def typepointeau_edit(request, pk):
    type_point_eau = get_object_or_404(TypePointEau, pk=pk)
    if request.method == 'POST':
        nom_type = request.POST.get('nom_type', '').strip()
        description = request.POST.get('description', '').strip()
        duplicate = TypePointEau.objects.exclude(pk=pk).filter(nom_type__iexact=nom_type).exists()
        if not nom_type:
            messages.error(request, 'Le nom du type est obligatoire.')
        elif duplicate:
            messages.error(request, 'Un autre type de point d’eau porte déjà ce nom.')
        else:
            type_point_eau.nom_type = nom_type
            type_point_eau.description = description or None
            type_point_eau.actif = request.POST.get('actif') == 'on'
            type_point_eau.save()
            messages.success(request, f'Le type « {type_point_eau.nom_type} » a été modifié.')
            return redirect('billing:typepointeau_detail', pk=type_point_eau.pk)
    return render(request, 'billing/typepointeau_form.html', {
        'title': f'Modifier {type_point_eau.nom_type}',
        'type_point_eau': type_point_eau,
    })


@login_required
def typepointeau_delete(request, pk):
    type_point_eau = get_object_or_404(TypePointEau, pk=pk)
    points_eau_count = PointEau.objects.filter(type_point_eau=type_point_eau).count()
    if request.method == 'POST' and points_eau_count == 0:
        type_name = type_point_eau.nom_type
        type_point_eau.delete()
        messages.success(request, f'Le type « {type_name} » a été supprimé.')
        return redirect('billing:typepointeau_list')
    return render(request, 'billing/typepointeau_confirm_delete.html', {
        'title': f'Supprimer {type_point_eau.nom_type}',
        'type_point_eau': type_point_eau,
        'points_eau_count': points_eau_count,
    })


# ================================
# COMPOSANTS DES TYPES DE POINTS D'EAU (pages + API JSON)
# ================================

def _composant_pe_payload(composant, with_count=False):
    data = {
        'id': str(composant.id),
        'nom_composant': composant.nom_composant,
        'description': composant.description,
        'ordre_affichage': composant.ordre_affichage,
        'est_obligatoire': composant.est_obligatoire,
    }
    if with_count:
        data['points_controle_count'] = composant.points_controle_count
    return data


@login_required
def composants_type_point_eau_list(request, type_pk):
    from apps.inspections.models import ComposantTypePointEau
    type_point_eau = get_object_or_404(TypePointEau, pk=type_pk)
    composants = ComposantTypePointEau.objects.filter(
        type_point_eau=type_point_eau
    ).order_by('ordre_affichage', 'nom_composant')
    return render(request, 'billing/composants_type_point_eau_list.html', {
        'title': f'Composants - {type_point_eau.nom_type}',
        'type_point_eau': type_point_eau,
        'composants': composants,
    })


def _composant_pe_save(request, composant):
    composant.nom_composant = request.POST.get('nom_composant', '').strip()
    composant.description = request.POST.get('description', '')
    composant.ordre_affichage = int(request.POST.get('ordre_affichage') or 1)
    composant.est_obligatoire = request.POST.get('est_obligatoire') == 'on'
    composant.save()


@login_required
def composant_type_point_eau_create(request, type_pk):
    from apps.inspections.models import ComposantTypePointEau
    type_point_eau = get_object_or_404(TypePointEau, pk=type_pk)
    if request.method == 'POST':
        if request.POST.get('nom_composant', '').strip():
            composant = ComposantTypePointEau(type_point_eau=type_point_eau)
            _composant_pe_save(request, composant)
            messages.success(request, f'Composant « {composant.nom_composant} » créé.')
            return redirect('billing:composants_type_point_eau_list', type_pk=type_pk)
        messages.error(request, 'Le nom du composant est obligatoire.')
    return render(request, 'billing/composant_type_point_eau_form.html', {
        'title': f'Nouveau composant - {type_point_eau.nom_type}',
        'type_point_eau': type_point_eau,
    })


@login_required
def composant_type_point_eau_edit(request, type_pk, composant_pk):
    from apps.inspections.models import ComposantTypePointEau
    type_point_eau = get_object_or_404(TypePointEau, pk=type_pk)
    composant = get_object_or_404(ComposantTypePointEau, pk=composant_pk, type_point_eau=type_point_eau)
    if request.method == 'POST':
        if request.POST.get('nom_composant', '').strip():
            _composant_pe_save(request, composant)
            messages.success(request, f'Composant « {composant.nom_composant} » modifié.')
            return redirect('billing:composants_type_point_eau_list', type_pk=type_pk)
        messages.error(request, 'Le nom du composant est obligatoire.')
    return render(request, 'billing/composant_type_point_eau_form.html', {
        'title': f'Modifier : {composant.nom_composant}',
        'type_point_eau': type_point_eau,
        'composant': composant,
    })


@login_required
def composant_type_point_eau_delete(request, type_pk, composant_pk):
    from apps.inspections.models import ComposantTypePointEau
    type_point_eau = get_object_or_404(TypePointEau, pk=type_pk)
    composant = get_object_or_404(ComposantTypePointEau, pk=composant_pk, type_point_eau=type_point_eau)
    if request.method == 'POST':
        nom = composant.nom_composant
        composant.delete()
        messages.success(request, f'Composant « {nom} » supprimé.')
        return redirect('billing:composants_type_point_eau_list', type_pk=type_pk)
    return render(request, 'billing/composant_type_point_eau_confirm_delete.html', {
        'title': f'Supprimer : {composant.nom_composant}',
        'type_point_eau': type_point_eau,
        'composant': composant,
    })


@login_required
def api_composants_type_point_eau_list(request, type_pk):
    from apps.inspections.models import ComposantTypePointEau
    type_point_eau = get_object_or_404(TypePointEau, pk=type_pk)
    composants = ComposantTypePointEau.objects.filter(
        type_point_eau=type_point_eau
    ).annotate(
        points_controle_count=Count('points_controle')
    ).order_by('ordre_affichage', 'nom_composant')
    return JsonResponse({
        'success': True,
        'composants': [_composant_pe_payload(c, with_count=True) for c in composants],
    })


@login_required
def api_composant_type_point_eau_detail(request, type_pk, composant_pk):
    from apps.inspections.models import ComposantTypePointEau
    composant = get_object_or_404(ComposantTypePointEau, pk=composant_pk, type_point_eau_id=type_pk)
    return JsonResponse({'success': True, 'composant': _composant_pe_payload(composant)})


@login_required
def api_composant_type_point_eau_create(request, type_pk):
    from apps.inspections.models import ComposantTypePointEau
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'}, status=405)
    type_point_eau = get_object_or_404(TypePointEau, pk=type_pk)
    nom = request.POST.get('nom_composant', '').strip()
    if not nom:
        return JsonResponse({'success': False, 'message': 'Le nom du composant est obligatoire'})
    if ComposantTypePointEau.objects.filter(type_point_eau=type_point_eau, nom_composant=nom).exists():
        return JsonResponse({'success': False, 'message': 'Un composant porte déjà ce nom pour ce type'})
    try:
        composant = ComposantTypePointEau(type_point_eau=type_point_eau)
        _composant_pe_save(request, composant)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {e}'})
    return JsonResponse({
        'success': True,
        'message': f'Composant "{nom}" créé avec succès',
        'composant_id': str(composant.id),
    })


@login_required
def api_composant_type_point_eau_edit(request, type_pk, composant_pk):
    from apps.inspections.models import ComposantTypePointEau
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'}, status=405)
    composant = get_object_or_404(ComposantTypePointEau, pk=composant_pk, type_point_eau_id=type_pk)
    nom = request.POST.get('nom_composant', '').strip()
    if not nom:
        return JsonResponse({'success': False, 'message': 'Le nom du composant est obligatoire'})
    if ComposantTypePointEau.objects.filter(
        type_point_eau_id=type_pk, nom_composant=nom
    ).exclude(pk=composant.pk).exists():
        return JsonResponse({'success': False, 'message': 'Un composant porte déjà ce nom pour ce type'})
    try:
        _composant_pe_save(request, composant)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {e}'})
    return JsonResponse({'success': True, 'message': f'Composant "{nom}" modifié avec succès'})


@login_required
def api_composant_type_point_eau_delete(request, type_pk, composant_pk):
    from apps.inspections.models import ComposantTypePointEau
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'}, status=405)
    composant = get_object_or_404(ComposantTypePointEau, pk=composant_pk, type_point_eau_id=type_pk)
    nom = composant.nom_composant
    composant.delete()
    return JsonResponse({'success': True, 'message': f'Composant "{nom}" supprimé avec succès'})


@login_required
def api_points_controle_composant_list(request, composant_pk):
    from apps.inspections.models import ComposantTypePointEau, PointDeControleComposant
    composant = get_object_or_404(ComposantTypePointEau, pk=composant_pk)
    liens = PointDeControleComposant.objects.filter(
        composant_point_eau=composant
    ).select_related('point_de_controle').order_by('ordre_affichage')
    data = []
    for pcc in liens:
        pc = pcc.point_de_controle
        data.append({
            'id': str(pcc.id),
            'point_controle_id': str(pc.id),
            'nom': pc.nom,
            'description': pc.description,
            'type_resultat': pc.get_type_resultat_display(),
            'type_resultat_code': pc.type_resultat,
            'valeur_min': str(pc.valeur_min) if pc.valeur_min is not None else None,
            'valeur_max': str(pc.valeur_max) if pc.valeur_max is not None else None,
            'unite': pc.unite,
            'ordre_affichage': pcc.ordre_affichage,
            'est_obligatoire': pcc.est_obligatoire,
        })
    return JsonResponse({'success': True, 'points_controle': data})


@login_required
def api_point_controle_composant_create(request, composant_pk):
    from apps.inspections.models import ComposantTypePointEau, PointDeControle, PointDeControleComposant
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'}, status=405)
    composant = get_object_or_404(ComposantTypePointEau, pk=composant_pk)
    pc_id = request.POST.get('point_de_controle')
    if not pc_id:
        return JsonResponse({'success': False, 'message': 'Le point de contrôle est obligatoire'})
    point_controle = get_object_or_404(PointDeControle, pk=pc_id)
    if PointDeControleComposant.objects.filter(
        composant_point_eau=composant, point_de_controle=point_controle
    ).exists():
        return JsonResponse({'success': False, 'message': 'Ce point de contrôle est déjà associé à ce composant'})
    try:
        pcc = PointDeControleComposant.objects.create(
            point_de_controle=point_controle,
            composant_point_eau=composant,
            ordre_affichage=int(request.POST.get('ordre_affichage') or 1),
            est_obligatoire=request.POST.get('est_obligatoire') == 'on',
        )
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {e}'})
    return JsonResponse({
        'success': True,
        'message': f'Point de contrôle "{point_controle.nom}" ajouté avec succès',
        'point_controle_composant_id': str(pcc.id),
    })


@login_required
def api_point_controle_composant_edit(request, composant_pk, point_controle_pk):
    from apps.inspections.models import ComposantTypePointEau, PointDeControleComposant
    composant = get_object_or_404(ComposantTypePointEau, pk=composant_pk)
    pcc = get_object_or_404(PointDeControleComposant, pk=point_controle_pk, composant_point_eau=composant)
    pc = pcc.point_de_controle
    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'point_controle': {
                'id': str(pcc.id),
                'point_controle_id': str(pc.id),
                'nom': pc.nom,
                'description': pc.description,
                'type_resultat': pc.type_resultat,
                'valeur_min': float(pc.valeur_min) if pc.valeur_min is not None else None,
                'valeur_max': float(pc.valeur_max) if pc.valeur_max is not None else None,
                'unite': pc.unite,
                'ordre_affichage': pcc.ordre_affichage,
                'est_obligatoire': pcc.est_obligatoire,
            },
        })
    if request.method == 'POST':
        try:
            pcc.ordre_affichage = int(request.POST.get('ordre_affichage') or 1)
            pcc.est_obligatoire = request.POST.get('est_obligatoire') == 'on'
            pcc.save()
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erreur: {e}'})
        return JsonResponse({'success': True, 'message': f'Point de contrôle "{pc.nom}" modifié avec succès'})
    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'}, status=405)


@login_required
def api_point_controle_composant_delete(request, composant_pk, point_controle_pk):
    from apps.inspections.models import ComposantTypePointEau, PointDeControleComposant
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'}, status=405)
    composant = get_object_or_404(ComposantTypePointEau, pk=composant_pk)
    pcc = get_object_or_404(PointDeControleComposant, pk=point_controle_pk, composant_point_eau=composant)
    nom = pcc.point_de_controle.nom
    pcc.delete()
    return JsonResponse({'success': True, 'message': f'Point de contrôle "{nom}" retiré avec succès'})


def __getattr__(name):
    if name.startswith('_'):
        raise AttributeError(name)

    def _fallback_view(request, *args, **kwargs):
        return render(request, 'billing/dashboard.html', {
            'title': name.replace('_', ' ').title(),
        })

    return _fallback_view
