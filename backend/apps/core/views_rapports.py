import mimetypes
from collections import defaultdict
from decimal import Decimal
from apps.billing.tarifs_forfaitaires import tarif_pour_annee
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q, F, Min
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods
from datetime import datetime
from apps.planning.models import Planning, PlanningDetail, Activite
from apps.employees.models import Employe
from apps.organization.models import Ouvrage, Organisation
from apps.employees.permissions import employe_required, filter_queryset_by_permissions, is_visiteur
from apps.billing.models import ConsoCarteSociale, CoupureEau, PaiementForfaitaire, PointEau, Releve
from apps.geography.models import Region, District, Commune, Parcelle
from apps.planning.views_visites import (
    _build_ouvrage_stats,
    _get_filtered_ouvrages_queryset,
    _get_organisation_filter_state,
)
from apps.organization.views_grading_annuel import build_ouvrage_grading_annuel_analyse_payload
from apps.usagers.views import build_representants_avis_evolution_payload
from apps.accounting.models import BaseDiameX
from apps.accounting.views_dashboard_recettes import (
    _build_ouvrage_geo_data,
    _build_communes_breakdown,
    _compute_cartes_sociales_summary,
    _compute_forfaitaire_summary,
    _compute_volume_summary,
)
from apps.accounting.views import (
    _build_coupure_periods_by_point,
    _get_gestionnaire_organisations_for_filter,
    _get_ouvrages_ids_by_effective_gestionnaire_ids,
    _is_releve_during_coupure,
    _resolve_effective_gestionnaire_scope,
    diviser_paiement_volume_multi,
    extraire_ouvrage_et_mois_generique as extraire_ouvrage_et_mois_generique_views,
)
from apps.accounting.views_dashboard_forfaitaire import (
    _get_modalite_active_map,
    _trimestres_exigibles_depuis_date_debut,
)
from hydria.views import (
    _get_dashboard_allowed_organisation_ids,
    _resolve_dashboard_organisation_filter,
    build_dashboard_commune_ouvrages_stats_payload,
    calculate_dashboard_stats_par_commune_with_permissions,
    calculate_dashboard_stats_with_permissions,
    get_dashboard_modalites_payment_chart_payload,
)
from apps.core.models import PartnerQuarterlyReportArchive
from apps.core.partner_report_archives import (
    PartnerReportArchiveError,
    build_partner_report_archive_queryset_for_user,
    generate_partner_report_archives_for_organisation,
    get_latest_due_partner_report_quarter_spec,
    regenerate_partner_report_archive,
    regenerate_partner_report_archive_html,
)
from apps.organization.scoping import get_user_organisation


DASHBOARD_COMMUNE_NUMERIC_FIELDS = [
    'villages',
    'villages_desservis',
    'ouvrages',
    'ouvrages_forfaitaire',
    'ouvrages_volume',
    'ouvrages_mixte',
    'habitants',
    'habitants_desservis',
    'points_eau_total',
    'points_eau_prives',
    'points_eau_publics',
    'points_eau_coupes',
]

REPORT_MONTH_LABELS = [
    {'number': 1, 'label': 'Jan'},
    {'number': 2, 'label': 'Fev'},
    {'number': 3, 'label': 'Mar'},
    {'number': 4, 'label': 'Avr'},
    {'number': 5, 'label': 'Mai'},
    {'number': 6, 'label': 'Juin'},
    {'number': 7, 'label': 'Juil'},
    {'number': 8, 'label': 'Aou'},
    {'number': 9, 'label': 'Sep'},
    {'number': 10, 'label': 'Oct'},
    {'number': 11, 'label': 'Nov'},
    {'number': 12, 'label': 'Dec'},
]

PARTNER_REPORT_PRINT_GROUPS = [
    {
        'key': 'dashboard',
        'label': 'Dashboard principal',
        'icon_class': 'fas fa-chart-line',
        'items': [
            {
                'id': 'dashboard_stats',
                'label': 'Stats du dashboard',
                'description': 'Cartes statistiques geographie, points d eau, population et gestion.',
            },
            {
                'id': 'dashboard_payment_table',
                'label': 'Repartition par modalite de paiement',
                'description': 'Tableau des ouvrages et points d eau par modalite.',
            },
            {
                'id': 'dashboard_commune_table',
                'label': 'Statistiques territoriales',
                'description': 'Tableau par commune ou detail par ouvrage quand une commune est filtree.',
            },
            {
                'id': 'dashboard_points_chart',
                'label': 'Graphique modalites points d eau',
                'description': 'Barres horizontales empilees des points d eau par modalite.',
            },
            {
                'id': 'dashboard_ouvrages_chart',
                'label': 'Graphique modalites ouvrages',
                'description': 'Barres horizontales empilees des ouvrages par modalite.',
            },
        ],
    },
    {
        'key': 'visites',
        'label': 'Plannings visites',
        'icon_class': 'fas fa-route',
        'items': [
            {
                'id': 'visites_stats',
                'label': 'Stats des visites',
                'description': 'Cartes de suivi des plannings, ouvrages, actions et participants.',
            },
        ],
    },
    {
        'key': 'grading',
        'label': 'Grading annuel',
        'icon_class': 'fas fa-chart-line',
        'items': [
            {
                'id': 'grading_chart',
                'label': 'Evolution annee 1 / annee 2',
                'description': 'Graphique d evolution des gradings avec valeurs utiles uniquement.',
            },
        ],
    },
    {
        'key': 'recettes',
        'label': 'Recettes globales',
        'icon_class': 'fas fa-wallet',
        'items': [
            {
                'id': 'recettes_stats',
                'label': 'Stats des recettes',
                'description': 'Totaux prevus, payes, ecarts et nombre d ouvrages.',
            },
            {
                'id': 'recettes_workflows_table',
                'label': 'Comparaison des workflows',
                'description': 'Tableau comparatif forfaitaire, volume et cartes sociales.',
            },
            {
                'id': 'recettes_breakdown_table',
                'label': 'Repartition des recettes',
                'description': 'Tableau par commune ou detail par ouvrage quand une commune est filtree.',
            },
            {
                'id': 'recettes_volume_monthly_table',
                'label': 'Volume mensuel par ouvrage',
                'description': 'Tableau mensuel du workflow volume, disponible pour l annee en cours.',
            },
            {
                'id': 'recettes_cartes_monthly_table',
                'label': 'Cartes sociales mensuel',
                'description': 'Tableau mensuel des cartes sociales, disponible pour l annee en cours.',
            },
            {
                'id': 'recettes_forfaitaire_echu_table',
                'label': 'Forfaitaire echu par ouvrage',
                'description': 'Detail forfaitaire des ouvrages avec facture echue, disponible pour l annee en cours.',
            },
        ],
    },
    {
        'key': 'representants',
        'label': 'Evolution des representants',
        'icon_class': 'fas fa-user-check',
        'items': [
            {
                'id': 'representants_stats',
                'label': 'Stats representants',
                'description': 'Cartes representants, avis, points negatifs et satisfaction.',
            },
            {
                'id': 'representants_volume_chart',
                'label': 'Graphique volume et points negatifs',
                'description': 'Evolution annuelle du volume d avis et des points negatifs.',
            },
            {
                'id': 'representants_quality_chart',
                'label': 'Graphique taux negatif et satisfaction',
                'description': 'Evolution annuelle des indicateurs de qualite.',
            },
            {
                'id': 'representants_criteres_chart',
                'label': 'Graphique criteres negatifs',
                'description': 'Details des criteres negatifs par annee.',
            },
        ],
    },
]

PARTNER_REPORT_PRINT_OPTION_IDS = [
    item['id']
    for group in PARTNER_REPORT_PRINT_GROUPS
    for item in group['items']
]
PARTNER_REPORT_PRINT_OPTION_SET = set(PARTNER_REPORT_PRINT_OPTION_IDS)


def _build_partner_report_print_url(request):
    params = request.GET.copy()
    params['print'] = '1'
    query_string = params.urlencode()
    report_url = reverse('core:rapport_partenaires_trimestriel')
    return f'{report_url}?{query_string}' if query_string else f'{report_url}?print=1'


def _build_partner_report_print_form_fields(request):
    fields = []
    for key, values in request.GET.lists():
        if key in {'print', 'print_item'}:
            continue
        for value in values:
            fields.append({'name': key, 'value': value})
    return fields


def _normalize_partner_report_layout_config(layout_config=None):
    layout_config = layout_config if isinstance(layout_config, dict) else {}
    selected_items_supplied = 'selected_items' in layout_config
    raw_selected_items = layout_config.get('selected_items')
    raw_narratives = layout_config.get('narratives')

    normalized_selected = []
    if isinstance(raw_selected_items, (list, tuple)):
        for value in raw_selected_items:
            item_id = (value or '').strip()
            if item_id in PARTNER_REPORT_PRINT_OPTION_SET and item_id not in normalized_selected:
                normalized_selected.append(item_id)

    if not normalized_selected and not selected_items_supplied:
        normalized_selected = list(PARTNER_REPORT_PRINT_OPTION_IDS)

    normalized_narratives = {}
    raw_narratives = raw_narratives if isinstance(raw_narratives, dict) else {}
    for item_id in PARTNER_REPORT_PRINT_OPTION_IDS:
        narrative = raw_narratives.get(item_id)
        narrative = narrative if isinstance(narrative, dict) else {}
        normalized_narratives[item_id] = {
            'before': str(narrative.get('before', '') or '').strip(),
            'after': str(narrative.get('after', '') or '').strip(),
        }

    return {
        'selected_items': normalized_selected,
        'narratives': normalized_narratives,
    }


def _extract_partner_report_layout_config_from_post(post_data):
    narratives = {}
    for item_id in PARTNER_REPORT_PRINT_OPTION_IDS:
        narratives[item_id] = {
            'before': str(post_data.get(f'narrative_before__{item_id}', '') or '').strip(),
            'after': str(post_data.get(f'narrative_after__{item_id}', '') or '').strip(),
        }

    return _normalize_partner_report_layout_config(
        {
            'selected_items': post_data.getlist('print_item'),
            'narratives': narratives,
        }
    )


def _build_partner_report_print_state(request=None, selected_ids=None):
    raw_selected = []
    if selected_ids is None:
        for value in request.GET.getlist('print_item'):
            item_id = (value or '').strip()
            if item_id in PARTNER_REPORT_PRINT_OPTION_SET and item_id not in raw_selected:
                raw_selected.append(item_id)
        selected_ids = raw_selected or list(PARTNER_REPORT_PRINT_OPTION_IDS)
        has_custom_selection = bool(raw_selected)
    else:
        for value in selected_ids:
            item_id = (value or '').strip()
            if item_id in PARTNER_REPORT_PRINT_OPTION_SET and item_id not in raw_selected:
                raw_selected.append(item_id)
        selected_ids = raw_selected
        has_custom_selection = selected_ids != list(PARTNER_REPORT_PRINT_OPTION_IDS)

    selected_set = set(selected_ids)
    visibility = {}
    groups = []

    for group in PARTNER_REPORT_PRINT_GROUPS:
        group_items = []
        for item in group['items']:
            item_copy = item.copy()
            item_copy['selected'] = item['id'] in selected_set
            visibility[item['id']] = item_copy['selected']
            group_items.append(item_copy)
        groups.append(
            {
                'key': group['key'],
                'label': group['label'],
                'icon_class': group['icon_class'],
                'items': group_items,
            }
        )

    sections = {
        group['key']: any(item['selected'] for item in group['items'])
        for group in groups
    }

    return {
        'groups': groups,
        'visibility': visibility,
        'sections': sections,
        'selected_count': len(selected_ids),
        'has_custom_selection': has_custom_selection,
    }


