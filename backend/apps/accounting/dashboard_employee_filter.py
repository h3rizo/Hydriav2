import unicodedata

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.employees.models import EmployeOuvrages


ALLOWED_DASHBOARD_POSTES = {
    'agent de recouvrement',
    'agent de maintenance',
    'agent de recouvrement superviseur technique',
}


def calculate_water_point_score(point_ids, payment_totals_by_point):
    """Retourne un point par point d'eau dont l'exigible est payé à au moins 100 %."""
    normalized_point_ids = {str(point_id) for point_id in (point_ids or []) if point_id}
    gap_point_ids = get_water_point_score_gap_ids(
        normalized_point_ids,
        payment_totals_by_point,
    )

    points_max = len(normalized_point_ids)
    points_acquis = points_max - len(gap_point_ids)
    return {
        'points_acquis': points_acquis,
        'points_max': points_max,
        'points_ecart': len(gap_point_ids),
        'pourcentage': round((points_acquis / points_max) * 100, 1) if points_max else 0,
    }


def get_water_point_score_gap_ids(point_ids, payment_totals_by_point):
    """Identifie les points d'eau qui n'obtiennent pas leur point de score."""
    normalized_point_ids = {str(point_id) for point_id in (point_ids or []) if point_id}
    gap_point_ids = set()

    for point_id in normalized_point_ids:
        totals = payment_totals_by_point.get(point_id, {})
        montant_exigible = Decimal(str(totals.get('expected', 0) or 0))
        montant_paye = Decimal(str(totals.get('paid', 0) or 0))
        if montant_exigible <= 0 or montant_paye < montant_exigible:
            gap_point_ids.add(point_id)

    return gap_point_ids


def is_closed_payment_month(payment_date, reference_date=None):
    """Le mois d'une échéance ne compte qu'à partir du mois suivant."""
    if not payment_date:
        return False
    reference_date = reference_date or timezone.localdate()
    return payment_date.replace(day=1) < reference_date.replace(day=1)


def resolve_score_scope(
    *,
    employee_options=None,
    employee_id='',
    ouvrage_id='',
    commune_id='',
    district_id='',
    region_id='',
    organisation_id='',
    default_organisation_name='',
):
    """Détermine le libellé du périmètre le plus précis représenté par le score."""
    employee_id = str(employee_id or '').strip()
    if employee_id:
        employee_name = next((
            employee['label']
            for employee in (employee_options or [])
            if str(employee.get('id', '')) == employee_id
        ), 'Employé sélectionné')
        return {'scope_label': 'Score employé', 'scope_name': employee_name}

    lookups = (
        ('ouvrage', ouvrage_id, 'apps.organization.models', 'Ouvrage', 'nom_ouvrage'),
        ('commune', commune_id, 'apps.geography.models', 'Commune', 'nom_commune'),
        ('district', district_id, 'apps.geography.models', 'District', 'nom_district'),
        ('région', region_id, 'apps.geography.models', 'Region', 'nom_region'),
        ('organisation', organisation_id, 'apps.organization.models', 'Organisation', 'nom_organisation'),
    )
    for scope_name, selected_id, module_name, model_name, label_field in lookups:
        selected_id = str(selected_id or '').strip()
        if not selected_id or selected_id == 'all':
            continue
        module = __import__(module_name, fromlist=[model_name])
        model = getattr(module, model_name)
        label = model.objects.filter(pk=selected_id).values_list(label_field, flat=True).first()
        return {
            'scope_label': f'Score {scope_name}',
            'scope_name': label or f'{scope_name.capitalize()} sélectionné(e)',
        }

    return {
        'scope_label': 'Score organisation',
        'scope_name': default_organisation_name or 'Périmètre de l’organisation',
    }


def _normalize_poste(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(character for character in text if not unicodedata.combining(character))
    return ' '.join(text.casefold().split())


def resolve_dashboard_employee_filter(ouvrage_ids, selected_employee_id=''):
    """Construit les choix employés et filtre les ouvrages par responsabilité active."""
    scope_ids = set(ouvrage_ids or [])
    selected_employee_id = str(selected_employee_id or '').strip()
    if not scope_ids:
        return [], set() if selected_employee_id else scope_ids

    today = timezone.localdate()
    relations = EmployeOuvrages.objects.filter(
        ouvrage_id__in=scope_ids,
        date_debut__lte=today,
        employe__date_debauchage__isnull=True,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=today),
    ).select_related(
        'employe', 'employe__poste', 'employe__base',
    ).order_by('employe__nom', 'employe__prenom', 'ouvrage__nom_ouvrage')

    employees = {}
    employee_ouvrage_ids = {}
    for relation in relations:
        employee = relation.employe
        poste_name = getattr(getattr(employee, 'poste', None), 'nom_poste', '') or ''
        if _normalize_poste(poste_name) not in ALLOWED_DASHBOARD_POSTES:
            continue
        employee_id = str(employee.id)
        employee_ouvrage_ids.setdefault(employee_id, set()).add(relation.ouvrage_id)
        employees[employee_id] = employee

    options = []
    for employee_id, employee in employees.items():
        poste_name = getattr(getattr(employee, 'poste', None), 'nom_poste', '') or ''
        options.append({
            'id': employee_id,
            'label': employee.nom_affichage,
            'poste': poste_name,
            'ouvrage_count': len(employee_ouvrage_ids.get(employee_id, set())),
            'ouvrage_ids': sorted(
                str(ouvrage_id)
                for ouvrage_id in employee_ouvrage_ids.get(employee_id, set())
            ),
        })
    options.sort(key=lambda item: (item['label'].casefold(), item['poste'].casefold()))

    if selected_employee_id and selected_employee_id in employee_ouvrage_ids:
        return options, employee_ouvrage_ids[selected_employee_id]
    # Un identifiant ancien/manipulé ne doit pas vider silencieusement le
    # dashboard : il est ignoré puisqu'il ne fait pas partie des choix actifs.
    return options, scope_ids


