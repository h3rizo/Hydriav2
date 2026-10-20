from __future__ import annotations

from collections import defaultdict

from django.shortcuts import render
from django.utils import timezone

from apps.billing.models import ModaliteGestion, PointEau
from apps.employees.permissions import employe_required
from apps.geography.models import Parcelle

from .models import Organisation, Ouvrage
from .services_fonctionnalite import get_statuts_fonctionnel_bulk
from .scoping import (
    get_default_gestionnaire_filter_value,
    get_user_accessible_gestionnaire_ids,
)
from .views_grading_annuel import (
    _apply_geo_filters_to_ouvrages,
    _build_ouvrage_rows,
    _extract_ouvrage_ids,
    _geo_filter_options,
    _normalize_filter_value,
)


def _base_modalites_queryset(user):
    qs = (
        ModaliteGestion.objects.exclude(type_gestion='pas_de_gestion')
        .filter(ouvrage__type_ouvrage__existe=True)
        .select_related('ouvrage', 'ouvrage__type_ouvrage', 'gestionnaire')
    )

    allowed_organisation_ids = get_user_accessible_gestionnaire_ids(user)
    if allowed_organisation_ids is None:
        return qs, None

    allowed_organisation_ids = [str(item) for item in allowed_organisation_ids if item]
    if not allowed_organisation_ids:
        return qs.none(), []

    return qs.filter(gestionnaire_id__in=allowed_organisation_ids), allowed_organisation_ids


def _organisation_filter_options_from_modalites(modalites_qs, allowed_ids):
    organisation_ids = (
        modalites_qs.filter(gestionnaire_id__isnull=False)
        .values_list('gestionnaire_id', flat=True)
        .distinct()
    )
    organisations = Organisation.objects.filter(
        id__in=organisation_ids,
        type_organisation=Organisation.TYPE_GESTIONNAIRE,
    )

    if allowed_ids is not None:
        if allowed_ids:
            organisations = organisations.filter(id__in=allowed_ids)
        else:
            organisations = Organisation.objects.none()

    return organisations.order_by('nom_organisation')


def _extract_available_years(modalites_items):
    if not modalites_items:
        return []

    current_year = timezone.localdate().year
    min_year = None
    max_year = None

    for item in modalites_items:
        if not item.date_debut:
            continue

        start_year = item.date_debut.year
        end_year = item.date_fin.year if item.date_fin else current_year

        min_year = start_year if min_year is None else min(min_year, start_year)
        max_year = end_year if max_year is None else max(max_year, end_year)

    if min_year is None or max_year is None:
        return []

    return list(range(max_year, min_year - 1, -1))


def _new_detail_bucket():
    return {
        'gestionnaires': set(),
        'types_gestion': set(),
        'modalites_paiement': set(),
        'statuts': set(),
        'lignes': 0,
    }


def _join_display(values, fallback='-'):
    cleaned = sorted({str(value).strip() for value in values if str(value or '').strip()})
    return ', '.join(cleaned) if cleaned else fallback


def _detail_to_display(detail):
    detail = detail or {}
    return {
        'gestionnaires_display': _join_display(detail.get('gestionnaires', []), 'Non specifie'),
        'types_gestion_display': _join_display(detail.get('types_gestion', []), '-'),
        'modalites_paiement_display': _join_display(detail.get('modalites_paiement', []), 'Non specifie'),
        'statuts_display': _join_display(detail.get('statuts', []), '-'),
        'nombre_lignes': int(detail.get('lignes', 0) or 0),
    }


def _augment_rows_with_year_detail(rows, detail_by_ouvrage_year, year):
    for row in rows:
        row.update(
            _detail_to_display(
                detail_by_ouvrage_year.get((row['ouvrage_id'], year))
            )
        )
    return rows


ORG_CHART_PALETTE = [
    '#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed',
    '#0891b2', '#db2777', '#65a30d', '#ea580c', '#4338ca',
    '#0d9488', '#b91c1c', '#9333ea', '#0284c7', '#ca8a04',
]


def _color_for_org_index(index):
    return ORG_CHART_PALETTE[index % len(ORG_CHART_PALETTE)]


FONCTIONNEL_COLOR = '#16a34a'
NON_FONCTIONNEL_COLOR = '#dc2626'