def _build_dashboard_stat_sections(stats):
    def card(label, key, icon_class, value_class, desc='', value_format='int'):
        return {
            'label': label,
            'value': stats.get(key, 0),
            'icon_class': icon_class,
            'value_class': value_class,
            'desc': desc,
            'format': value_format,
        }

    return [
        {
            'title': 'Geographie & Infrastructure',
            'title_icon_class': 'fas fa-map-marked-alt text-info',
            'grid_classes': 'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3',
            'cards': [
                card('Communes', 'communes', 'fas fa-map-marked-alt text-info', 'text-info'),
                card('Villages', 'villages', 'fas fa-map-pin text-primary', 'text-primary'),
                card('Villages desservis', 'villages_desservis', 'fas fa-check-circle text-success', 'text-success'),
                card('Ouvrages', 'ouvrages', 'fas fa-industry text-success', 'text-success'),
                card('Equipements', 'equipements', 'fas fa-cogs text-warning', 'text-warning'),
                card('Compteurs', 'compteurs_tete', 'fas fa-tachometer-alt text-secondary', 'text-secondary'),
                card('Adresses', 'adresses', 'fas fa-map-marker-alt text-error', 'text-error'),
            ],
        },
        {
            'title': "Points d'eau",
            'title_icon_class': 'fas fa-tint text-primary',
            'grid_classes': 'grid grid-cols-2 md:grid-cols-4 gap-3',
            'cards': [
                card('Total', 'points_eau_total', 'fas fa-tint text-primary', 'text-primary'),
                card('Prives', 'points_eau_prives', 'fas fa-home text-warning', 'text-warning'),
                card('Publics', 'points_eau_publics', 'fas fa-fountain text-accent', 'text-accent'),
                card('Coupes', 'points_eau_coupes', 'fas fa-exclamation-triangle text-error', 'text-error'),
            ],
        },
        {
            'title': 'Population',
            'title_icon_class': 'fas fa-users text-secondary',
            'grid_classes': 'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3',
            'cards': [
                card('Total habitants', 'habitants', 'fas fa-users text-secondary', 'text-secondary'),
                card('Hab. desservis', 'habitants_desservis', 'fas fa-user-check text-success', 'text-success', "Avec point d'eau"),
                card('Hab. prives', 'habitants_prives', 'fas fa-user-friends text-warning', 'text-warning', '4 hab/BP'),
                card('Hab/Pt public', 'habitants_par_point_eau_public', 'fas fa-chart-line text-accent', 'text-accent', 'Moyenne', 'float1'),
                card('Hab/Pt public', 'habitants_par_point_eau_public_mediane', 'fas fa-chart-area text-secondary', 'text-secondary', 'Mediane', 'float1'),
                card('Cartes sociales', 'cartes_sociales', 'fas fa-id-card text-info', 'text-info'),
            ],
        },
        {
            'title': 'Gestion & Facturation',
            'title_icon_class': 'fas fa-coins text-warning',
            'grid_classes': 'grid grid-cols-2 md:grid-cols-3 gap-3',
            'cards': [
                card('Tarifs actifs', 'tarifs_volumetriques', 'fas fa-coins text-primary', 'text-primary'),
                card('Modalites', 'modalites_gestion', 'fas fa-handshake text-success', 'text-success'),
                card('Fournisseurs', 'fournisseurs', 'fas fa-hiking text-warning', 'text-warning'),
            ],
        },
    ]


def _build_dashboard_commune_breakdown(rows, stats):
    grouped_rows = defaultdict(list)

    for row in sorted(
        rows,
        key=lambda item: (
            (item.get('district') or '').lower(),
            (item.get('commune') or '').lower(),
        ),
    ):
        grouped_rows[row.get('district') or 'Sans district'].append(row)

    grand_totals = {key: 0 for key in DASHBOARD_COMMUNE_NUMERIC_FIELDS}
    district_groups = []

    for district_nom, district_rows in grouped_rows.items():
        district_totals = {key: 0 for key in DASHBOARD_COMMUNE_NUMERIC_FIELDS}
        normalized_rows = []

        for row in district_rows:
            normalized_row = {
                'district': district_nom,
                'commune': row.get('commune') or '-',
                'commune_id': row.get('commune_id') or '',
            }
            for key in DASHBOARD_COMMUNE_NUMERIC_FIELDS:
                value = int(row.get(key) or 0)
                normalized_row[key] = value
                district_totals[key] += value
                grand_totals[key] += value
            normalized_rows.append(normalized_row)

        district_groups.append(
            {
                'district_nom': district_nom,
                'rows': normalized_rows,
                'totals': district_totals,
            }
        )

    if stats.get('ouvrages') is not None:
        grand_totals['ouvrages'] = int(stats.get('ouvrages') or 0)

    return {
        'groups': district_groups,
        'totals': grand_totals,
    }


def _has_display_value(rows, field_name):
    for row in rows:
        value = row.get(field_name)
        if value in (None, ''):
            continue
        try:
            if Decimal(str(value)) != 0:
                return True
        except Exception:
            if bool(value):
                return True
    return False


def _build_visible_columns(rows, field_names, forced_hidden=None):
    forced_hidden = set(forced_hidden or [])
    visibility = {}
    for field_name in field_names:
        visibility[field_name] = False if field_name in forced_hidden else _has_display_value(rows, field_name)
    return visibility


def _build_dashboard_ouvrage_detail_rows(request, filter_context):
    from django.db.models.functions import ExtractYear

    organisation_id = filter_context['selected_organisation']
    region_id = filter_context['selected_region']
    district_id = filter_context['selected_district']
    commune_id = filter_context['selected_commune']
    annee = filter_context['selected_year']

    selected_commune = Commune.objects.select_related('district__region').filter(id=commune_id).first() if commune_id else None
    if selected_commune:
        payload = build_dashboard_commune_ouvrages_stats_payload(
            request.user,
            selected_commune,
            annee=annee,
            organisation_id=organisation_id,
        )
        rows = []
        for row in payload['rows']:
            modalite_paiement = row.get('modalite_paiement')
            rows.append({
                **row,
                'ouvrages': 1,
                'ouvrages_forfaitaire': 1 if modalite_paiement == 'Forfaitaire' else 0,
                'ouvrages_volume': 1 if modalite_paiement == 'Au volume' else 0,
                'ouvrages_mixte': 1 if modalite_paiement == 'Mixte' else 0,
            })

        visible_columns = _build_visible_columns(
            rows,
            (
                'villages',
                'villages_desservis',
                'ouvrages',
                'ouvrages_forfaitaire',
                'ouvrages_volume',
                'ouvrages_mixte',
                'habitants',
                'habitants_desservis',
                'points_eau_total',
                'points_eau_prives',
                'points_eau_publics',
                'points_eau_coupes',
            ),
            forced_hidden={'villages', 'villages_desservis', 'ouvrages'},
        )
        return {
            'selected_commune': payload['commune'],
            'rows': rows,
            'visible_columns': visible_columns,
            'colspan': 1 + sum(1 for is_visible in visible_columns.values() if is_visible),
        }
    if commune_id:
        return {
            'selected_commune': None,
            'rows': [],
            'visible_columns': {},
            'colspan': 1,
        }

    parcelles_qs = filter_queryset_by_permissions(Parcelle.objects.all(), request.user)
    ouvrages_qs = filter_queryset_by_permissions(
        Ouvrage.objects.filter(pointeau__isnull=False).distinct(),
        request.user,
    )
    points_eau_qs = filter_queryset_by_permissions(PointEau.objects.all(), request.user)
    selected_commune = None

    if organisation_id and organisation_id != 'all':
        ouvrages_qs = ouvrages_qs.filter(
            modalites_gestion__statut='actif',
            modalites_gestion__gestionnaire_id=organisation_id,
        ).distinct()
        points_eau_qs = points_eau_qs.filter(ouvrage_id__in=ouvrages_qs.values_list('id', flat=True))

    if annee:
        try:
            annee_int = int(annee)
            ouvrages_qs = ouvrages_qs.filter(
                Q(annee_realisation__lte=annee_int)
                | Q(annee_realisation__isnull=True, annee_realisation_avant__lte=annee_int)
            )
            points_eau_qs = points_eau_qs.annotate(
                annee_branchement=ExtractYear('datebranchement'),
                annee_arret=ExtractYear('datearretbranchement'),
            ).filter(
                Q(annee_branchement__lte=annee_int)
                & (Q(annee_arret__isnull=True) | Q(annee_arret__gte=annee_int))
            )
        except (TypeError, ValueError):
            pass

    if commune_id:
        selected_commune = Commune.objects.select_related('district__region').filter(id=commune_id).first()
        if selected_commune:
            parcelles_qs = parcelles_qs.filter(village__fokontany__commune=selected_commune)
            points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany__commune=selected_commune)
            ouvrages_qs = ouvrages_qs.filter(
                pointeau__parcelle__village__fokontany__commune=selected_commune
            ).distinct()
    elif district_id:
        district = District.objects.get(pk=district_id)
        parcelles_qs = parcelles_qs.filter(village__fokontany__commune__district=district)
        points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany__commune__district=district)
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune__district=district
        ).distinct()
    elif region_id:
        region = Region.objects.get(pk=region_id)
        parcelles_qs = parcelles_qs.filter(village__fokontany__commune__district__region=region)
        points_eau_qs = points_eau_qs.filter(parcelle__village__fokontany__commune__district__region=region)
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune__district__region=region
        ).distinct()

    ouvrages_qs = ouvrages_qs.exclude(
        Q(type_ouvrage__nom_type_ouvrage__icontains='suspend')
        | Q(type_ouvrage__nom_type_ouvrage__icontains='potentiel')
    ).order_by('nom_ouvrage')
    points_eau_qs = points_eau_qs.filter(ouvrage__in=ouvrages_qs)

    point_payment_scope = build_payment_modality_scope(points_eau_qs, annee=annee)
    ouvrages_forfaitaire_ids = {str(value) for value in point_payment_scope['ouvrage_ids']['forfaitaire']}
    ouvrages_volume_ids = {str(value) for value in point_payment_scope['ouvrage_ids']['au_volume']}
    ouvrages_mixte_ids = {str(value) for value in point_payment_scope['ouvrage_ids']['mixte']}
    points_eau_coupes_ids = _active_coupes_point_ids(points_eau_qs, annee=annee)

    ouvrages_meta = {
        str(ouvrage.id): {
            'ouvrage_id': str(ouvrage.id),
            'ouvrage': ouvrage.nom_ouvrage,
            'modalite_paiement': 'Mixte'
            if str(ouvrage.id) in ouvrages_mixte_ids
            else 'Forfaitaire'
            if str(ouvrage.id) in ouvrages_forfaitaire_ids
            else 'Au volume'
            if str(ouvrage.id) in ouvrages_volume_ids
            else 'Sans modalite',
            'villages_set': set(),
            'villages_desservis_set': set(),
            'parcelles_set': set(),
            'parcelles_desservies_set': set(),
            'points_eau_total': 0,
            'points_eau_prives': 0,
            'points_eau_publics': 0,
            'points_eau_coupes': 0,
            'ouvrages': 1,
            'ouvrages_forfaitaire': 1 if str(ouvrage.id) in ouvrages_forfaitaire_ids else 0,
            'ouvrages_volume': 1 if str(ouvrage.id) in ouvrages_volume_ids else 0,
            'ouvrages_mixte': 1 if str(ouvrage.id) in ouvrages_mixte_ids else 0,
        }
        for ouvrage in ouvrages_qs
    }

    for point in points_eau_qs.values(
        'id',
        'ouvrage_id',
        'parcelle_id',
        'parcelle__village_id',
        'datebranchement',
        'type_point_eau__nom_type',
    ):
        ouvrage_key = str(point.get('ouvrage_id'))
        if ouvrage_key not in ouvrages_meta:
            continue

        target = ouvrages_meta[ouvrage_key]
        village_id = point.get('parcelle__village_id')
        parcelle_id = point.get('parcelle_id')
        is_active = bool(point.get('datebranchement'))
        is_private = point.get('type_point_eau__nom_type') == 'BP'

        if village_id:
            target['villages_set'].add(str(village_id))
            if is_active:
                target['villages_desservis_set'].add(str(village_id))

        if parcelle_id:
            target['parcelles_set'].add(str(parcelle_id))
            if is_active:
                target['parcelles_desservies_set'].add(str(parcelle_id))

        if is_active:
            target['points_eau_total'] += 1
            if is_private:
                target['points_eau_prives'] += 1
            else:
                target['points_eau_publics'] += 1

        if point.get('id') in points_eau_coupes_ids:
            target['points_eau_coupes'] += 1

    parcelles_habitants = {
        str(row['id']): int(row['nombre_habitants'] or 0)
        for row in Parcelle.objects.filter(
            id__in={
                *[parcelle_id for item in ouvrages_meta.values() for parcelle_id in item['parcelles_set']],
                *[parcelle_id for item in ouvrages_meta.values() for parcelle_id in item['parcelles_desservies_set']],
            }
        ).values('id', 'nombre_habitants')
    }

    rows = []
    for item in ouvrages_meta.values():
        habitants = sum(parcelles_habitants.get(parcelle_id, 0) for parcelle_id in item['parcelles_set'])
        habitants_desservis = sum(
            parcelles_habitants.get(parcelle_id, 0) for parcelle_id in item['parcelles_desservies_set']
        )
        rows.append(
            {
                'ouvrage_id': item['ouvrage_id'],
                'ouvrage': item['ouvrage'],
                'modalite_paiement': item['modalite_paiement'],
                'villages': len(item['villages_set']),
                'villages_desservis': len(item['villages_desservis_set']),
                'ouvrages': item['ouvrages'],
                'ouvrages_forfaitaire': item['ouvrages_forfaitaire'],
                'ouvrages_volume': item['ouvrages_volume'],
                'ouvrages_mixte': item['ouvrages_mixte'],
                'habitants': habitants,
                'habitants_desservis': habitants_desservis,
                'points_eau_total': item['points_eau_total'],
                'points_eau_prives': item['points_eau_prives'],
                'points_eau_publics': item['points_eau_publics'],
                'points_eau_coupes': item['points_eau_coupes'],
            }
        )

    rows.sort(key=lambda row: (row.get('ouvrage') or '').lower())
    visible_columns = _build_visible_columns(
        rows,
        (
            'villages',
            'villages_desservis',
            'ouvrages',
            'ouvrages_forfaitaire',
            'ouvrages_volume',
            'ouvrages_mixte',
            'habitants',
            'habitants_desservis',
            'points_eau_total',
            'points_eau_prives',
            'points_eau_publics',
            'points_eau_coupes',
        ),
        forced_hidden={'villages', 'villages_desservis', 'ouvrages'},
    )

    return {
        'selected_commune': {
            'id': str(selected_commune.id),
            'nom': selected_commune.nom_commune,
            'district': selected_commune.district.nom_district if selected_commune and selected_commune.district else '',
            'region': (
                selected_commune.district.region.nom_region
                if selected_commune and selected_commune.district and selected_commune.district.region
                else ''
            ),
        }
        if selected_commune
        else None,
        'rows': rows,
        'visible_columns': visible_columns,
        'colspan': 1 + sum(1 for is_visible in visible_columns.values() if is_visible),
    }