def build_employee_geo_filter_options(
    ouvrage_ids,
    employee_options=None,
    require_forfait_tariff=True,
):
    """Construit les options Employé -> Région -> District -> Commune -> Ouvrage."""
    from django.db.models import OuterRef, Subquery

    from apps.billing.models import PointEau
    from apps.geography.models import Commune, District, Region
    from apps.organization.models import Ouvrage

    scope_ids = set(ouvrage_ids or [])
    point_filters = {'ouvrage_id__in': scope_ids}
    if require_forfait_tariff:
        point_filters['tarifforfaitaire__isnull'] = False
    points_scope = PointEau.objects.filter(**point_filters)

    employee_ids_by_ouvrage = {}
    for option in employee_options or []:
        employee_id = str(option.get('id', ''))
        for ouvrage_id in option.get('ouvrage_ids', []):
            employee_ids_by_ouvrage.setdefault(str(ouvrage_id), set()).add(employee_id)

    employee_ids_by_region = {}
    employee_ids_by_district = {}
    employee_ids_by_commune = {}
    for ouvrage_id, region_id, district_id, commune_id in points_scope.values_list(
        'ouvrage_id',
        'parcelle__village__fokontany__commune__district__region_id',
        'parcelle__village__fokontany__commune__district_id',
        'parcelle__village__fokontany__commune_id',
    ).distinct():
        for employee_id in employee_ids_by_ouvrage.get(str(ouvrage_id), set()):
            if region_id:
                employee_ids_by_region.setdefault(str(region_id), set()).add(employee_id)
            if district_id:
                employee_ids_by_district.setdefault(str(district_id), set()).add(employee_id)
            if commune_id:
                employee_ids_by_commune.setdefault(str(commune_id), set()).add(employee_id)

    region_ids = points_scope.values_list(
        'parcelle__village__fokontany__commune__district__region_id', flat=True
    ).distinct()
    district_ids = points_scope.values_list(
        'parcelle__village__fokontany__commune__district_id', flat=True
    ).distinct()
    commune_ids = points_scope.values_list(
        'parcelle__village__fokontany__commune_id', flat=True
    ).distinct()

    regions = list(Region.objects.filter(id__in=region_ids).only(
        'id', 'nom_region'
    ).order_by('nom_region'))
    districts = list(District.objects.filter(id__in=district_ids).select_related(
        'region'
    ).only(
        'id', 'nom_district', 'region_id', 'region__id', 'region__nom_region'
    ).order_by('nom_district'))
    communes = list(Commune.objects.filter(id__in=commune_ids).select_related(
        'district__region'
    ).only(
        'id', 'nom_commune', 'district_id',
        'district__id', 'district__nom_district', 'district__region_id',
        'district__region__id', 'district__region__nom_region',
    ).order_by('district__nom_district', 'nom_commune'))

    for region in regions:
        region.filter_employe_ids = ','.join(sorted(
            employee_ids_by_region.get(str(region.id), set())
        ))
    for district in districts:
        district.filter_employe_ids = ','.join(sorted(
            employee_ids_by_district.get(str(district.id), set())
        ))
    for commune in communes:
        commune.filter_employe_ids = ','.join(sorted(
            employee_ids_by_commune.get(str(commune.id), set())
        ))

    subquery_filters = {'ouvrage_id': OuterRef('pk')}
    if require_forfait_tariff:
        subquery_filters['tarifforfaitaire__isnull'] = False
    commune_subquery = PointEau.objects.filter(**subquery_filters).values(
        'parcelle__village__fokontany__commune_id'
    )[:1]
    district_subquery = PointEau.objects.filter(**subquery_filters).values(
        'parcelle__village__fokontany__commune__district_id'
    )[:1]
    region_subquery = PointEau.objects.filter(**subquery_filters).values(
        'parcelle__village__fokontany__commune__district__region_id'
    )[:1]
    ouvrages = list(Ouvrage.objects.filter(id__in=scope_ids).annotate(
        filter_commune_id=Subquery(commune_subquery),
        filter_district_id=Subquery(district_subquery),
        filter_region_id=Subquery(region_subquery),
    ).only('id', 'nom_ouvrage').order_by('nom_ouvrage'))
    for ouvrage in ouvrages:
        ouvrage.filter_employe_ids = ','.join(sorted(
            employee_ids_by_ouvrage.get(str(ouvrage.id), set())
        ))

    return regions, districts, communes, ouvrages