def _est_fonctionnel_pour_annee(statut, year, current_year):
    """Indique si un ouvrage doit etre compte comme fonctionnel pour `year`.

    `statut` est l'entree de get_statuts_fonctionnel_bulk() pour l'ouvrage
    (statut ACTUEL : case manuelle / chantier actif, sans historique).

    - Chantier actif : situation ponctuelle, l'ouvrage n'est non fonctionnel
      que pour l'annee en cours ; les annees passees suivent la case manuelle.
    - Case manuelle : appliquee a toutes les annees.
    """
    if statut.get('chantier_actif') and year != current_year:
        return not statut.get('marque_manuel', False)
    return statut.get('fonctionnel', True)


def _population_par_ouvrage(ouvrage_ids):
    """Population desservie par ouvrage.

    Somme des habitants des parcelles rattachees a un point d'eau branche
    (datebranchement renseigne) de l'ouvrage, sans doublonner une parcelle
    partagee par plusieurs points d'eau du meme ouvrage.
    """
    ouvrage_ids = [oid for oid in ouvrage_ids if oid]
    if not ouvrage_ids:
        return {}

    ouvrage_parcelles = defaultdict(set)
    points = PointEau.objects.filter(
        ouvrage_id__in=ouvrage_ids,
        parcelle_id__isnull=False,
        datebranchement__isnull=False,
    ).values_list('ouvrage_id', 'parcelle_id')

    all_parcelle_ids = set()
    for ouvrage_id, parcelle_id in points:
        ouvrage_key = str(ouvrage_id)
        ouvrage_parcelles[ouvrage_key].add(parcelle_id)
        all_parcelle_ids.add(parcelle_id)

    parcelles_habitants = {
        row['id']: int(row['nombre_habitants'] or 0)
        for row in Parcelle.objects.filter(id__in=all_parcelle_ids).values('id', 'nombre_habitants')
    }

    return {
        ouvrage_key: sum(parcelles_habitants.get(pid, 0) for pid in parcelle_ids)
        for ouvrage_key, parcelle_ids in ouvrage_parcelles.items()
    }