def _build_recettes_ouvrage_breakdown(categories_raw):
    ouvrage_ids = set().union(*(category.get('ouvrage_ids', set()) for category in categories_raw))
    if not ouvrage_ids:
        return {'rows': [], 'visible_columns': {}, 'colspan': 1}

    ouvrages_map = {
        str(ouvrage.id): ouvrage.nom_ouvrage
        for ouvrage in Ouvrage.objects.filter(id__in=list(ouvrage_ids)).order_by('nom_ouvrage')
    }
    rows = []

    for ouvrage_id, ouvrage_nom in ouvrages_map.items():
        row = {
            'ouvrage_id': ouvrage_id,
            'ouvrage_nom': ouvrage_nom,
            'forfaitaire_prevision': Decimal('0'),
            'forfaitaire_paye': Decimal('0'),
            'volume_prevision': Decimal('0'),
            'volume_paye': Decimal('0'),
            'cartes_sociales_prevision': Decimal('0'),
            'cartes_sociales_paye': Decimal('0'),
            'total_prevu': Decimal('0'),
            'total_paye': Decimal('0'),
        }

        for category in categories_raw:
            row_data = category.get('rows_by_ouvrage', {}).get(ouvrage_id)
            if not row_data:
                continue
            prevision = Decimal(str(row_data.get('prevision') or 0))
            paye = Decimal(str(row_data.get('paye') or 0))
            row[f"{category['key']}_prevision"] += prevision
            row[f"{category['key']}_paye"] += paye
            row['total_prevu'] += prevision
            row['total_paye'] += paye

        row['ecart'] = row['total_prevu'] - row['total_paye']
        row['taux'] = int((row['total_paye'] / row['total_prevu']) * 100) if row['total_prevu'] > 0 else 0

        for field in (
            'forfaitaire_prevision',
            'forfaitaire_paye',
            'volume_prevision',
            'volume_paye',
            'cartes_sociales_prevision',
            'cartes_sociales_paye',
            'total_prevu',
            'total_paye',
            'ecart',
        ):
            row[field] = float(row[field])

        rows.append(row)

    visible_columns = _build_visible_columns(
        rows,
        (
            'forfaitaire_prevision',
            'forfaitaire_paye',
            'volume_prevision',
            'volume_paye',
            'cartes_sociales_prevision',
            'cartes_sociales_paye',
            'total_prevu',
            'total_paye',
            'ecart',
            'taux',
        ),
    )

    return {
        'rows': rows,
        'visible_columns': visible_columns,
        'colspan': 1 + sum(1 for is_visible in visible_columns.values() if is_visible),
    }


def _build_volume_monthly_workflow_table(annee, effective_gestionnaire_ids, filter_region, filter_district, filter_commune):
    releves_qs = Releve.objects.filter(
        montant__isnull=False,
        montant__gt=0,
        point_eau__ouvrage__isnull=False,
    ).filter(
        Q(datereleve__year__gte=2025) | Q(datereleve__year=2024, datereleve__month=12)
    ).exclude(
        remarque__icontains='coupe'
    ).select_related(
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune__district',
    )

    releves_filtered = []
    for releve in releves_qs:
        if not releve.datereleve:
            continue
        if releve.datereleve.year == annee:
            releves_filtered.append(releve)
            continue
        if releve.datereleve.year == (annee - 1) and releve.datereleve.month == 12:
            releves_filtered.append(releve)
    releves_qs = releves_filtered

    ouvrages_scope_ids = _get_ouvrages_ids_by_effective_gestionnaire_ids(effective_gestionnaire_ids)
    if effective_gestionnaire_ids is not None:
        releves_qs = [
            releve
            for releve in releves_qs
            if releve.point_eau and releve.point_eau.ouvrage and releve.point_eau.ouvrage.id in ouvrages_scope_ids
        ]

    if filter_region:
        releves_qs = [
            releve
            for releve in releves_qs
            if releve.point_eau
            and releve.point_eau.parcelle
            and releve.point_eau.parcelle.village
            and releve.point_eau.parcelle.village.fokontany
            and releve.point_eau.parcelle.village.fokontany.commune
            and releve.point_eau.parcelle.village.fokontany.commune.district
            and releve.point_eau.parcelle.village.fokontany.commune.district.region
            and str(releve.point_eau.parcelle.village.fokontany.commune.district.region.id) == filter_region
        ]
    if filter_district:
        releves_qs = [
            releve
            for releve in releves_qs
            if releve.point_eau
            and releve.point_eau.parcelle
            and releve.point_eau.parcelle.village
            and releve.point_eau.parcelle.village.fokontany
            and releve.point_eau.parcelle.village.fokontany.commune
            and releve.point_eau.parcelle.village.fokontany.commune.district
            and str(releve.point_eau.parcelle.village.fokontany.commune.district.id) == filter_district
        ]
    if filter_commune:
        releves_qs = [
            releve
            for releve in releves_qs
            if releve.point_eau
            and releve.point_eau.parcelle
            and releve.point_eau.parcelle.village
            and releve.point_eau.parcelle.village.fokontany
            and releve.point_eau.parcelle.village.fokontany.commune
            and str(releve.point_eau.parcelle.village.fokontany.commune.id) == filter_commune
        ]

    point_eau_ids = {str(releve.point_eau.id) for releve in releves_qs if releve.point_eau}
    periodes_coupure = _build_coupure_periods_by_point(point_eau_ids)
    releves_qs = [
        releve
        for releve in releves_qs
        if not _is_releve_during_coupure(releve, periodes_coupure, check_facturation_month=True)
    ]

    recouvrement_par_ouvrage_mois = {}
    recouvrement_par_ouvrage_annee = {}
    pointed_pairs_par_cle_mois = {}

    def _pair_key(numero_diamex, base_diamex):
        num = str(numero_diamex or '').strip().lower()
        base = str(base_diamex or '').strip().lower()
        if not num or not base:
            return ''
        return f'{num}||{base}'

    for releve in releves_qs:
        if not releve.point_eau or not releve.point_eau.ouvrage:
            continue

        ouvrage = releve.point_eau.ouvrage
        ouvrage_id = str(ouvrage.id)
        district_nom = 'Sans district'
        if releve.point_eau.parcelle and releve.point_eau.parcelle.village:
            village = releve.point_eau.parcelle.village
            if village.fokontany and village.fokontany.commune and village.fokontany.commune.district:
                district_nom = village.fokontany.commune.district.nom_district

        mois_source = releve.datereleve.month
        if mois_source == 12:
            mois = 1
            annee_cible = releve.datereleve.year + 1
        else:
            mois = mois_source + 1
            annee_cible = releve.datereleve.year
        if annee_cible != annee:
            continue

        cle_mois = f'{ouvrage_id}_{annee}_{mois:02d}'
        recouvrement_par_ouvrage_mois.setdefault(
            cle_mois,
            {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage.nom_ouvrage,
                'district_nom': district_nom,
                'mois': mois,
                'total_releves': Decimal('0'),
                'total_diamex': Decimal('0'),
                'nb_releves': 0,
                'montant_non_pointe_releve': Decimal('0'),
                'montant_non_pointe_compta': Decimal('0'),
                'nb_non_pointe_releve': 0,
                'nb_non_pointe_compta': 0,
            },
        )
        pointed_pairs_par_cle_mois.setdefault(cle_mois, set())

        montant = Decimal(str(releve.montant or 0))
        recouvrement_par_ouvrage_mois[cle_mois]['total_releves'] += montant
        recouvrement_par_ouvrage_mois[cle_mois]['nb_releves'] += 1

        pair_value = _pair_key(releve.numeroDiameX, releve.baseDiameX)
        if pair_value:
            pointed_pairs_par_cle_mois[cle_mois].add(pair_value)
        else:
            recouvrement_par_ouvrage_mois[cle_mois]['montant_non_pointe_compta'] += montant
            recouvrement_par_ouvrage_mois[cle_mois]['nb_non_pointe_compta'] += 1

        recouvrement_par_ouvrage_annee.setdefault(
            ouvrage_id,
            {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage.nom_ouvrage,
                'district_nom': district_nom,
                'total_diamex': Decimal('0'),
            },
        )

    ouvrages_filtres_ids = {
        str(releve.point_eau.ouvrage.id)
        for releve in releves_qs
        if releve.point_eau and releve.point_eau.ouvrage
    }

    for entry in BaseDiameX.objects.filter(compte_code='707401'):
        segments = []
        if entry.description and ';' in entry.description:
            segments = diviser_paiement_volume_multi(
                entry.description,
                entry.compte_code,
                entry.montant_in if entry.montant_in else 0,
            )

        if segments:
            extracted_items = [
                (
                    segment['extraction'].get('ouvrage_obj'),
                    segment['extraction'].get('mois'),
                    segment['extraction'].get('annee'),
                    Decimal(str(segment['montant'])),
                )
                for segment in segments
            ]
        else:
            extraction = extraire_ouvrage_et_mois_generique_views(entry.description or '', entry.compte_code)
            extracted_items = [
                (
                    extraction.get('ouvrage_obj'),
                    extraction.get('mois'),
                    extraction.get('annee'),
                    Decimal(str(entry.montant_in or 0)),
                )
            ]

        for ouvrage_obj, mois, annee_entry, montant_value in extracted_items:
            if not ouvrage_obj or not mois or annee_entry != annee:
                continue
            ouvrage_id = str(ouvrage_obj.id)
            if ouvrage_id not in ouvrages_filtres_ids:
                continue

            district_nom = recouvrement_par_ouvrage_annee.get(ouvrage_id, {}).get('district_nom', 'Sans district')
            cle_mois = f'{ouvrage_id}_{annee}_{mois:02d}'
            recouvrement_par_ouvrage_mois.setdefault(
                cle_mois,
                {
                    'ouvrage_id': ouvrage_id,
                    'ouvrage_nom': ouvrage_obj.nom_ouvrage,
                    'district_nom': district_nom,
                    'mois': mois,
                    'total_releves': Decimal('0'),
                    'total_diamex': Decimal('0'),
                    'nb_releves': 0,
                    'montant_non_pointe_releve': Decimal('0'),
                    'montant_non_pointe_compta': Decimal('0'),
                    'nb_non_pointe_releve': 0,
                    'nb_non_pointe_compta': 0,
                },
            )
            pointed_pairs_par_cle_mois.setdefault(cle_mois, set())
            recouvrement_par_ouvrage_mois[cle_mois]['total_diamex'] += montant_value

            diamex_pair_key = _pair_key(entry.id_access, entry.prog)
            is_diamex_pointe = bool(
                diamex_pair_key and diamex_pair_key in pointed_pairs_par_cle_mois.get(cle_mois, set())
            )
            if not is_diamex_pointe:
                recouvrement_par_ouvrage_mois[cle_mois]['montant_non_pointe_releve'] += montant_value
                recouvrement_par_ouvrage_mois[cle_mois]['nb_non_pointe_releve'] += 1

            recouvrement_par_ouvrage_annee.setdefault(
                ouvrage_id,
                {
                    'ouvrage_id': ouvrage_id,
                    'ouvrage_nom': ouvrage_obj.nom_ouvrage,
                    'district_nom': district_nom,
                    'total_diamex': Decimal('0'),
                },
            )

    taux_mensuels_par_ouvrage = {}
    for data in recouvrement_par_ouvrage_mois.values():
        ouvrage_id = data['ouvrage_id']
        total_releves = Decimal(str(data.get('total_releves') or 0))
        total_diamex = Decimal(str(data.get('total_diamex') or 0))
        ecart = total_releves - total_diamex
        taux = int((total_diamex / total_releves) * 100) if total_releves > 0 else 0

        taux_mensuels_par_ouvrage.setdefault(
            ouvrage_id,
            {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': data['ouvrage_nom'],
                'district_nom': data.get('district_nom') or 'Sans district',
                'taux_par_mois': {},
            },
        )
        taux_mensuels_par_ouvrage[ouvrage_id]['taux_par_mois'][data['mois']] = {
            'taux': taux,
            'total_releves': float(total_releves),
            'total_diamex': float(total_diamex),
            'ecart': float(ecart),
            'non_pointe_releve': float(Decimal(str(data.get('montant_non_pointe_releve') or 0))),
            'non_pointe_compta': float(Decimal(str(data.get('montant_non_pointe_compta') or 0))),
            'nb_non_pointe_releve': int(data.get('nb_non_pointe_releve') or 0),
            'nb_non_pointe_compta': int(data.get('nb_non_pointe_compta') or 0),
        }

    visible_month_numbers = [
        month['number']
        for month in REPORT_MONTH_LABELS
        if any(
            ouvrage_data['taux_par_mois'].get(month['number'])
            and (
                Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('total_releves') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('total_diamex') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('non_pointe_releve') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('non_pointe_compta') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('ecart') or 0)) != 0
            )
            for ouvrage_data in taux_mensuels_par_ouvrage.values()
        )
    ]
    visible_month_labels = [
        month
        for month in REPORT_MONTH_LABELS
        if month['number'] in visible_month_numbers
    ]

    grouped_rows = defaultdict(list)
    for ouvrage_data in taux_mensuels_par_ouvrage.values():
        montants_prevus = [
            Decimal(str(item.get('total_releves') or 0))
            for item in ouvrage_data['taux_par_mois'].values()
            if Decimal(str(item.get('total_releves') or 0)) > 0
        ]
        moyenne_prevu = (
            sum(montants_prevus, Decimal('0')) / Decimal(len(montants_prevus))
            if montants_prevus
            else Decimal('0')
        )
        seuil_alerte = moyenne_prevu * Decimal('1.5')
        for item in ouvrage_data['taux_par_mois'].values():
            total_releves = Decimal(str(item.get('total_releves') or 0))
            item['depasse_50_moyenne'] = bool(moyenne_prevu > 0 and total_releves > seuil_alerte)
        ouvrage_data['visible_months'] = [
            ouvrage_data['taux_par_mois'].get(month_number)
            for month_number in visible_month_numbers
        ]
        grouped_rows[ouvrage_data.get('district_nom') or 'Sans district'].append(ouvrage_data)

    groups = []
    for district_nom in sorted(grouped_rows.keys(), key=lambda value: value.lower()):
        rows = sorted(grouped_rows[district_nom], key=lambda item: (item.get('ouvrage_nom') or '').lower())
        groups.append({'district_nom': district_nom, 'rows': rows})

    return {
        'groups': groups,
        'has_data': bool(groups and visible_month_labels),
        'row_count': sum(len(group['rows']) for group in groups),
        'visible_month_labels': visible_month_labels,
    }