def build_modalites_gestion_analyse_payload(request):
    base_modalites_qs, allowed_organisation_ids = _base_modalites_queryset(request.user)
    default_organisation_id = get_default_gestionnaire_filter_value(
        request.user,
        allowed_organisation_ids,
    )
    organisation_id = _normalize_filter_value(
        request.GET.get('organisation_id', default_organisation_id)
    )
    if allowed_organisation_ids is not None:
        allowed_ids_as_str = {str(item) for item in allowed_organisation_ids}
        if organisation_id and organisation_id not in allowed_ids_as_str:
            organisation_id = default_organisation_id

    region_id = _normalize_filter_value(request.GET.get('region_id', ''))
    district_id = _normalize_filter_value(request.GET.get('district_id', ''))
    commune_id = _normalize_filter_value(request.GET.get('commune_id', ''))

    accessible_ouvrage_ids = (
        base_modalites_qs.values_list('ouvrage_id', flat=True).distinct()
    )
    ouvrages_accessibles = Ouvrage.objects.filter(
        id__in=accessible_ouvrage_ids,
        type_ouvrage__existe=True,
    ).select_related('type_ouvrage')

    ouvrages_for_geo_options = ouvrages_accessibles
    if organisation_id:
        ouvrages_for_geo_options = ouvrages_for_geo_options.filter(
            id__in=base_modalites_qs.filter(
                gestionnaire_id=organisation_id
            ).values_list('ouvrage_id', flat=True)
        )

    regions, districts, communes = _geo_filter_options(
        ouvrages_for_geo_options,
        region_id=region_id,
        district_id=district_id,
    )

    ouvrages_geo_scope = _apply_geo_filters_to_ouvrages(
        ouvrages_accessibles,
        region_id=region_id,
        district_id=district_id,
        commune_id=commune_id,
    )
    ouvrage_ids_geo_scope = _extract_ouvrage_ids(ouvrages_geo_scope)

    modalites_geo_scope = base_modalites_qs.filter(ouvrage_id__in=ouvrage_ids_geo_scope)
    organisations = _organisation_filter_options_from_modalites(
        modalites_geo_scope,
        allowed_organisation_ids,
    )

    modalites_scope_qs = modalites_geo_scope
    if organisation_id:
        modalites_scope_qs = modalites_scope_qs.filter(gestionnaire_id=organisation_id)

    modalites_scope = list(
        modalites_scope_qs.order_by('ouvrage__nom_ouvrage', 'date_debut', 'id')
    )
    annees_disponibles = _extract_available_years(modalites_scope)

    annee_from_raw = str(request.GET.get('annee_from', '')).strip()
    annee_to_raw = str(request.GET.get('annee_to', '')).strip()

    if not annee_to_raw and annees_disponibles:
        annee_to_raw = str(annees_disponibles[0])
    if not annee_from_raw and len(annees_disponibles) > 1:
        annee_from_raw = str(annees_disponibles[1])
    elif not annee_from_raw and annees_disponibles:
        annee_from_raw = str(annees_disponibles[0])

    try:
        annee_from = int(annee_from_raw) if annee_from_raw else None
    except ValueError:
        annee_from = None
    try:
        annee_to = int(annee_to_raw) if annee_to_raw else None
    except ValueError:
        annee_to = None

    if annee_from is not None and annee_to is not None and annee_from > annee_to:
        annee_from, annee_to = annee_to, annee_from
        annee_from_raw, annee_to_raw = str(annee_from), str(annee_to)

    if annee_from is not None and annee_to is not None:
        multi_start = annee_from
        multi_end = annee_to
    elif annee_to is not None:
        multi_start = annee_to
        multi_end = annee_to
    elif annee_from is not None:
        multi_start = annee_from
        multi_end = annee_from
    elif annees_disponibles:
        multi_start = annees_disponibles[-1]
        multi_end = annees_disponibles[0]
    else:
        multi_start = None
        multi_end = None

    multi_years = []
    if multi_start is not None and multi_end is not None:
        multi_years = list(range(multi_start, multi_end + 1))

    current_year = timezone.localdate().year
    year_presence = {year: set() for year in multi_years}
    detail_by_ouvrage_year = defaultdict(_new_detail_bucket)

    # Suivi par organisation (gestionnaire) pour le graphique d'evolution annuelle.
    org_names = {}
    org_year_ouvrages = defaultdict(lambda: defaultdict(set))

    for modalite in modalites_scope:
        if not modalite.date_debut or not multi_years:
            continue

        start_year = modalite.date_debut.year
        end_year = modalite.date_fin.year if modalite.date_fin else current_year
        effective_start = max(start_year, multi_start)
        effective_end = min(end_year, multi_end)

        if effective_start > effective_end:
            continue

        gestionnaire_nom = (
            modalite.gestionnaire.nom_organisation
            if modalite.gestionnaire and modalite.gestionnaire.nom_organisation
            else 'Non specifie'
        )
        gestionnaire_key = str(modalite.gestionnaire_id) if modalite.gestionnaire_id else 'sans_gestionnaire'
        org_names[gestionnaire_key] = gestionnaire_nom
        type_gestion_label = modalite.get_type_gestion_display()
        modalite_paiement_label = (
            modalite.get_modalitepaiement_display()
            if modalite.modalitepaiement else 'Non specifie'
        )
        statut_label = modalite.get_statut_display()
        ouvrage_id = str(modalite.ouvrage_id)

        for year in range(effective_start, effective_end + 1):
            year_presence[year].add(ouvrage_id)
            org_year_ouvrages[gestionnaire_key][year].add(ouvrage_id)
            detail = detail_by_ouvrage_year[(ouvrage_id, year)]
            detail['gestionnaires'].add(gestionnaire_nom)
            detail['types_gestion'].add(type_gestion_label)
            detail['modalites_paiement'].add(modalite_paiement_label)
            detail['statuts'].add(statut_label)
            detail['lignes'] += 1

    # Population desservie (habitants) par ouvrage, calculee une seule fois
    # pour tous les ouvrages presents sur la periode analysee.
    tous_ouvrages_ids = {
        ouvrage_id
        for ouvrages_annee in year_presence.values()
        for ouvrage_id in ouvrages_annee
    }
    population_par_ouvrage = _population_par_ouvrage(tous_ouvrages_ids)
    statuts_fonctionnel = get_statuts_fonctionnel_bulk(list(tous_ouvrages_ids))

    # Evolution annuelle globale, ventilee fonctionnel / non fonctionnel.
    fonct_ouvrages, non_fonct_ouvrages = [], []
    fonct_population, non_fonct_population = [], []
    for year in multi_years:
        nb_f = nb_nf = pop_f = pop_nf = 0
        for ouvrage_id in year_presence.get(year, set()):
            population = population_par_ouvrage.get(ouvrage_id, 0)
            statut = statuts_fonctionnel.get(ouvrage_id, {})
            if _est_fonctionnel_pour_annee(statut, year, current_year):
                nb_f += 1
                pop_f += population
            else:
                nb_nf += 1
                pop_nf += population
        fonct_ouvrages.append(nb_f)
        non_fonct_ouvrages.append(nb_nf)
        fonct_population.append(pop_f)
        non_fonct_population.append(pop_nf)

    def _fonctionnalite_datasets(data_f, data_nf):
        # Courbes superposees (non empilees : chacune dans sa propre pile).
        return [
            {'label': 'Fonctionnels', 'data': data_f, 'type': 'line', 'fill': False,
             'borderColor': FONCTIONNEL_COLOR, 'backgroundColor': FONCTIONNEL_COLOR,
             'borderWidth': 3, 'tension': 0.25, 'stack': 'fonctionnels', 'order': 0},
            {'label': 'Non fonctionnels', 'data': data_nf, 'type': 'line', 'fill': False,
             'borderColor': NON_FONCTIONNEL_COLOR, 'backgroundColor': NON_FONCTIONNEL_COLOR,
             'borderWidth': 3, 'borderDash': [6, 4], 'tension': 0.25,
             'stack': 'non_fonctionnels', 'order': 0},
        ]

    # Construction des datasets Chart.js (aires empilees): evolution annuelle
    # par organisation du nombre d'ouvrages et de la population desservie.
    organisations_evolution_chart_labels = [str(year) for year in multi_years]
    organisations_evolution_ouvrages_datasets = []
    organisations_evolution_population_datasets = []

    org_keys_sorted = sorted(
        org_year_ouvrages.keys(),
        key=lambda key: (
            -sum(len(ouvrages) for ouvrages in org_year_ouvrages[key].values()),
            org_names.get(key, '').lower(),
        ),
    )

    for index, gestionnaire_key in enumerate(org_keys_sorted):
        org_label = org_names.get(gestionnaire_key, 'Non specifie')
        color = _color_for_org_index(index)
        ouvrages_par_annee_org = org_year_ouvrages[gestionnaire_key]

        ouvrages_data = [
            len(ouvrages_par_annee_org.get(year, set())) for year in multi_years
        ]
        population_data = [
            sum(
                population_par_ouvrage.get(ouvrage_id, 0)
                for ouvrage_id in ouvrages_par_annee_org.get(year, set())
            )
            for year in multi_years
        ]

        if not any(ouvrages_data):
            continue

        organisations_evolution_ouvrages_datasets.append({
            'label': org_label,
            'data': ouvrages_data,
            'type': 'line',
            'fill': 'stack',
            'borderColor': color,
            'backgroundColor': color + '66',
            'borderWidth': 1,
            'pointRadius': 0,
            'tension': 0.25,
            'stack': 'organisations',
            'order': 1,
        })
        organisations_evolution_population_datasets.append({
            'label': org_label,
            'data': population_data,
            'type': 'line',
            'fill': 'stack',
            'borderColor': color,
            'backgroundColor': color + '66',
            'borderWidth': 1,
            'pointRadius': 0,
            'tension': 0.25,
            'stack': 'organisations',
            'order': 1,
        })

    if organisations_evolution_ouvrages_datasets:
        organisations_evolution_ouvrages_datasets += _fonctionnalite_datasets(
            fonct_ouvrages, non_fonct_ouvrages)
        organisations_evolution_population_datasets += _fonctionnalite_datasets(
            fonct_population, non_fonct_population)

    ouvrages_par_annee = {
        year: year_presence.get(year, set()) for year in multi_years
    }
    ouvrages_depart = ouvrages_par_annee.get(annee_from, set()) if annee_from is not None else set()
    ouvrages_arrivee = ouvrages_par_annee.get(annee_to, set()) if annee_to is not None else set()
    ouvrages_communs = ouvrages_depart & ouvrages_arrivee
    ouvrages_uniquement_depart = ouvrages_depart - ouvrages_arrivee
    ouvrages_uniquement_arrivee = ouvrages_arrivee - ouvrages_depart

    ouvrages_uniquement_depart_rows = _augment_rows_with_year_detail(
        _build_ouvrage_rows(ouvrages_uniquement_depart),
        detail_by_ouvrage_year,
        annee_from,
    )
    ouvrages_uniquement_arrivee_rows = _augment_rows_with_year_detail(
        _build_ouvrage_rows(ouvrages_uniquement_arrivee),
        detail_by_ouvrage_year,
        annee_to,
    )

    yearly_counts_rows = []
    yearly_max_count = max((len(ids) for ids in ouvrages_par_annee.values()), default=0)
    depart_count = len(ouvrages_depart)
    for year in multi_years:
        count = len(ouvrages_par_annee.get(year, set()))
        yearly_counts_rows.append({
            'annee': year,
            'count': count,
            'relative_pct': round((count * 100) / yearly_max_count, 1) if yearly_max_count else 0,
            'delta_vs_depart': count - depart_count,
            'pct_vs_depart': round((count * 100) / depart_count, 1) if depart_count else 0,
        })

    coverage_rows = []
    if multi_years and ouvrages_depart:
        coverage_rows = _augment_rows_with_year_detail(
            _build_ouvrage_rows(ouvrages_depart),
            detail_by_ouvrage_year,
            annee_from,
        )

        for row in coverage_rows:
            ouvrage_id = row['ouvrage_id']
            coverage = []
            missing_years = []
            present_years = []
            first_missing_year = None
            gap_seen = False
            reappears_after_gap = False

            for year in multi_years:
                present = ouvrage_id in ouvrages_par_annee.get(year, set())
                coverage.append({
                    'year': year,
                    'present': present,
                })
                if present:
                    present_years.append(year)
                    if gap_seen:
                        reappears_after_gap = True
                else:
                    gap_seen = True
                    if year != annee_from:
                        missing_years.append(year)
                        if first_missing_year is None:
                            first_missing_year = year

            row['coverage'] = coverage
            row['present_years_display'] = (
                ', '.join(str(year) for year in present_years) if present_years else '-'
            )
            row['missing_years_display'] = (
                ', '.join(str(year) for year in missing_years) if missing_years else '-'
            )
            row['first_missing_year'] = first_missing_year or ''
            row['absent_years_count'] = len(missing_years)
            row['reappears_after_gap'] = reappears_after_gap

        coverage_rows.sort(
            key=lambda row: (
                0 if row['absent_years_count'] > 0 else 1,
                row['first_missing_year'] or 9999,
                row['region_nom'] or '',
                row['district_nom'] or '',
                row['commune_nom'] or '',
                (row['nom_ouvrage'] or '').lower(),
            )
        )

    presence_complete_ids = set()
    if multi_years:
        presence_complete_ids = set(ouvrages_depart)
        for year in multi_years[1:]:
            presence_complete_ids &= ouvrages_par_annee.get(year, set())

    coverage_rows_missing = [row for row in coverage_rows if row['absent_years_count'] > 0]
    coverage_rows_complete = [row for row in coverage_rows if row['absent_years_count'] == 0]
    coverage_rows_reappearing = [row for row in coverage_rows if row['reappears_after_gap']]

    scope_ouvrage_ids = {
        str(item.ouvrage_id) for item in modalites_scope if item.ouvrage_id
    }

    context = {
        'title': 'Analyse des modalites de gestion',
        'organisations': organisations,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'annees_disponibles': annees_disponibles,
        'yearly_counts_rows': yearly_counts_rows,
        'yearly_max_count': yearly_max_count,
        'ouvrages_uniquement_depart': ouvrages_uniquement_depart_rows,
        'ouvrages_uniquement_arrivee': ouvrages_uniquement_arrivee_rows,
        'coverage_rows': coverage_rows,
        'coverage_rows_missing': coverage_rows_missing,
        'coverage_rows_complete': coverage_rows_complete,
        'coverage_rows_reappearing': coverage_rows_reappearing,
        'coverage_empty_colspan': len(multi_years) + 8,
        'organisations_evolution_chart_labels': organisations_evolution_chart_labels,
        'organisations_evolution_ouvrages_datasets': organisations_evolution_ouvrages_datasets,
        'organisations_evolution_population_datasets': organisations_evolution_population_datasets,
        'stats': {
            'ouvrages_filtres': len(scope_ouvrage_ids),
            'lignes_modalites': len(modalites_scope),
            'present_depart': len(ouvrages_depart),
            'present_arrivee': len(ouvrages_arrivee),
            'communs': len(ouvrages_communs),
            'uniquement_depart': len(ouvrages_uniquement_depart),
            'uniquement_arrivee': len(ouvrages_uniquement_arrivee),
            'maintenus_toute_periode': len(presence_complete_ids),
            'absents_en_cours_periode': len(coverage_rows_missing),
            'reapparitions': len(coverage_rows_reappearing),
        },
        'multi_period': {
            'start': multi_start,
            'end': multi_end,
            'years_count': len(multi_years),
        },
        'filters': {
            'organisation_id': organisation_id,
            'region_id': region_id,
            'district_id': district_id,
            'commune_id': commune_id,
            'annee_from': annee_from_raw,
            'annee_to': annee_to_raw,
        },
    }
    return context


@employe_required
def modalites_gestion_analyse(request):
    context = build_modalites_gestion_analyse_payload(request)
    return render(request, 'organization/modalites_gestion_analyse.html', context)