def _build_cartes_mensual_workflow_table(annee, effective_gestionnaire_ids, filter_region, filter_district, filter_commune):
    ouvrages_scope_qs = Ouvrage.objects.filter(
        cartes_sociales_infra__isnull=False,
        modalites_gestion__date_fin__isnull=True,
        modalites_gestion__modalitepaiement__in=['au_volume', 'mixte'],
    )
    if effective_gestionnaire_ids is not None:
        if effective_gestionnaire_ids:
            ouvrages_scope_qs = ouvrages_scope_qs.filter(
                modalites_gestion__gestionnaire_id__in=effective_gestionnaire_ids
            )
        else:
            ouvrages_scope_qs = ouvrages_scope_qs.none()
    ouvrages_scope_ids = {str(ouvrage_id) for ouvrage_id in ouvrages_scope_qs.values_list('id', flat=True).distinct()}
    if not ouvrages_scope_ids:
        return {'groups': [], 'has_data': False, 'row_count': 0}

    geo_data = _build_ouvrage_geo_data(ouvrages_scope_ids)
    ouvrages_geo = geo_data['ouvrages_geo']
    ouvrages_filtres_ids = set(ouvrages_scope_ids)

    if filter_region:
        ouvrages_filtres_ids = {
            ouvrage_id
            for ouvrage_id in ouvrages_filtres_ids
            if filter_region in ouvrages_geo.get(ouvrage_id, {}).get('region_ids', set())
        }
    if filter_district:
        ouvrages_filtres_ids = {
            ouvrage_id
            for ouvrage_id in ouvrages_filtres_ids
            if filter_district in ouvrages_geo.get(ouvrage_id, {}).get('district_ids', set())
        }
    if filter_commune:
        ouvrages_filtres_ids = {
            ouvrage_id
            for ouvrage_id in ouvrages_filtres_ids
            if filter_commune in ouvrages_geo.get(ouvrage_id, {}).get('commune_ids', set())
        }
    if not ouvrages_filtres_ids:
        return {'groups': [], 'has_data': False, 'row_count': 0}

    recouvrement_par_ouvrage_mois = {}

    consos_qs = ConsoCarteSociale.objects.filter(
        date__year=annee,
        carte_sociale__ouvrage__isnull=False,
        carte_sociale__ouvrage_id__in=list(ouvrages_filtres_ids),
    ).select_related('carte_sociale__ouvrage')

    for conso in consos_qs:
        ouvrage = conso.carte_sociale.ouvrage
        if not ouvrage or not conso.date:
            continue
        ouvrage_id = str(ouvrage.id)
        geo = ouvrages_geo.get(ouvrage_id, {})
        cle_mois = f'{ouvrage_id}_{annee}_{conso.date.month:02d}'
        recouvrement_par_ouvrage_mois.setdefault(
            cle_mois,
            {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage.nom_ouvrage,
                'region_nom': geo.get('region_nom') or 'Sans region',
                'district_nom': geo.get('district_nom') or 'Sans district',
                'mois': conso.date.month,
                'total_prevu': Decimal('0'),
                'total_realise': Decimal('0'),
            },
        )
        recouvrement_par_ouvrage_mois[cle_mois]['total_prevu'] += Decimal(str(conso.montant_paye or 0))

    for entry in BaseDiameX.objects.filter(compte_code='748415'):
        extraction = extraire_ouvrage_et_mois_generique_views(entry.description or '', entry.compte_code)
        ouvrage_obj = extraction.get('ouvrage_obj')
        mois = extraction.get('mois')
        annee_entry = extraction.get('annee')
        if not ouvrage_obj or not mois or annee_entry != annee:
            continue
        ouvrage_id = str(ouvrage_obj.id)
        if ouvrage_id not in ouvrages_filtres_ids:
            continue

        geo = ouvrages_geo.get(ouvrage_id, {})
        cle_mois = f'{ouvrage_id}_{annee}_{mois:02d}'
        recouvrement_par_ouvrage_mois.setdefault(
            cle_mois,
            {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage_obj.nom_ouvrage,
                'region_nom': geo.get('region_nom') or 'Sans region',
                'district_nom': geo.get('district_nom') or 'Sans district',
                'mois': mois,
                'total_prevu': Decimal('0'),
                'total_realise': Decimal('0'),
            },
        )
        recouvrement_par_ouvrage_mois[cle_mois]['total_realise'] += Decimal(str(entry.montant_in or 0))

    taux_mensuels_par_ouvrage = {}
    for data in recouvrement_par_ouvrage_mois.values():
        ouvrage_id = data['ouvrage_id']
        total_prevu = Decimal(str(data.get('total_prevu') or 0))
        total_realise = Decimal(str(data.get('total_realise') or 0))
        taux = int((total_realise / total_prevu) * 100) if total_prevu > 0 else 0
        taux_mensuels_par_ouvrage.setdefault(
            ouvrage_id,
            {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': data['ouvrage_nom'],
                'region_nom': data.get('region_nom') or 'Sans region',
                'district_nom': data.get('district_nom') or 'Sans district',
                'taux_par_mois': {},
            },
        )
        taux_mensuels_par_ouvrage[ouvrage_id]['taux_par_mois'][data['mois']] = {
            'taux': taux,
            'total_prevu': float(total_prevu),
            'total_realise': float(total_realise),
            'ecart': float(total_prevu - total_realise),
        }

    visible_month_numbers = [
        month['number']
        for month in REPORT_MONTH_LABELS
        if any(
            ouvrage_data['taux_par_mois'].get(month['number'])
            and (
                Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('total_prevu') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('total_realise') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('ecart') or 0)) != 0
            )
            for ouvrage_data in taux_mensuels_par_ouvrage.values()
        )
    ]
    visible_month_labels = [
        month
        for month in REPORT_MONTH_LABELS
        if month['number'] in visible_month_numbers
    ]

    grouped_rows = defaultdict(lambda: defaultdict(list))
    for ouvrage_data in taux_mensuels_par_ouvrage.values():
        ouvrage_data['visible_months'] = [
            ouvrage_data['taux_par_mois'].get(month_number)
            for month_number in visible_month_numbers
        ]
        grouped_rows[ouvrage_data.get('region_nom') or 'Sans region'][ouvrage_data.get('district_nom') or 'Sans district'].append(ouvrage_data)

    groups = []
    for region_nom in sorted(grouped_rows.keys(), key=lambda value: value.lower()):
        districts = []
        for district_nom in sorted(grouped_rows[region_nom].keys(), key=lambda value: value.lower()):
            rows = sorted(grouped_rows[region_nom][district_nom], key=lambda item: (item.get('ouvrage_nom') or '').lower())
            districts.append({'district_nom': district_nom, 'rows': rows})
        groups.append({'region_nom': region_nom, 'districts': districts})

    return {
        'groups': groups,
        'has_data': bool(groups and visible_month_labels),
        'row_count': sum(len(district['rows']) for group in groups for district in group['districts']),
        'visible_month_labels': visible_month_labels,
    }


def _build_forfaitaire_echu_workflow_table(annee, effective_gestionnaire_ids, rows_by_ouvrage):
    ouvrage_ids = set(rows_by_ouvrage.keys())
    if not ouvrage_ids:
        return {'groups': [], 'has_data': False, 'row_count': 0}

    today = timezone.localdate()
    geo_data = _build_ouvrage_geo_data(ouvrage_ids)
    ouvrages_geo = geo_data['ouvrages_geo']
    ouvrages_map = {
        str(ouvrage.id): ouvrage
        for ouvrage in Ouvrage.objects.filter(id__in=list(ouvrage_ids)).only('id', 'nom_ouvrage', 'saisonnier')
    }

    ouvrages_avec_facture_echue = set()
    paiements_qs = PaiementForfaitaire.objects.filter(
        date_facture__year=annee,
        point_eau__ouvrage_id__in=list(ouvrage_ids),
    ).select_related('point_eau__ouvrage')
    for paiement in paiements_qs:
        ouvrage = paiement.point_eau.ouvrage if paiement.point_eau else None
        if not ouvrage:
            continue
        numero_diamex = (paiement.numeroDiameX or '').strip()
        est_paye = bool(numero_diamex) or bool(paiement.paye)
        if (not est_paye) and paiement.date_facture and paiement.date_facture <= today:
            ouvrages_avec_facture_echue.add(str(ouvrage.id))

    if not ouvrages_avec_facture_echue:
        return {'groups': [], 'has_data': False, 'row_count': 0}

    points_eau_by_ouvrage = defaultdict(list)
    points_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=list(ouvrages_avec_facture_echue),
        tarifforfaitaire__isnull=False,
    ).select_related('parcelle__village__fokontany__commune__district')
    for point_eau in points_eau_qs:
        points_eau_by_ouvrage[str(point_eau.ouvrage_id)].append(point_eau)

    points_coupes_map = {
        str(item['point_eau__ouvrage_id']): int(item['nb'] or 0)
        for item in CoupureEau.objects.filter(
            point_eau__ouvrage_id__in=list(ouvrages_avec_facture_echue),
            date_evenement__year=annee,
        ).values('point_eau__ouvrage_id').annotate(nb=Count('point_eau', distinct=True))
    }

    modalite_active_map = _get_modalite_active_map(
        [ouvrage.id for ouvrage in ouvrages_map.values()],
        annee=annee,
        gestionnaire_ids=effective_gestionnaire_ids,
    )

    grouped_rows = defaultdict(lambda: defaultdict(list))
    for ouvrage_id in sorted(ouvrages_avec_facture_echue):
        ouvrage = ouvrages_map.get(ouvrage_id)
        if not ouvrage:
            continue

        row_data = rows_by_ouvrage.get(ouvrage_id, {})
        points_eau = points_eau_by_ouvrage.get(ouvrage_id, [])
        modalite_active = modalite_active_map.get(ouvrage.id)
        trimestres_exigibles = _trimestres_exigibles_depuis_date_debut(
            annee,
            getattr(modalite_active, 'date_debut', None),
        )

        montant_brut = Decimal('0')
        for point_eau in points_eau:
            montant_brut += tarif_pour_annee(point_eau, annee) * Decimal(str(trimestres_exigibles))

        montant_a_collecter = Decimal(str(row_data.get('prevision') or 0))
        montant_paiement_forfaitaire = Decimal(str(row_data.get('prevision_secondaire') or 0))
        montant_collecte = Decimal(str(row_data.get('paye') or 0))
        decote_totale = montant_brut - montant_a_collecter
        if decote_totale < 0:
            decote_totale = Decimal('0')

        has_taux = montant_a_collecter > 0
        taux = int((montant_collecte / montant_a_collecter) * 100) if has_taux else 0
        has_taux_paye_sur_forfaitaire = montant_paiement_forfaitaire > 0
        taux_paye_sur_forfaitaire = (
            int((montant_collecte / montant_paiement_forfaitaire) * 100)
            if has_taux_paye_sur_forfaitaire
            else 0
        )

        geo = ouvrages_geo.get(ouvrage_id, {})
        grouped_rows[geo.get('district_nom') or 'Sans district'][geo.get('commune_nom') or 'Sans commune'].append(
            {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage.nom_ouvrage,
                'est_saisonnier': bool(ouvrage.saisonnier),
                'nb_points_eau': len(points_eau),
                'nb_points_eau_coupes': int(points_coupes_map.get(ouvrage_id, 0)),
                'montant_brut': float(montant_brut),
                'decote_totale': float(decote_totale),
                'montant_a_collecter': float(montant_a_collecter),
                'montant_paiement_forfaitaire': float(montant_paiement_forfaitaire),
                'montant_collecte': float(montant_collecte),
                'taux': taux,
                'has_taux': has_taux,
                'taux_paye_sur_forfaitaire': taux_paye_sur_forfaitaire,
                'has_taux_paye_sur_forfaitaire': has_taux_paye_sur_forfaitaire,
            }
        )

    groups = []
    for district_nom in sorted(grouped_rows.keys(), key=lambda value: value.lower()):
        communes = []
        for commune_nom in sorted(grouped_rows[district_nom].keys(), key=lambda value: value.lower()):
            rows = sorted(grouped_rows[district_nom][commune_nom], key=lambda item: (item.get('ouvrage_nom') or '').lower())
            communes.append({'commune_nom': commune_nom, 'rows': rows})
        groups.append({'district_nom': district_nom, 'communes': communes})

    return {
        'groups': groups,
        'has_data': bool(groups),
        'row_count': sum(len(commune['rows']) for group in groups for commune in group['communes']),
    }


@employe_required
def activites_par_employe(request):
    """Rapport des activités par employé"""
    # Filtres
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    mois_filter = request.GET.get('mois', '')
    employe_filter = request.GET.get('employe', '')

    # Base queryset
    plannings = filter_queryset_by_permissions(Planning.objects.all(), request.user)
    plannings = plannings.filter(date__year=annee_filter)

    if mois_filter:
        plannings = plannings.filter(date__month=mois_filter)

    if employe_filter:
        plannings = plannings.filter(employe_id=employe_filter)

    # Statistiques par employé
    employes_stats = []
    # Employés actifs = ceux qui n'ont pas de date de débauchage
    employes_qs = filter_queryset_by_permissions(Employe.objects.filter(date_debauchage__isnull=True), request.user)

    if employe_filter:
        employes_qs = employes_qs.filter(id=employe_filter)

    for employe in employes_qs:
        plannings_employe = plannings.filter(employe=employe)

        # Compter par type d'activité
        activites_count = plannings_employe.values(
            activite__nom=F('type_activite__nomtype')
        ).annotate(
            count=Count('id')
        ).order_by('-count')

        total_jours = plannings_employe.count()

        employes_stats.append({
            'employe': employe,
            'total_jours': total_jours,
            'activites': list(activites_count),
        })

    # Listes pour les dropdowns
    employes_list = filter_queryset_by_permissions(Employe.objects.filter(date_debauchage__isnull=True), request.user).order_by('surnom')

    context = {
        'title': 'Activités par Employé',
        'annee_filter': annee_filter,
        'mois_filter': mois_filter,
        'employe_filter': employe_filter,
        'employes_stats': employes_stats,
        'employes_list': employes_list,
    }

    return render(request, 'core/activites_par_employe.html', context)


@employe_required
def performance_bases(request):
    """Rapport de performance par base/ouvrage"""
    # Filtres
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    ouvrage_filter = request.GET.get('ouvrage', '')

    # Base queryset
    ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)

    if ouvrage_filter:
        ouvrages = ouvrages.filter(id=ouvrage_filter)

    # Statistiques par ouvrage
    ouvrages_stats = []

    for ouvrage in ouvrages:
        # Nombre d'interventions
        interventions = Planning.objects.filter(
            ouvrage=ouvrage,
            date__year=annee_filter
        ).count()

        # Nombre de points d'eau
        nb_points_eau = ouvrage.pointeau_set.count()

        # Taux d'intervention (interventions / points d'eau)
        taux_intervention = (interventions / nb_points_eau * 100) if nb_points_eau > 0 else 0

        ouvrages_stats.append({
            'ouvrage': ouvrage,
            'nb_points_eau': nb_points_eau,
            'interventions': interventions,
            'taux_intervention': round(taux_intervention, 2),
        })

    # Trier par taux d'intervention décroissant
    ouvrages_stats.sort(key=lambda x: x['taux_intervention'], reverse=True)

    # Listes pour les dropdowns
    ouvrages_list = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user).order_by('nom_ouvrage')

    context = {
        'title': 'Performance des Bases',
        'annee_filter': annee_filter,
        'ouvrage_filter': ouvrage_filter,
        'ouvrages_stats': ouvrages_stats,
        'ouvrages_list': ouvrages_list,
    }

    return render(request, 'core/performance_bases.html', context)


@employe_required
def indicateurs_diamex(request):
    """Indicateurs DiameX - Suivi des synchronisations comptables"""
    # Filtres
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    mois_filter = request.GET.get('mois', '')

    # Base queryset des détails de planning avec numéro DiameX
    details_qs = PlanningDetail.objects.filter(
        planning__date__year=annee_filter
    )

    if mois_filter:
        details_qs = details_qs.filter(planning__date__month=mois_filter)

    # Statistiques globales
    total_details = details_qs.count()
    details_avec_diamex = details_qs.filter(numeroDiameX__isnull=False).count()
    details_sans_diamex = total_details - details_avec_diamex

    taux_sync = (details_avec_diamex / total_details * 100) if total_details > 0 else 0

    # Statistiques par type de désignation
    details_par_type = details_qs.values('designation__nom').annotate(
        total=Count('id'),
        avec_diamex=Count('id', filter=Q(numeroDiameX__isnull=False)),
    ).order_by('-total')

    # Calculer les pourcentages
    for item in details_par_type:
        item['taux_sync'] = (item['avec_diamex'] / item['total'] * 100) if item['total'] > 0 else 0
        item['sans_diamex'] = item['total'] - item['avec_diamex']

    context = {
        'title': 'Indicateurs DiameX',
        'annee_filter': annee_filter,
        'mois_filter': mois_filter,
        'total_details': total_details,
        'details_avec_diamex': details_avec_diamex,
        'details_sans_diamex': details_sans_diamex,
        'taux_sync': round(taux_sync, 2),
        'details_par_type': list(details_par_type),
    }

    return render(request, 'core/indicateurs_diamex.html', context)


def _build_partner_report_filter_context(request):
    current_year = datetime.now().year
    root_organisation = get_user_organisation(request.user)
    allowed_organisation_ids = _get_dashboard_allowed_organisation_ids(request.user)
    root_is_gestionnaire = bool(
        root_organisation and root_organisation.type_organisation == Organisation.TYPE_GESTIONNAIRE
    )
    organisation_locked = bool(
        root_is_gestionnaire and not request.user.is_superuser and not is_visiteur(request.user)
    )

    if organisation_locked:
        organisations = Organisation.objects.filter(id=root_organisation.id).order_by('nom_organisation')
    elif request.user.is_superuser or is_visiteur(request.user):
        organisations = Organisation.objects.filter(
            type_organisation=Organisation.TYPE_GESTIONNAIRE
        ).order_by('nom_organisation')
    elif allowed_organisation_ids is None:
        organisations = Organisation.objects.filter(
            type_organisation=Organisation.TYPE_GESTIONNAIRE
        ).order_by('nom_organisation')
    elif allowed_organisation_ids:
        organisations = Organisation.objects.filter(
            id__in=allowed_organisation_ids,
            type_organisation=Organisation.TYPE_GESTIONNAIRE
        ).order_by('nom_organisation')
    else:
        organisations = Organisation.objects.none()

    if organisation_locked:
        selected_organisation = str(root_organisation.id)
    else:
        selected_organisation = _resolve_dashboard_organisation_filter(
            request.user,
            request.GET.get('organisation', '')
        )
        if selected_organisation and not organisations.filter(id=selected_organisation).exists():
            selected_organisation = ''
        if not selected_organisation:
            default_organisation = None
            if root_is_gestionnaire:
                default_organisation = organisations.filter(id=root_organisation.id).first()
            if not default_organisation:
                default_organisation = organisations.first()
            selected_organisation = str(default_organisation.id) if default_organisation else ''

    ouvrages_accessibles = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    scope_info = _resolve_effective_gestionnaire_scope(request.user, selected_organisation)
    effective_gestionnaire_ids = scope_info['effective_gestionnaire_ids']
    if effective_gestionnaire_ids is not None:
        scoped_ouvrage_ids = _get_ouvrages_ids_by_effective_gestionnaire_ids(effective_gestionnaire_ids)
        if scoped_ouvrage_ids:
            ouvrages_accessibles = ouvrages_accessibles.filter(id__in=scoped_ouvrage_ids)
        else:
            ouvrages_accessibles = ouvrages_accessibles.none()

    points_eau_accessibles = PointEau.objects.filter(ouvrage__in=ouvrages_accessibles)
    communes_accessibles = Commune.objects.filter(
        fokontanys__villages__parcelles__pointeau__in=points_eau_accessibles
    ).select_related('district__region').distinct()
    districts_accessibles = District.objects.filter(
        communes__in=communes_accessibles
    ).select_related('region').distinct()
    regions_accessibles = Region.objects.filter(
        districts__in=districts_accessibles
    ).distinct()
    selected_region = (request.GET.get('region', '') or '').strip()
    selected_district = (request.GET.get('district', '') or '').strip()
    selected_commune = (request.GET.get('commune', '') or '').strip()

    try:
        selected_year = int((request.GET.get('annee', '') or '').strip() or current_year)
    except (TypeError, ValueError):
        selected_year = current_year

    annee_min_data = ouvrages_accessibles.aggregate(
        min_realisation=Min('annee_realisation'),
        min_avant=Min('annee_realisation_avant'),
    )
    year_candidates = [annee_min_data['min_realisation'], annee_min_data['min_avant']]
    first_year = min(filter(None, year_candidates)) if any(year_candidates) else current_year - 10
    years = list(range(int(first_year), current_year + 1))
    years.reverse()

    if selected_region and not regions_accessibles.filter(id=selected_region).exists():
        selected_region = ''

    districts = districts_accessibles
    if selected_region:
        districts = districts.filter(region_id=selected_region)
    if selected_district and not districts.filter(id=selected_district).exists():
        selected_district = ''

    communes = communes_accessibles
    if selected_region:
        communes = communes.filter(district__region_id=selected_region)
    if selected_district:
        communes = communes.filter(district_id=selected_district)
    if selected_commune and not communes.filter(id=selected_commune).exists():
        selected_commune = ''

    return {
        'ouvrages_accessibles': ouvrages_accessibles,
        'organisations': organisations,
        'regions': regions_accessibles.order_by('nom_region'),
        'districts': districts.order_by('nom_district'),
        'communes': communes.order_by('nom_commune'),
        'selected_organisation': selected_organisation,
        'organisation_locked': organisation_locked,
        'root_organisation': root_organisation,
        'selected_region': selected_region,
        'selected_district': selected_district,
        'selected_commune': selected_commune,
        'selected_year': selected_year,
        'years': years,
    }


def _build_partner_report_identity_context(request, filter_context):
    root_organisation = get_user_organisation(request.user)
    selected_organisation_id = filter_context['selected_organisation']
    selected_region_id = filter_context['selected_region']
    selected_district_id = filter_context['selected_district']
    selected_commune_id = filter_context['selected_commune']

    selected_organisation = None
    if selected_organisation_id:
        selected_organisation = Organisation.objects.filter(id=selected_organisation_id).first()

    selected_region = None
    if selected_region_id:
        selected_region = Region.objects.filter(id=selected_region_id).first()

    selected_district = None
    if selected_district_id:
        selected_district = District.objects.select_related('region').filter(id=selected_district_id).first()

    selected_commune = None
    if selected_commune_id:
        selected_commune = Commune.objects.select_related('district__region').filter(id=selected_commune_id).first()

    if selected_commune and not selected_district:
        selected_district = selected_commune.district
    if selected_district and not selected_region:
        selected_region = selected_district.region
    if selected_commune and not selected_region:
        selected_region = selected_commune.district.region

    scope_level = 'organisation'
    scope_level_label = 'Organisation'
    scope_label = (
        (root_organisation.nom_organisation if root_organisation else None)
        or (selected_organisation.nom_organisation if selected_organisation else None)
        or 'Toutes les organisations'
    )

    if selected_region:
        scope_level = 'region'
        scope_level_label = 'Region'
        scope_label = selected_region.nom_region
    if selected_district:
        scope_level = 'district'
        scope_level_label = 'District'
        scope_label = selected_district.nom_district
    if selected_commune:
        scope_level = 'commune'
        scope_level_label = 'Commune'
        scope_label = selected_commune.nom_commune

    period_year = filter_context['selected_year']
    try:
        requested_period_year = int((request.GET.get('archive_period_year', '') or '').strip() or period_year)
    except (TypeError, ValueError):
        requested_period_year = period_year

    period_quarter = None
    try:
        raw_quarter = (request.GET.get('archive_period_quarter', '') or '').strip()
        parsed_quarter = int(raw_quarter) if raw_quarter else None
        if parsed_quarter in {1, 2, 3, 4}:
            period_quarter = parsed_quarter
    except (TypeError, ValueError):
        period_quarter = None

    period_label = (
        f"T{period_quarter} {requested_period_year}"
        if period_quarter
        else f"Annee {period_year}"
    )

    return {
        'organisation_label': (
            (root_organisation.nom_organisation if root_organisation else None)
            or (selected_organisation.nom_organisation if selected_organisation else None)
            or 'Toutes les organisations'
        ),
        'scope_level': scope_level,
        'scope_level_label': scope_level_label,
        'scope_label': scope_label,
        'region_label': selected_region.nom_region if selected_region else '',
        'district_label': selected_district.nom_district if selected_district else '',
        'commune_label': selected_commune.nom_commune if selected_commune else '',
        'period_label': period_label,
        'period_year': requested_period_year,
        'period_quarter': period_quarter,
    }


def _build_dashboard_report_data(request, filter_context):
    ouvrages_accessibles = filter_context['ouvrages_accessibles']
    organisation_id = filter_context['selected_organisation']
    region_id = filter_context['selected_region']
    district_id = filter_context['selected_district']
    commune_id = filter_context['selected_commune']
    annee = filter_context['selected_year']

    stats = calculate_dashboard_stats_with_permissions(
        ouvrages_accessibles,
        region_id=region_id,
        district_id=district_id,
        commune_id=commune_id,
        annee=annee,
        organisation_id=organisation_id,
    )
    stats_par_commune = calculate_dashboard_stats_par_commune_with_permissions(
        ouvrages_accessibles,
        region_id=region_id,
        district_id=district_id,
        commune_id=commune_id,
        annee=annee,
        organisation_id=organisation_id,
    )
    modalites_payload = get_dashboard_modalites_payment_chart_payload(
        request.user,
        region_id=region_id,
        district_id=district_id,
        commune_id=commune_id,
        annee=annee,
        organisation_id=organisation_id,
    )
    stats_par_commune_breakdown = _build_dashboard_commune_breakdown(stats_par_commune, stats)
    ouvrage_detail = (
        _build_dashboard_ouvrage_detail_rows(request, filter_context)
        if commune_id
        else {'selected_commune': None, 'rows': [], 'visible_columns': {}, 'colspan': 13}
    )

    modalite_rows = [
        {
            'label': 'Forfaitaire',
            'ouvrages': stats.get('ouvrages_forfaitaire', 0),
            'points_eau': stats.get('points_eau_forfaitaire', 0),
        },
        {
            'label': 'Au volume',
            'ouvrages': stats.get('ouvrages_volume', 0),
            'points_eau': stats.get('points_eau_volume', 0),
        },
        {
            'label': 'Mixte',
            'ouvrages': stats.get('ouvrages_mixte', 0),
            'points_eau': stats.get('points_eau_mixte', 0),
        },
        {
            'label': 'Cotisation',
            'ouvrages': stats.get('ouvrages_cotisation', 0),
            'points_eau': stats.get('points_eau_cotisation', 0),
        },
    ]
    modalite_rows = [
        row for row in modalite_rows
        if int(row.get('ouvrages') or 0) > 0 or int(row.get('points_eau') or 0) > 0
    ]

    return {
        'stats': stats,
        'stat_sections': _build_dashboard_stat_sections(stats),
        'stats_par_commune': stats_par_commune,
        'stats_par_commune_groups': stats_par_commune_breakdown['groups'],
        'stats_par_commune_totals': stats_par_commune_breakdown['totals'],
        'is_commune_detail_mode': bool(commune_id),
        'selected_commune': ouvrage_detail['selected_commune'],
        'ouvrage_detail_rows': ouvrage_detail['rows'],
        'ouvrage_detail_visible_columns': ouvrage_detail['visible_columns'],
        'ouvrage_detail_colspan': ouvrage_detail['colspan'],
        'modalite_rows': modalite_rows,
        'modalite_totals': {
            'ouvrages': sum(int(row['ouvrages'] or 0) for row in modalite_rows),
            'points_eau': sum(int(row['points_eau'] or 0) for row in modalite_rows),
        },
        'points_chart': modalites_payload.get('chart_data', {}),
        'ouvrages_chart': modalites_payload.get('ouvrages_chart_data', {}),
    }


def _build_visites_report_data(request, filter_context):
    organisation_scope = _get_organisation_filter_state(request)
    ouvrages = _get_filtered_ouvrages_queryset(
        request,
        organisation_scope['gestionnaire_ids'],
        organisation_scope['organisation_filter'],
        filter_context['selected_region'],
        filter_context['selected_district'],
        filter_context['selected_commune'],
        filter_context['selected_year'],
    )
    stats_ouvrages = _build_ouvrage_stats(
        ouvrages,
        annee=filter_context['selected_year'],
        organisation_filter=organisation_scope['organisation_filter'],
        gestionnaire_ids=organisation_scope['gestionnaire_ids'],
    )

    total_visites = sum(stat['nb_visites'] for stat in stats_ouvrages)
    total_visites_reparation = sum(stat['nb_visites_reparation'] for stat in stats_ouvrages)
    total_visites_reparation_panne = sum(stat['nb_visites_reparation_panne'] for stat in stats_ouvrages)

    visites_counts = sorted(stat['nb_visites'] for stat in stats_ouvrages)
    if visites_counts:
        middle = len(visites_counts) // 2
        if len(visites_counts) % 2:
            median_visites = visites_counts[middle]
        else:
            median_visites = (visites_counts[middle - 1] + visites_counts[middle]) / 2
    else:
        median_visites = 0

    return {
        'total_visites': total_visites,
        'total_visites_reparation': total_visites_reparation,
        'total_visites_reparation_panne': total_visites_reparation_panne,
        'nb_ouvrages': len(stats_ouvrages),
        'moyenne_visites': round((total_visites / len(stats_ouvrages)), 2) if stats_ouvrages else 0,
        'median_visites': median_visites,
    }


def _recettes_category_has_visible_values(category):
    if Decimal(str(category.get('prevision') or 0)) != Decimal('0'):
        return True
    if Decimal(str(category.get('paye') or 0)) != Decimal('0'):
        return True
    if Decimal(str(category.get('ecart') or 0)) != Decimal('0'):
        return True
    if int(category.get('nb_ouvrages') or 0) > 0:
        return True
    return False


def _build_recettes_report_data(request, filter_context):
    annee = filter_context['selected_year']
    organisation_id = filter_context['selected_organisation']
    region_id = filter_context['selected_region']
    district_id = filter_context['selected_district']
    commune_id = filter_context['selected_commune']

    scope_info = _resolve_effective_gestionnaire_scope(request.user, organisation_id)
    accessible_gestionnaire_ids = scope_info['accessible_gestionnaire_ids']
    effective_gestionnaire_ids = scope_info['effective_gestionnaire_ids']
    selected_organisation_id = scope_info['selected_organisation_id']

    categories_raw = [
        _compute_forfaitaire_summary(
            request,
            annee,
            selected_organisation_id,
            region_id,
            district_id,
            commune_id,
            '',
        ),
        _compute_volume_summary(
            annee,
            effective_gestionnaire_ids,
            region_id,
            district_id,
            commune_id,
            '',
        ),
        _compute_cartes_sociales_summary(
            annee,
            effective_gestionnaire_ids,
            region_id,
            district_id,
            commune_id,
            '',
        ),
    ]

    total_prevu_global = sum((category['prevision'] for category in categories_raw), 0)
    total_paye_global = sum((category['paye'] for category in categories_raw), 0)
    ouvrages_couverts = set().union(*(category.get('ouvrage_ids', set()) for category in categories_raw))
    communes_breakdown = _build_communes_breakdown(categories_raw)
    ouvrages_breakdown = (
        _build_recettes_ouvrage_breakdown(categories_raw)
        if commune_id
        else {'rows': [], 'visible_columns': {}, 'colspan': 12}
    )
    categories_by_key = {category['key']: category for category in categories_raw}
    show_current_year_tables = annee == timezone.localdate().year
    workflow_tables = {
        'month_labels': REPORT_MONTH_LABELS,
        'volume': {'groups': [], 'has_data': False, 'row_count': 0},
        'cartes_sociales': {'groups': [], 'has_data': False, 'row_count': 0},
        'forfaitaire_echu': {'groups': [], 'has_data': False, 'row_count': 0},
    }

    if show_current_year_tables:
        workflow_tables['volume'] = _build_volume_monthly_workflow_table(
            annee,
            effective_gestionnaire_ids,
            region_id,
            district_id,
            commune_id,
        )
        workflow_tables['cartes_sociales'] = _build_cartes_mensual_workflow_table(
            annee,
            effective_gestionnaire_ids,
            region_id,
            district_id,
            commune_id,
        )
        workflow_tables['forfaitaire_echu'] = _build_forfaitaire_echu_workflow_table(
            annee,
            effective_gestionnaire_ids,
            categories_by_key.get('forfaitaire', {}).get('rows_by_ouvrage', {}),
        )

    categories = []
    for category in categories_raw:
        if not _recettes_category_has_visible_values(category):
            continue
        item = {
            'key': category['key'],
            'label': category['label'],
            'description': category['description'],
            'prevision_label': category['prevision_label'],
            'prevision': float(category['prevision']),
            'paye': float(category['paye']),
            'ecart': float(category['ecart']),
            'taux': category['taux'],
            'nb_ouvrages': category['nb_ouvrages'],
        }
        if 'prevision_secondaire_label' in category:
            item['prevision_secondaire_label'] = category['prevision_secondaire_label']
            item['prevision_secondaire'] = float(category.get('prevision_secondaire') or 0)
        categories.append(item)

    return {
        'categories': categories,
        'is_commune_detail_mode': bool(commune_id),
        'ouvrages_breakdown': ouvrages_breakdown['rows'],
        'ouvrages_breakdown_visible_columns': ouvrages_breakdown['visible_columns'],
        'ouvrages_breakdown_colspan': ouvrages_breakdown['colspan'],
        'communes_breakdown': communes_breakdown['groups'],
        'communes_totals': communes_breakdown['totals'],
        'stats_global': {
            'total_prevu': float(total_prevu_global),
            'total_paye': float(total_paye_global),
            'ecart': float(total_prevu_global - total_paye_global),
            'taux_recouvrement': int((total_paye_global / total_prevu_global) * 100) if total_prevu_global else 0,
            'nb_categories': len(categories),
            'nb_ouvrages_total': len(ouvrages_couverts),
        },
        'show_current_year_tables': show_current_year_tables,
        'workflow_tables': workflow_tables,
        'organisations': _get_gestionnaire_organisations_for_filter(accessible_gestionnaire_ids),
    }


def _build_partner_report_archives_context(request, filter_context):
    queryset = build_partner_report_archive_queryset_for_user(request.user)
    root_organisation = get_user_organisation(request.user)
    selected_organisation_id = (filter_context.get('selected_organisation', '') or '').strip()

    if selected_organisation_id:
        queryset = queryset.filter(organisation_id=selected_organisation_id)
        root_organisation = Organisation.objects.filter(id=selected_organisation_id).first() or root_organisation

    latest_due_spec = get_latest_due_partner_report_quarter_spec()
    archives = list(
        queryset.order_by(
            '-report_year',
            '-report_quarter',
            'organisation__nom_organisation',
            'scope_level',
            'region__nom_region',
            'district__nom_district',
            'commune__nom_commune',
        )[:200]
    )
    latest_generated_at = archives[0].generated_at if archives else None

    return {
        'root_organisation': root_organisation,
        'latest_due_spec': latest_due_spec,
        'latest_generated_at': latest_generated_at,
        'items': archives,
        'total_count': queryset.count(),
        'can_generate': bool(root_organisation),
    }


def build_partner_report_context(request, print_mode=None, layout_config=None):
    filter_context = _build_partner_report_filter_context(request)
    if print_mode is None:
        print_mode = (request.GET.get('print', '') or '').strip() == '1'
    normalized_layout_config = _normalize_partner_report_layout_config(layout_config)
    print_state = (
        _build_partner_report_print_state(selected_ids=normalized_layout_config['selected_items'])
        if layout_config is not None
        else _build_partner_report_print_state(request=request)
    )

    grading_payload = build_ouvrage_grading_annuel_analyse_payload(
        request,
        filters={
            'organisation_id': filter_context['selected_organisation'],
            'region_id': filter_context['selected_region'],
            'district_id': filter_context['selected_district'],
            'commune_id': filter_context['selected_commune'],
            'annee_from': (request.GET.get('grading_annee_from', '') or '').strip(),
            'annee_to': (request.GET.get('grading_annee_to', '') or '').strip(),
        },
    )
    representants_payload = build_representants_avis_evolution_payload(
        request,
        filters={
            'organisation': filter_context['selected_organisation'],
            'region': filter_context['selected_region'],
            'district': filter_context['selected_district'],
            'commune': filter_context['selected_commune'],
            'ouvrage': '',
            'search': '',
            'actif': (request.GET.get('actif', 'tous') or 'tous').strip(),
            'annee_min': (request.GET.get('avis_annee_min', '') or '').strip(),
            'annee_max': (request.GET.get('avis_annee_max', '') or '').strip(),
        },
    )

    return {
        'title': 'Rapport partenaires',
        'compact_base': True,
        'base_template': 'core/report_print_base.html' if print_mode else 'base.html',
        'print_mode': print_mode,
        'print_url': _build_partner_report_print_url(request),
        'print_form_fields': _build_partner_report_print_form_fields(request),
        'print_option_groups': print_state['groups'],
        'print_visibility': print_state['visibility'],
        'print_sections': print_state['sections'],
        'print_selected_count': print_state['selected_count'],
        'print_has_custom_selection': print_state['has_custom_selection'],
        'print_narratives': normalized_layout_config['narratives'],
        'print_layout_config': normalized_layout_config,
        'generated_at': timezone.localtime(timezone.now()),
        'current_full_path': request.get_full_path(),
        'filter_context': filter_context,
        'report_identity': _build_partner_report_identity_context(request, filter_context),
        'dashboard_data': _build_dashboard_report_data(request, filter_context),
        'visites_data': _build_visites_report_data(request, filter_context),
        'grading_data': grading_payload,
        'recettes_data': _build_recettes_report_data(request, filter_context),
        'representants_data': representants_payload,
        'selected_grading_annee_from': (request.GET.get('grading_annee_from', '') or '').strip(),
        'selected_grading_annee_to': (request.GET.get('grading_annee_to', '') or '').strip(),
        'selected_avis_annee_min': (request.GET.get('avis_annee_min', '') or '').strip(),
        'selected_avis_annee_max': (request.GET.get('avis_annee_max', '') or '').strip(),
        'selected_actif': (request.GET.get('actif', 'tous') or 'tous').strip(),
        'archives_data': _build_partner_report_archives_context(request, filter_context),
        'print_urls': {
            'dashboard': reverse('core:dashboard'),
            'visites': reverse('planning:visites_par_ouvrage'),
            'grading': reverse('organization:ouvrage_grading_annuel_analyse'),
            'recettes': reverse('accounting:dashboard_recettes_globales'),
            'representants': reverse('usagers:representants_avis_evolution_dashboard'),
        },
    }


@employe_required
def rapport_partenaires_trimestriel(request):
    context = build_partner_report_context(request)
    return render(request, 'core/rapport_partenaires_trimestriel.html', context)


@employe_required
@require_POST
def generate_partner_report_archives_now(request):
    organisation = get_user_organisation(request.user)
    next_url = request.POST.get('next') or reverse('core:rapport_partenaires_trimestriel')

    if request.user.is_superuser and not organisation:
        selected_organisation_id = (request.POST.get('organisation', '') or '').strip()
        if selected_organisation_id:
            organisation = Organisation.objects.filter(
                id=selected_organisation_id,
                type_organisation=Organisation.TYPE_GESTIONNAIRE,
            ).first()

    if not organisation:
        messages.error(request, "Aucune organisation racine n'est liee a cet utilisateur.")
        return redirect(next_url)

    try:
        summary = generate_partner_report_archives_for_organisation(
            organisation=organisation,
            generated_by=request.user,
            overwrite=False,
            automatic=False,
        )
    except PartnerReportArchiveError as exc:
        messages.error(request, f"Generation des archives impossible: {exc}")
        return redirect(next_url)
    except Exception as exc:
        messages.error(request, f"Erreur inattendue pendant la generation des archives: {exc}")
        return redirect(next_url)

    created_count = summary.get('created_count', 0)
    skipped_count = summary.get('skipped_count', 0)
    messages.success(
        request,
        f"Archives trimestrielles traitees: {created_count} archive(s) HTML generee(s), {skipped_count} deja presente(s).",
    )
    return redirect(next_url)


def _get_partner_report_archive_file_response(archive):
    filename = (getattr(archive.document_file, 'name', '') or '').rsplit('/', 1)[-1]
    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    response = FileResponse(archive.document_file.open('rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _get_partner_report_archive_html_filename(archive):
    scope_fragment = (archive.scope_key or 'archive').replace(':', '-').replace('/', '-')
    return f"rapport-partenaires-{archive.period_label}-{scope_fragment}.html".replace(' ', '-')


@employe_required
def download_partner_report_archive(request, archive_id):
    queryset = build_partner_report_archive_queryset_for_user(request.user)
    archive = get_object_or_404(queryset, id=archive_id)
    if not archive.document_file:
        try:
            archive = regenerate_partner_report_archive(
                archive,
                generated_by=request.user,
                automatic=False,
            )
            archive.refresh_from_db()
        except PartnerReportArchiveError as exc:
            raise Http404(
                "Le document archive est introuvable et sa regeneration automatique a echoue."
            ) from exc

    if not archive.document_file:
        raise Http404("Le document archive est introuvable.")

    return _get_partner_report_archive_file_response(archive)


@employe_required
def view_partner_report_archive_html(request, archive_id):
    archive = get_object_or_404(
        build_partner_report_archive_queryset_for_user(request.user),
        id=archive_id,
    )
    if not archive.has_html_archive:
        try:
            archive = regenerate_partner_report_archive_html(
                archive,
                generated_by=request.user,
                automatic=False,
            )
            archive.refresh_from_db()
        except PartnerReportArchiveError as exc:
            raise Http404(
                "L'archive HTML est introuvable et sa regeneration automatique a echoue."
            ) from exc

    if not archive.has_html_archive:
        raise Http404("L'archive HTML est introuvable.")

    response = HttpResponse(archive.html_content, content_type='text/html; charset=utf-8')
    if request.GET.get('download') == '1':
        filename = _get_partner_report_archive_html_filename(archive)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@employe_required
@require_http_methods(["GET", "POST"])
def edit_partner_report_archive_html(request, archive_id):
    archive = get_object_or_404(
        build_partner_report_archive_queryset_for_user(request.user),
        id=archive_id,
    )
    next_url = request.GET.get('next') or request.POST.get('next') or reverse('core:rapport_partenaires_trimestriel')

    if request.method == 'POST':
        archive.layout_config = _extract_partner_report_layout_config_from_post(request.POST)
        archive.generated_by = request.user
        archive.is_automatic = False
        archive.save(update_fields=['layout_config', 'generated_by', 'is_automatic', 'updated_at'])

        try:
            archive = regenerate_partner_report_archive_html(
                archive,
                generated_by=request.user,
                automatic=False,
            )
        except PartnerReportArchiveError as exc:
            messages.error(request, f"Archive HTML impossible a mettre a jour: {exc}")
        else:
            messages.success(
                request,
                f"Archive HTML mise a jour pour {archive.period_label} - {archive.territory_label}.",
            )

        if request.POST.get('action') == 'save_and_view':
            return redirect(reverse('core:view_partner_report_archive_html', args=[archive.id]))
        if request.POST.get('action') == 'save_and_return':
            return redirect(next_url)
        safe_next = quote(next_url, safe='')
        return redirect(f"{reverse('core:edit_partner_report_archive_html', args=[archive.id])}?next={safe_next}")

    layout_config = _normalize_partner_report_layout_config(archive.layout_config or {})
    print_state = _build_partner_report_print_state(selected_ids=layout_config['selected_items'])
    context = {
        'title': 'Personnaliser archive HTML',
        'archive': archive,
        'next_url': next_url,
        'layout_config': layout_config,
        'print_option_groups': print_state['groups'],
        'print_selected_count': print_state['selected_count'],
        'print_has_custom_selection': print_state['has_custom_selection'],
        'html_view_url': reverse('core:view_partner_report_archive_html', args=[archive.id]),
        'html_download_url': f"{reverse('core:view_partner_report_archive_html', args=[archive.id])}?download=1",
    }
    return render(request, 'core/partner_report_archive_html_editor.html', context)


@employe_required
@require_POST
def upload_partner_report_archive(request, archive_id):
    archive = get_object_or_404(
        build_partner_report_archive_queryset_for_user(request.user),
        id=archive_id,
    )
    next_url = request.POST.get('next') or reverse('core:rapport_partenaires_trimestriel')
    uploaded_file = request.FILES.get('document_file')

    if not uploaded_file:
        messages.error(request, "Selectionnez un document Word a televerser.")
        return redirect(next_url)

    filename = uploaded_file.name or ''
    extension = f".{filename.rsplit('.', 1)[-1].lower()}" if '.' in filename else ''
    if extension not in {'.doc', '.docx'}:
        messages.error(request, "Le fichier doit etre au format .doc ou .docx.")
        return redirect(next_url)

    if archive.document_file:
        archive.document_file.delete(save=False)

    archive.document_file.save(filename, uploaded_file, save=False)
    archive.file_size = uploaded_file.size or None
    archive.generated_at = timezone.now()
    archive.generated_by = archive.generated_by or request.user
    archive.is_automatic = False
    archive.is_user_uploaded = True
    archive.uploaded_by = request.user
    archive.save()

    messages.success(
        request,
        f"Version Word importee pour {archive.period_label} - {archive.territory_label}.",
    )
    return redirect(next_url)


@employe_required
@require_POST
def delete_partner_report_archive(request, archive_id):
    archive = get_object_or_404(
        build_partner_report_archive_queryset_for_user(request.user),
        id=archive_id,
    )
    next_url = request.POST.get('next') or reverse('core:rapport_partenaires_trimestriel')
    archive_label = f"{archive.period_label} - {archive.territory_label}"

    if archive.document_file:
        archive.document_file.delete(save=False)
    archive.delete()

    messages.success(request, f"Archive supprimee: {archive_label}.")
    return redirect(next_url)
