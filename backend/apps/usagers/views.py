"""
Vues pour la gestion des représentants des usagers et leurs avis
"""

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg, Subquery
from django.core.paginator import Paginator
from django.db import transaction, connection
from django.utils import timezone
from decimal import Decimal
from collections import defaultdict
import openpyxl
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime, date
import io
import json

from .models import RepresentantUsager, AvisRepresentant, Reunion
from apps.geography.models import Village, Commune, District, Region
from apps.employees.models import Employe
from apps.organization.models import Organisation
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_default_gestionnaire_filter_value,
    get_user_accessible_gestionnaire_ids,
)

def parse_year_filter(value):
    value = (value or '').strip()
    if not value:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_effective_gestionnaire_ids_for_scope(user, organisation_id=''):
    requested = str(organisation_id or '').strip()
    if requested == 'all':
        requested = ''

    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if not requested:
        return gestionnaire_ids

    if gestionnaire_ids is None:
        return [requested]

    allowed_ids = {str(item) for item in gestionnaire_ids if item}
    return [requested] if requested in allowed_ids else []


def _get_allowed_ouvrage_ids_for_scope(user, organisation_id=''):
    from apps.billing.models import ModaliteGestion

    effective_gestionnaire_ids = _get_effective_gestionnaire_ids_for_scope(user, organisation_id=organisation_id)
    modalites_qs = ModaliteGestion.objects.filter(
        date_fin__isnull=True
    ).exclude(
        ouvrage_id__isnull=True
    )

    if effective_gestionnaire_ids is None:
        pass
    elif not effective_gestionnaire_ids:
        return set()
    else:
        modalites_qs = modalites_qs.filter(gestionnaire_id__in=effective_gestionnaire_ids)

    ouvrage_ids = set(modalites_qs.values_list('ouvrage_id', flat=True).distinct())
    scoped_ids = apply_user_responsable_ouvrage_scope(ouvrage_ids, user)
    return ouvrage_ids if scoped_ids is None else set(scoped_ids)


def _get_allowed_village_ids_for_scope(user, organisation_id=''):
    from apps.billing.models import PointEau

    allowed_ouvrage_ids = _get_allowed_ouvrage_ids_for_scope(user, organisation_id=organisation_id)
    if not allowed_ouvrage_ids:
        return set()

    return set(
        PointEau.objects.filter(
            ouvrage_id__in=allowed_ouvrage_ids,
            parcelle__village_id__isnull=False,
        ).values_list('parcelle__village_id', flat=True).distinct()
    )


def _filter_representants_queryset_for_user(queryset, user, organisation_id=''):
    allowed_village_ids = _get_allowed_village_ids_for_scope(user, organisation_id=organisation_id)
    if not allowed_village_ids:
        return queryset.none()
    return queryset.filter(village_id__in=allowed_village_ids)


def _filter_avis_queryset_for_user(queryset, user, organisation_id=''):
    allowed_village_ids = _get_allowed_village_ids_for_scope(user, organisation_id=organisation_id)
    if not allowed_village_ids:
        return queryset.none()
    return queryset.filter(representant__village_id__in=allowed_village_ids)


def build_representants_queryset(region_id='', district_id='', commune_id='', village_id='', organisation_id='', actif='tous', search='', user=None):
    queryset = RepresentantUsager.objects.select_related(
        'village',
        'village__fokontany',
        'village__fokontany__commune',
        'village__fokontany__commune__district'
    ).all()

    if user is not None:
        queryset = _filter_representants_queryset_for_user(
            queryset,
            user,
            organisation_id=organisation_id,
        )

    if region_id:
        queryset = queryset.filter(village__fokontany__commune__district__region_id=region_id)

    if district_id:
        queryset = queryset.filter(village__fokontany__commune__district_id=district_id)

    if commune_id:
        queryset = queryset.filter(village__fokontany__commune_id=commune_id)

    if village_id:
        queryset = queryset.filter(village_id=village_id)
    if organisation_id:
        from apps.billing.models import PointEau
        village_ids = PointEau.objects.filter(
            ouvrage__modalites_gestion__gestionnaire_id=organisation_id,
            ouvrage__modalites_gestion__date_fin__isnull=True
        ).values_list('parcelle__village_id', flat=True).distinct()
        queryset = queryset.filter(village_id__in=village_ids)


    if actif == 'oui':
        queryset = queryset.filter(actif=True)
    elif actif == 'non':
        queryset = queryset.filter(actif=False)

    if search:
        queryset = queryset.filter(
            Q(nom__icontains=search)
            | Q(contact__icontains=search)
            | Q(village__nom_village__icontains=search)
            | Q(village__fokontany__commune__nom_commune__icontains=search)
            | Q(village__fokontany__commune__district__nom_district__icontains=search)
        )

    return queryset


def get_canonical_avis_queryset(queryset):
    ordered = queryset.order_by('representant_id', 'date_avis', '-updated_at', '-created_at', '-id')

    if connection.vendor == 'postgresql':
        canonical_ids = ordered.distinct('representant_id', 'date_avis').values_list('id', flat=True)
        return queryset.filter(id__in=Subquery(canonical_ids))

    seen = set()
    ids = []
    for avis in ordered:
        key = (avis.representant_id, avis.date_avis)
        if key in seen:
            continue
        seen.add(key)
        ids.append(avis.id)

    return queryset.filter(id__in=ids)


def get_filtered_avis_queryset(representants_queryset, annee=None):
    queryset = get_canonical_avis_queryset(
        AvisRepresentant.objects.select_related(
            'representant',
            'representant__village',
            'representant__village__fokontany',
            'representant__village__fokontany__commune',
            'representant__village__fokontany__commune__district',
            'employe'
        ).filter(representant__in=representants_queryset)
    )

    if annee:
        queryset = queryset.filter(date_avis__year=annee)

    return queryset


def get_available_avis_years(representants_queryset):
    years = (
        AvisRepresentant.objects.filter(representant__in=representants_queryset, date_avis__isnull=False)
        .order_by()
        .values_list('date_avis__year', flat=True)
        .distinct()
    )
    return sorted({year for year in years if year}, reverse=True)


def get_ouvrages_by_village_ids(village_ids, organisation_id=None, include_meta=False, user=None):
    from apps.billing.models import PointEau

    village_ids = [village_id for village_id in village_ids if village_id]
    ouvrages_by_village = defaultdict(dict)

    if not village_ids:
        return {}

    queryset = PointEau.objects.filter(parcelle__village_id__in=village_ids, ouvrage__isnull=False)

    if user is not None:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids_for_scope(user, organisation_id=organisation_id)
        if not allowed_ouvrage_ids:
            return {
                village_id: ([{'id': '', 'nom': 'Sans ouvrage', 'saisonnier': False}] if include_meta else ['Sans ouvrage'])
                for village_id in village_ids
            }
        queryset = queryset.filter(ouvrage_id__in=allowed_ouvrage_ids)
    elif organisation_id:
        queryset = queryset.filter(
            ouvrage__modalites_gestion__gestionnaire_id=organisation_id,
            ouvrage__modalites_gestion__date_fin__isnull=True
        )

    points_eau = queryset.values(
        'ouvrage_id',
        'ouvrage__nom_ouvrage',
        'ouvrage__saisonnier',
        'parcelle__village_id',
    ).distinct()

    for row in points_eau:
        village_id = row.get('parcelle__village_id')
        ouvrage_id = row.get('ouvrage_id')
        nom = (row.get('ouvrage__nom_ouvrage') or '').strip()
        if not village_id or not ouvrage_id or not nom:
            continue
        ouvrages_by_village[village_id][str(ouvrage_id)] = {
            'id': str(ouvrage_id),
            'nom': nom,
            'saisonnier': bool(row.get('ouvrage__saisonnier')),
        }

    result = {}
    for village_id in village_ids:
        ouvrages = sorted(
            ouvrages_by_village.get(village_id, {}).values(),
            key=lambda item: (item.get('nom') or '').lower(),
        )
        if include_meta:
            result[village_id] = ouvrages or [{'id': '', 'nom': 'Sans ouvrage', 'saisonnier': False}]
        else:
            result[village_id] = [item['nom'] for item in ouvrages] or ['Sans ouvrage']

    return result


def clean_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    value = str(value).strip()

    # Format Excel "AAA-MM-JJ HH:MM:SS"
    if " " in value:
        value = value.split(" ")[0]

    # Format AAAA-MM-JJ
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except:
        pass

    # Format JJ/MM/AAAA
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except:
        pass

    raise ValueError(f"Format de date invalide '{value}' (attendu: JJ/MM/AAAA ou AAAA-MM-JJ)")


def parse_bool_flag(value, default=None):
    if value is None:
        return default

    normalized = str(value).strip().lower()
    if not normalized:
        return default

    if normalized in {'oui', 'yes', '1', 'true', 'vrai', 'actif', 'active'}:
        return True
    if normalized in {'non', 'no', '0', 'false', 'faux', 'inactif', 'inactive'}:
        return False
    return default


def resolve_representant_active_flag(date_debut, date_fin, explicit_actif=None, fallback=True):
    if date_debut is not None or date_fin is not None:
        today = timezone.localdate()
        debut_ok = date_debut is None or date_debut <= today
        fin_ok = date_fin is None or date_fin >= today
        return debut_ok and fin_ok

    if explicit_actif is None:
        return fallback

    return explicit_actif


def build_stacked_100_chart_payload(labels, positive_counts, negative_counts):
    payload = {
        'labels': [],
        'positive_counts': [],
        'negative_counts': [],
        'positive_percentages': [],
        'negative_percentages': [],
        'totals': [],
    }

    for label, positive_count, negative_count in zip(labels, positive_counts, negative_counts):
        positive_value = int(positive_count or 0)
        negative_value = int(negative_count or 0)
        total_value = positive_value + negative_value

        payload['labels'].append(label)
        payload['positive_counts'].append(positive_value)
        payload['negative_counts'].append(negative_value)
        payload['totals'].append(total_value)

        if total_value > 0:
            payload['positive_percentages'].append(round((positive_value / total_value) * 100, 2))
            payload['negative_percentages'].append(round((negative_value / total_value) * 100, 2))
        else:
            payload['positive_percentages'].append(0)
            payload['negative_percentages'].append(0)

    return payload


def build_communes_stacked_chart_payload(avis_queryset):
    criteria = [
        ('Quantite', 'quantite_ok'),
        ('Qualite', 'qualite_ok'),
        ('Delai', 'delai_reparation_ok'),
        ('Relation', 'relation_gestionnaire_ok'),
    ]
    stats_by_commune = defaultdict(
        lambda: {
            'region': '',
            'district': '',
            'commune': '',
            'criteria': {
                criterion_label: {'positive': 0, 'negative': 0}
                for criterion_label, _ in criteria
            },
        }
    )

    for avis in avis_queryset:
        region_nom = ''
        district_nom = ''
        commune_nom = ''
        if (
            avis.representant
            and avis.representant.village
            and avis.representant.village.fokontany
            and avis.representant.village.fokontany.commune
        ):
            commune = avis.representant.village.fokontany.commune
            commune_nom = commune.nom_commune or ''
            if commune.district:
                district_nom = commune.district.nom_district or ''
                if commune.district.region:
                    region_nom = commune.district.region.nom_region or ''

        region_label = region_nom.strip() or 'Region non specifiee'
        district_label = district_nom.strip() or 'District non specifie'
        commune_label = commune_nom.strip() or 'Commune non specifiee'
        item = stats_by_commune[(region_label, district_label, commune_label)]
        item['region'] = region_label
        item['district'] = district_label
        item['commune'] = commune_label

        for criterion_label, field_name in criteria:
            if getattr(avis, field_name, False):
                item['criteria'][criterion_label]['positive'] += 1
            else:
                item['criteria'][criterion_label]['negative'] += 1

    ordered_stats = sorted(
        stats_by_commune.values(),
        key=lambda item: (
            item['region'].lower(),
            item['district'].lower(),
            item['commune'].lower(),
        )
    )

    labels = []
    positive_counts = []
    negative_counts = []

    for item in ordered_stats:
        geographic_label = f"{item['district']} / {item['region']}"
        for criterion_label, _ in criteria:
            criterion_stats = item['criteria'][criterion_label]
            labels.append([
                item['commune'],
                criterion_label,
                geographic_label,
            ])
            positive_counts.append(criterion_stats['positive'])
            negative_counts.append(criterion_stats['negative'])

    return build_stacked_100_chart_payload(labels, positive_counts, negative_counts)


def get_representant_geography_names(representant):
    region_nom = ''
    district_nom = ''
    commune_nom = ''

    village = representant.village if representant else None
    if village and village.fokontany and village.fokontany.commune:
        commune = village.fokontany.commune
        commune_nom = commune.nom_commune or ''
        if commune.district:
            district_nom = commune.district.nom_district or ''
            if commune.district.region:
                region_nom = commune.district.region.nom_region or ''

    return {
        'region': region_nom.strip(),
        'district': district_nom.strip(),
        'commune': commune_nom.strip(),
    }


def build_avis_analysis_rows(avis_list):
    criteria = [
        ('Quantite', 'quantite_ok'),
        ('Qualite', 'qualite_ok'),
        ('Delai reparation', 'delai_reparation_ok'),
        ('Relation gestionnaire', 'relation_gestionnaire_ok'),
    ]
    criterion_order = {label: index for index, (label, _) in enumerate(criteria)}
    criteria_summary = {
        label: {'positive': 0, 'negative': 0}
        for label, _ in criteria
    }
    commune_summary = defaultdict(lambda: {'positive': 0, 'negative': 0})

    for avis in avis_list:
        geography = get_representant_geography_names(avis.representant)
        region_label = geography['region'] or 'Region non specifiee'
        district_label = geography['district'] or 'District non specifie'
        commune_label = geography['commune'] or 'Commune non specifiee'

        for criterion_label, field_name in criteria:
            is_positive = bool(getattr(avis, field_name, False))
            if is_positive:
                criteria_summary[criterion_label]['positive'] += 1
            else:
                criteria_summary[criterion_label]['negative'] += 1

            commune_summary[(region_label, district_label, commune_label, criterion_label)][
                'positive' if is_positive else 'negative'
            ] += 1

    criterion_rows = []
    for criterion_label, _ in criteria:
        positive_count = criteria_summary[criterion_label]['positive']
        negative_count = criteria_summary[criterion_label]['negative']
        total_count = positive_count + negative_count
        criterion_rows.append({
            'criterion': criterion_label,
            'positive': positive_count,
            'negative': negative_count,
            'positive_pct': round((positive_count / total_count) * 100, 1) if total_count else 0,
            'negative_pct': round((negative_count / total_count) * 100, 1) if total_count else 0,
        })

    commune_rows = []
    for region_label, district_label, commune_label, criterion_label in sorted(
        commune_summary.keys(),
        key=lambda key: (
            key[0].lower(),
            key[1].lower(),
            key[2].lower(),
            criterion_order[key[3]],
        )
    ):
        values = commune_summary[(region_label, district_label, commune_label, criterion_label)]
        positive_count = values['positive']
        negative_count = values['negative']
        total_count = positive_count + negative_count
        commune_rows.append({
            'region': region_label,
            'district': district_label,
            'commune': commune_label,
            'criterion': criterion_label,
            'positive': positive_count,
            'negative': negative_count,
            'positive_pct': round((positive_count / total_count) * 100, 1) if total_count else 0,
            'negative_pct': round((negative_count / total_count) * 100, 1) if total_count else 0,
            'chart_label': f"{district_label} / {commune_label} - {criterion_label}",
        })

    return criterion_rows, commune_rows


def add_export_stacked_chart(
    ws,
    title,
    category_col,
    data_start_col,
    header_row,
    data_start_row,
    data_end_row,
    anchor,
    y_axis_title,
    x_axis_title='',
    show_data_labels=True,
    grouping='stacked',
):
    if data_end_row < data_start_row:
        return

    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.grouping = grouping
    chart.overlap = 100 if grouping in ('stacked', 'percentStacked') else 0
    chart.title = title
    chart.y_axis.title = y_axis_title
    if x_axis_title:
        chart.x_axis.title = x_axis_title
    chart.height = 7
    chart.width = 14

    data = Reference(
        ws,
        min_col=data_start_col,
        max_col=data_start_col + 1,
        min_row=header_row,
        max_row=data_end_row,
    )
    categories = Reference(
        ws,
        min_col=category_col,
        max_col=category_col,
        min_row=data_start_row,
        max_row=data_end_row,
    )
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)
    if show_data_labels:
        chart.dLbls = DataLabelList()
        chart.dLbls.showVal = True

    ws.add_chart(chart, anchor)

@login_required
def representants_list(request):
    """Page de gestion des représentants avec liste des avis en cascade"""

    # Filtres
    region_id = request.GET.get('region', '').strip()
    district_id = request.GET.get('district', '').strip()
    commune_id = request.GET.get('commune', '').strip()
    village_id = request.GET.get('village', '').strip()
    organisation_id = request.GET.get('organisation', '').strip()
    search = request.GET.get('search', '').strip()
    actif = request.GET.get('actif', 'tous').strip()
    annee = parse_year_filter(request.GET.get('annee'))

    # Par défaut sur l'organisation de l'employé si pas de filtre
    if not organisation_id and not request.GET.get('clear'):
        organisation_id = get_default_gestionnaire_filter_value(request.user)

    default_organisation_id = get_default_gestionnaire_filter_value(request.user) or ''
    if not organisation_id or organisation_id == 'all':
        organisation_id = default_organisation_id

    allowed_org_ids = get_user_accessible_gestionnaire_ids(request.user)
    if organisation_id and allowed_org_ids is not None:
        allowed_org_ids_set = {str(item) for item in allowed_org_ids if item}
        if organisation_id not in allowed_org_ids_set:
            organisation_id = default_organisation_id

    representants_base = build_representants_queryset(
        region_id=region_id,
        district_id=district_id,
        commune_id=commune_id,
        village_id=village_id,
        organisation_id=organisation_id,
        actif=actif,
        search=search,
        user=request.user,
    )
    years_available = get_available_avis_years(representants_base)
    # Ajouter l'année sélectionnée et garantir l'unicité avec set()
    if annee:
        years_set = set(years_available)
        years_set.add(annee)
        years_available = sorted(years_set, reverse=True)
    representants = representants_base

    # Appliquer les filtres géographiques
    if region_id:
        representants = representants.filter(village__fokontany__commune__district__region_id=region_id)

    if district_id:
        representants = representants.filter(village__fokontany__commune__district_id=district_id)

    if commune_id:
        representants = representants.filter(village__fokontany__commune_id=commune_id)

    if village_id:
        representants = representants.filter(village_id=village_id)

    if actif == 'oui':
        representants = representants.filter(actif=True)
    elif actif == 'non':
        representants = representants.filter(actif=False)

    if search:
        representants = representants.filter(
            Q(nom__icontains=search) |
            Q(contact__icontains=search) |
            Q(village__nom_village__icontains=search) |
            Q(village__fokontany__commune__nom_commune__icontains=search) |
            Q(village__fokontany__commune__district__nom_district__icontains=search)
        )

    # Conserver un queryset "base" (sans jointure avis) pour les comptages
    representants_base = representants

    # Annoter avec le nombre d'avis pour l'affichage détaillé
    avis_queryset = get_filtered_avis_queryset(representants_base, annee=annee)
    avis_counts_by_representant = dict(
        avis_queryset.values('representant_id')
        .annotate(total=Count('id'))
        .values_list('representant_id', 'total')
    )
    representants = list(representants_base)
    for representant in representants:
        representant.nb_avis = avis_counts_by_representant.get(representant.id, 0)

    # Regroupement hiérarchique : District > Commune > Ouvrage > Représentants
    representants_groupes = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))
    # Structure: {district: {commune: {ouvrage: {rep_id: rep_data}}}}
    ouvrages_by_village = get_ouvrages_by_village_ids(
        {representant.village_id for representant in representants},
        organisation_id=organisation_id,
        include_meta=True,
        user=request.user,
    )

    # Éviter d'afficher un représentant plusieurs fois si son village est
    # desservi par plusieurs ouvrages : ne le rattacher qu'au premier ouvrage.
    representants_deja_affiches = set()

    for rep in representants:
        # Récupérer les ouvrages liés au village via Parcelle → PointEau → Ouvrage
        district = rep.village.fokontany.commune.district if rep.village.fokontany and rep.village.fokontany.commune and rep.village.fokontany.commune.district else None
        commune = rep.village.fokontany.commune if rep.village.fokontany and rep.village.fokontany.commune else None

        district_nom = district.nom_district if district else 'District non spécifié'
        commune_nom = commune.nom_commune if commune else 'Commune non spécifiée'

        # Collecter tous les ouvrages uniques pour ce représentant
        ouvrages_trouves = ouvrages_by_village.get(rep.village_id, [{'id': '', 'nom': 'Sans ouvrage', 'saisonnier': False}])

        # Si aucun ouvrage trouvé, ajouter à "Sans ouvrage"

        # Ne rattacher le représentant qu'au premier ouvrage de son village
        # pour éviter tout doublon d'affichage (village multi-ouvrages)
        if str(rep.id) in representants_deja_affiches:
            continue

        ouvrage_item = ouvrages_trouves[0] if ouvrages_trouves else {'id': '', 'nom': 'Sans ouvrage', 'saisonnier': False}
        ouvrage_nom = ouvrage_item.get('nom') or 'Sans ouvrage'
        ouvrage_bucket = representants_groupes[district_nom][commune_nom].setdefault(
            ouvrage_nom,
            {
                'nom': ouvrage_nom,
                'saisonnier': bool(ouvrage_item.get('saisonnier')),
                'representants_by_id': {},
            },
        )
        ouvrage_bucket['saisonnier'] = bool(ouvrage_bucket.get('saisonnier') or ouvrage_item.get('saisonnier'))
        if str(rep.id) not in ouvrage_bucket['representants_by_id']:
            ouvrage_bucket['representants_by_id'][str(rep.id)] = {
                'representant': rep,
                'nb_avis': rep.nb_avis
            }
        representants_deja_affiches.add(str(rep.id))

    # Convertir en structure ordonnée
    groupes_ordonnes = []
    for district_nom in sorted(representants_groupes.keys()):
        communes_data = []
        for commune_nom in sorted(representants_groupes[district_nom].keys()):
            ouvrages_data = []
            for ouvrage_nom in sorted(representants_groupes[district_nom][commune_nom].keys()):
                ouvrage_data = representants_groupes[district_nom][commune_nom][ouvrage_nom]
                reps = list(ouvrage_data['representants_by_id'].values())  # Convertir le dict en liste
                ouvrages_data.append({
                    'nom': ouvrage_data['nom'],
                    'saisonnier': bool(ouvrage_data.get('saisonnier')),
                    'representants': reps,
                    'nb_representants': len(reps)
                })
            communes_data.append({
                'nom': commune_nom,
                'ouvrages': ouvrages_data,
                'nb_ouvrages': len(ouvrages_data)
            })
        groupes_ordonnes.append({
            'nom': district_nom,
            'communes': communes_data,
            'nb_communes': len(communes_data)
        })

    # Listes pour les filtres
    allowed_org_ids = get_user_accessible_gestionnaire_ids(request.user)
    if allowed_org_ids is None:
        organisations = Organisation.objects.filter(type_organisation='gestionnaire')
    else:
        organisations = Organisation.objects.filter(
            type_organisation='gestionnaire',
            id__in=allowed_org_ids,
        )
    organisations = organisations.order_by('nom_organisation')

    villages_scope_qs = Village.objects.select_related(
        'fokontany',
        'fokontany__commune',
        'fokontany__commune__district'
    ).filter(
        id__in=_get_allowed_village_ids_for_scope(request.user, organisation_id=organisation_id)
    )

    region_ids_scope = villages_scope_qs.values_list(
        'fokontany__commune__district__region_id', flat=True
    ).distinct()
    regions = Region.objects.filter(id__in=region_ids_scope).order_by('nom_region')

    districts_scope_qs = villages_scope_qs
    if region_id:
        districts_scope_qs = districts_scope_qs.filter(fokontany__commune__district__region_id=region_id)
    district_ids_scope = districts_scope_qs.values_list(
        'fokontany__commune__district_id', flat=True
    ).distinct()
    districts = District.objects.select_related('region').filter(id__in=district_ids_scope).order_by('nom_district')

    communes_scope_qs = villages_scope_qs
    if region_id:
        communes_scope_qs = communes_scope_qs.filter(fokontany__commune__district__region_id=region_id)
    if district_id:
        communes_scope_qs = communes_scope_qs.filter(fokontany__commune__district_id=district_id)
    commune_ids_scope = communes_scope_qs.values_list(
        'fokontany__commune_id', flat=True
    ).distinct()
    communes = Commune.objects.select_related('district', 'district__region').filter(
        id__in=commune_ids_scope
    ).order_by('nom_commune')

    villages = villages_scope_qs.order_by('nom_village')

    if region_id:
        villages = villages.filter(fokontany__commune__district__region_id=region_id)

    if district_id:
        villages = villages.filter(fokontany__commune__district_id=district_id)

    if commune_id:
        villages = villages.filter(fokontany__commune_id=commune_id)

    # Employés actifs pour les avis
    employes = Employe.objects.filter(salarie=True).order_by('surnom')

    # Statistiques globales (appliquent les filtres)
    stats = {
        'total': representants_base.count(),
        'actifs': representants_base.filter(actif=True).count(),
        'inactifs': representants_base.filter(actif=False).count(),
        'total_avis': avis_queryset.count(),
        # Stats sur les avis
        'avis_positifs': avis_queryset.filter(
            Q(quantite_ok=True) &
            Q(qualite_ok=True) &
            Q(delai_reparation_ok=True) &
            Q(relation_gestionnaire_ok=True) &
            (Q(probleme_technique__isnull=True) | Q(probleme_technique='')) &
            (Q(probleme_recouvrement__isnull=True) | Q(probleme_recouvrement='')) &
            (Q(probleme_regles_utilisation__isnull=True) | Q(probleme_regles_utilisation=''))
        ).count(),
        'avis_negatifs': avis_queryset.filter(
            Q(probleme_technique__isnull=False) & ~Q(probleme_technique='') |
            Q(probleme_recouvrement__isnull=False) & ~Q(probleme_recouvrement='') |
            Q(probleme_regles_utilisation__isnull=False) & ~Q(probleme_regles_utilisation='') |
            (
                Q(quantite_ok=False) &
                Q(qualite_ok=False) &
                Q(delai_reparation_ok=False) &
                Q(relation_gestionnaire_ok=False)
            )
        ).count(),
        'score_moyen': round(
            sum(a.score_satisfaction for a in avis_queryset) / avis_queryset.count() if avis_queryset.count() > 0 else 0,
            2
        ),
        'taux_satisfaction_moyen': round(
            sum(a.pourcentage_satisfaction for a in avis_queryset) / avis_queryset.count() if avis_queryset.count() > 0 else 0,
            1
        ),
        # Détail par critère
        'quantite_ok_count': avis_queryset.filter(quantite_ok=True).count(),
        'qualite_ok_count': avis_queryset.filter(qualite_ok=True).count(),
        'delai_ok_count': avis_queryset.filter(delai_reparation_ok=True).count(),
        'relation_ok_count': avis_queryset.filter(relation_gestionnaire_ok=True).count(),
    }

    # Nombre d'ouvrages distincts concernés par les filtres actifs
    ouvrage_ids_concernes = set()
    for rep in representants:
        for ouvrage_item in ouvrages_by_village.get(rep.village_id, []):
            if ouvrage_item.get('id'):
                ouvrage_ids_concernes.add(ouvrage_item['id'])
    stats['nb_ouvrages'] = len(ouvrage_ids_concernes)

    # Statistiques regroupées par district avec communes
    stats_by_commune = representants_base.values(
        'village__fokontany__commune__district__id',
        'village__fokontany__commune__district__nom_district',
        'village__fokontany__commune__id',
        'village__fokontany__commune__nom_commune'
    ).annotate(
        count=Count('id', distinct=True)
    ).order_by(
        'village__fokontany__commune__district__nom_district',
        '-count'
    )

    # Regrouper par district
    stats_grouped = defaultdict(lambda: {'district': '', 'total': 0, 'communes': []})
    for stat in stats_by_commune:
        district_id_key = stat['village__fokontany__commune__district__id']
        district_nom = stat['village__fokontany__commune__district__nom_district'] or 'Non spécifié'
        commune_nom = stat['village__fokontany__commune__nom_commune'] or 'Non spécifié'
        count = stat['count']

        if not stats_grouped[district_id_key]['district']:
            stats_grouped[district_id_key]['district'] = district_nom

        stats_grouped[district_id_key]['total'] += count
        stats_grouped[district_id_key]['communes'].append({
            'nom': commune_nom,
            'count': count
        })

    # Trier par total décroissant (sans limiter aux top districts)
    stats_repartition = sorted(
        stats_grouped.values(),
        key=lambda x: x['total'],
        reverse=True
    )

    chart_criteres = build_stacked_100_chart_payload(
        ['Quantite', 'Qualite', 'Delai', 'Relation'],
        [
            stats['quantite_ok_count'],
            stats['qualite_ok_count'],
            stats['delai_ok_count'],
            stats['relation_ok_count'],
        ],
        [
            max(0, stats['total_avis'] - stats['quantite_ok_count']),
            max(0, stats['total_avis'] - stats['qualite_ok_count']),
            max(0, stats['total_avis'] - stats['delai_ok_count']),
            max(0, stats['total_avis'] - stats['relation_ok_count']),
        ],
    )
    chart_communes = build_communes_stacked_chart_payload(avis_queryset)

    context = {
        'groupes_ordonnes': groupes_ordonnes,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'villages': villages,
        'employes': employes,
        'current_employe_id': str(request.user.employe.id) if hasattr(request.user, 'employe') and request.user.employe else '',
        'stats': stats,
        'stats_repartition': stats_repartition,
        'selected_region': region_id,
        'selected_district': district_id,
        'selected_commune': commune_id,
        'selected_village': village_id,
        'selected_organisation': organisation_id,
        'organisations': organisations,
        'selected_actif': actif,
        'selected_annee': str(annee) if annee else '',
        'years_available': years_available,
        'search_query': search,
        'export_querystring': request.GET.urlencode(),
        'chart_criteres_stacked_json': json.dumps(chart_criteres),
        'chart_communes_stacked_json': json.dumps(chart_communes),
    }

    return render(request, 'usagers/representants_list.html', context)


@login_required
def representants_reparations_dashboard(request):
    """
    Dashboard combin?:
    - Avis repr?sentants (source usagers)
    - Reparations (source planning)
    - Etat ouvrages via Village -> Parcelle -> PointEau -> Ouvrage
    """
    from apps.billing.models import PointEau, Releve, PaiementForfaitaire, ModaliteGestion
    from apps.accounting.models import BaseDiameX
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
    from apps.planning.models import Planning, PlanningDetail, ActivitePoste, Activite
    from apps.planning.grading import get_ouvrage_grading

    region_id = request.GET.get('region', '').strip()
    district_id = request.GET.get('district', '').strip()
    commune_id = request.GET.get('commune', '').strip()
    search = request.GET.get('search', '').strip()
    actif = request.GET.get('actif', 'tous').strip()
    filter_annee = request.GET.get('annee', str(timezone.localdate().year)).strip()

    try:
        annee = int(filter_annee)
    except Exception:
        annee = timezone.localdate().year

    allowed_ouvrage_ids = _get_allowed_ouvrage_ids_for_scope(request.user)

    # Base de comptage "ouvrages" alignee sur le dashboard:
    # perimetre geographique + organisation, independamment de la presence d'avis.
    all_points_scope_qs = PointEau.objects.filter(ouvrage__isnull=False)
    all_points_scope_qs = all_points_scope_qs.exclude(
        ouvrage__type_ouvrage__nom_type_ouvrage__in=['Potentiel', 'Travaux en cours']
    )
    if allowed_ouvrage_ids is not None:
        all_points_scope_qs = all_points_scope_qs.filter(ouvrage_id__in=allowed_ouvrage_ids)
    if region_id:
        all_points_scope_qs = all_points_scope_qs.filter(
            parcelle__village__fokontany__commune__district__region_id=region_id
        )
    if district_id:
        all_points_scope_qs = all_points_scope_qs.filter(
            parcelle__village__fokontany__commune__district_id=district_id
        )
    if commune_id:
        all_points_scope_qs = all_points_scope_qs.filter(
            parcelle__village__fokontany__commune_id=commune_id
        )
    if search:
        all_points_scope_qs = all_points_scope_qs.filter(
            Q(ouvrage__nom_ouvrage__icontains=search)
            | Q(parcelle__village__nom_village__icontains=search)
            | Q(parcelle__village__fokontany__commune__nom_commune__icontains=search)
            | Q(parcelle__village__fokontany__commune__district__nom_district__icontains=search)
        )
    all_ouvrage_ids_filtered = set(all_points_scope_qs.values_list('ouvrage_id', flat=True).distinct())

    representants_qs = RepresentantUsager.objects.select_related(
        'village',
        'village__fokontany__commune__district__region'
    )
    representants_qs = _filter_representants_queryset_for_user(representants_qs, request.user)

    if actif == 'oui':
        representants_qs = representants_qs.filter(actif=True)
    elif actif == 'non':
        representants_qs = representants_qs.filter(actif=False)

    if region_id:
        representants_qs = representants_qs.filter(village__fokontany__commune__district__region_id=region_id)
    if district_id:
        representants_qs = representants_qs.filter(village__fokontany__commune__district_id=district_id)
    if commune_id:
        representants_qs = representants_qs.filter(village__fokontany__commune_id=commune_id)
    if search:
        representants_qs = representants_qs.filter(
            Q(nom__icontains=search)
            | Q(village__nom_village__icontains=search)
            | Q(village__fokontany__commune__nom_commune__icontains=search)
            | Q(village__fokontany__commune__district__nom_district__icontains=search)
        )

    representants = list(representants_qs)
    rep_ids = [rep.id for rep in representants]
    village_ids = list({rep.village_id for rep in representants if rep.village_id})

    village_ouvrages_qs = PointEau.objects.filter(
        parcelle__village_id__in=village_ids,
        ouvrage__isnull=False
    )
    if allowed_ouvrage_ids is not None:
        village_ouvrages_qs = village_ouvrages_qs.filter(ouvrage_id__in=allowed_ouvrage_ids)
    village_ouvrages_rows = village_ouvrages_qs.values(
        'parcelle__village_id',
        'ouvrage_id',
        'ouvrage__nom_ouvrage',
        'ouvrage__saisonnier'
    ).distinct()
    ouvrages_by_village = defaultdict(dict)
    ouvrage_meta = {}
    for row in village_ouvrages_rows:
        village_id = row['parcelle__village_id']
        ouvrage_id = row['ouvrage_id']
        ouvrages_by_village[village_id][ouvrage_id] = True
        ouvrage_meta[ouvrage_id] = {
            'ouvrage_nom': row['ouvrage__nom_ouvrage'] or 'Ouvrage sans nom',
            'saisonnier': bool(row['ouvrage__saisonnier']),
        }

    avis_qs_base = AvisRepresentant.objects.select_related(
        'representant',
        'representant__village__fokontany__commune__district__region'
    ).filter(
        representant_id__in=rep_ids
    )

    # Filtrage strict par annee sur la date d'avis (pas de fallback inter-annees).
    avis_qs = avis_qs_base.filter(date_avis__year=annee)

    def _negative_points_avis(avis):
        # Compter les negatives critere par critere (sur 4)
        points_criteres = (
            (0 if avis.quantite_ok else 1)
            + (0 if avis.qualite_ok else 1)
            + (0 if avis.delai_reparation_ok else 1)
            + (0 if avis.relation_gestionnaire_ok else 1)
        )
        has_problem_text = (
            bool((avis.probleme_technique or '').strip())
            or bool((avis.probleme_recouvrement or '').strip())
            or bool((avis.probleme_regles_utilisation or '').strip())
        )
        # Si aucun critere negatif mais un probleme texte existe,
        # on compte au moins 1 point negatif.
        if points_criteres == 0 and has_problem_text:
            return 1
        return points_criteres

    ouvrages_data = {}
    avis_details_by_ouvrage = defaultdict(list)
    for avis in avis_qs:
        rep = avis.representant
        village = rep.village
        ouvrage_ids_for_village = list(ouvrages_by_village.get(village.id, {}).keys())
        if not ouvrage_ids_for_village:
            continue

        negative_points = _negative_points_avis(avis)
        is_negative = negative_points > 0
        for ouvrage_id in ouvrage_ids_for_village:
            commune_obj = village.fokontany.commune if (village and village.fokontany and village.fokontany.commune) else None
            district_obj = commune_obj.district if (commune_obj and commune_obj.district) else None
            region_obj = district_obj.region if (district_obj and district_obj.region) else None

            item = ouvrages_data.setdefault(ouvrage_id, {
                'ouvrage_id': str(ouvrage_id),
                'ouvrage_nom': ouvrage_meta.get(ouvrage_id, {}).get('ouvrage_nom', 'Ouvrage sans nom'),
                'saisonnier': ouvrage_meta.get(ouvrage_id, {}).get('saisonnier', False),
                'region': (region_obj.nom_region if region_obj else 'Non defini'),
                'district': (district_obj.nom_district if district_obj else 'Non defini'),
                'commune': (commune_obj.nom_commune if commune_obj else 'Non defini'),
                'total_avis': 0,
                'avis_negatifs': 0,
                'avis_positifs': 0,
                'representants_ids': set(),
                'villages_ids': set(),
                'score_total': 0,
            })
            item['total_avis'] += 1
            item['avis_negatifs'] += int(negative_points)
            item['avis_positifs'] += int(4 - negative_points)
            item['representants_ids'].add(str(rep.id))
            item['villages_ids'].add(str(village.id))
            item['score_total'] += int(avis.score_satisfaction or 0)
            avis_details_by_ouvrage[str(ouvrage_id)].append({
                'date_avis': avis.date_avis.isoformat() if avis.date_avis else '',
                'representant_nom': rep.nom or '-',
                'village_nom': village.nom_village if village else '-',
                'score': int(avis.score_satisfaction or 0),
                'taux_satisfaction': int(round(avis.pourcentage_satisfaction or 0)),
                'est_negatif': bool(is_negative),
                'negative_points': int(negative_points),
                'probleme_technique': (avis.probleme_technique or '').strip(),
                'probleme_recouvrement': (avis.probleme_recouvrement or '').strip(),
                'probleme_regles_utilisation': (avis.probleme_regles_utilisation or '').strip(),
                'remarque': (avis.remarque or '').strip(),
            })

    ouvrage_ids = list(ouvrages_data.keys())
    reparations_details_map = defaultdict(list)
    if ouvrage_ids:
        # Règle partagée : points d'eau = actifs ; coupés = depuis moins d'un an (abandonnés à part)
        from apps.billing.points_eau_statut import q_actif, q_coupe
        pe_stats_rows = PointEau.objects.filter(ouvrage_id__in=ouvrage_ids).values('ouvrage_id').annotate(
            nb_points_eau=Count('id', filter=q_actif()),
            nb_points_eau_coupes=Count('id', filter=q_coupe())
        )
        pe_stats_map = {row['ouvrage_id']: row for row in pe_stats_rows}

        # Aligner la source des reparations sur la page /plannings/reparations/ :
        # workflow Planning (activites de reparation/rehabilitation), non terminees = estvalide=False.
        repair_activities = Activite.objects.filter(
            Q(nom__icontains='paration') |
            Q(nom__icontains='habilitation') |
            Q(nom__icontains='panne')
        ).exclude(
            Q(nom__icontains='préparation') |
            Q(nom__icontains='preparation') |
            Q(nom__icontains='au cas')
        ).distinct()
        repair_fiche_poste_ids = list(
            ActivitePoste.objects.filter(
                activite__in=repair_activities,
                fiche_poste__isnull=False
            ).values_list('fiche_poste_id', flat=True).distinct()
        )

        if repair_fiche_poste_ids:
            repairs_planning_qs = Planning.objects.filter(
                ouvrage_id__in=ouvrage_ids,
                fiche_poste_id__in=repair_fiche_poste_ids,
                date__year=annee
            ).select_related('fiche_poste').order_by('-date')
            repairs_open_qs = repairs_planning_qs.filter(Q(estvalide=False) | Q(estvalide__isnull=True))
        else:
            repairs_open_qs = Planning.objects.none()

        repairs_rows = repairs_open_qs.values('ouvrage_id').annotate(
            nb_reparations_a_faire=Count('id'),
            nb_reparations_urgentes=Count('id', filter=Q(date__lte=timezone.now())),
        )
        repairs_map = {row['ouvrage_id']: row for row in repairs_rows}

        planning_ids = list(repairs_open_qs.values_list('id', flat=True))
        point_eau_by_planning = {}
        if planning_ids:
            details_pe = PlanningDetail.objects.filter(
                planning_id__in=planning_ids,
                point_eau__isnull=False
            ).values(
                'planning_id',
                'point_eau__nomabonne',
                'point_eau__code_point_eau'
            ).order_by('planning_id', 'id')
            for d in details_pe:
                pid = str(d.get('planning_id'))
                if pid in point_eau_by_planning:
                    continue
                point_eau_by_planning[pid] = d.get('point_eau__nomabonne') or d.get('point_eau__code_point_eau') or '-'

        today = timezone.localdate()
        for repa in repairs_open_qs:
            date_prevue = None
            if repa.date:
                if timezone.is_aware(repa.date):
                    date_prevue = timezone.localtime(repa.date).date()
                else:
                    date_prevue = repa.date.date() if hasattr(repa.date, 'date') else repa.date

            date_signalement = None
            if repa.datesignalementactivite:
                if hasattr(repa.datesignalementactivite, 'date'):
                    date_signalement = repa.datesignalementactivite.date()
                else:
                    date_signalement = repa.datesignalementactivite

            statut_label = 'Planifiee' if (date_prevue and date_prevue > today) else 'En cours'
            priorite_label = 'Urgente' if (date_prevue and date_prevue <= today) else 'Normale'

            reparations_details_map[str(repa.ouvrage_id)].append({
                'id': str(repa.id),
                'titre': (repa.fiche_poste.tache if repa.fiche_poste else 'Reparation') or 'Reparation',
                'statut': statut_label,
                'priorite': priorite_label,
                'date_signalement': date_signalement.isoformat() if date_signalement else '',
                'date_prevue': date_prevue.isoformat() if date_prevue else '',
                'point_eau': point_eau_by_planning.get(str(repa.id), '-'),
                'description': (repa.remarque or '').strip(),
            })
    else:
        pe_stats_map = {}
        repairs_map = {}

    rows = []
    for ouvrage_id, item in ouvrages_data.items():
        pe_stats = pe_stats_map.get(ouvrage_id, {})
        repairs = repairs_map.get(ouvrage_id, {})

        nb_points_eau = int(pe_stats.get('nb_points_eau') or 0)
        nb_points_eau_coupes = int(pe_stats.get('nb_points_eau_coupes') or 0)
        has_coupure = nb_points_eau_coupes > 0

        nb_reparations_a_faire = int(repairs.get('nb_reparations_a_faire') or 0)
        nb_reparations_urgentes = int(repairs.get('nb_reparations_urgentes') or 0)
        has_reparations_a_faire = nb_reparations_a_faire > 0

        total_avis = item['total_avis']
        avis_negatifs = item['avis_negatifs']
        total_points_avis = total_avis * 4
        taux_negatif = int(round((avis_negatifs / total_points_avis) * 100)) if total_points_avis > 0 else 0
        score_moyen = round(item['score_total'] / total_avis, 2) if total_avis > 0 else 0.0

        grading = get_ouvrage_grading(ouvrage_id)
        grade = grading.get('grade', 'A')
        grade_label = grading.get('label', grade)

        rows.append({
            'ouvrage_id': item['ouvrage_id'],
            'ouvrage_nom': item['ouvrage_nom'],
            'region': item['region'],
            'district': item['district'],
            'commune': item['commune'],
            'saisonnier': item['saisonnier'],
            'total_avis': total_avis,
            'avis_negatifs': avis_negatifs,
            'avis_positifs': item['avis_positifs'],
            'taux_negatif': taux_negatif,
            'score_moyen': score_moyen,
            'nb_representants': len(item['representants_ids']),
            'nb_villages': len(item['villages_ids']),
            'nb_points_eau': nb_points_eau,
            'nb_points_eau_coupes': nb_points_eau_coupes,
            'has_coupure': has_coupure,
            'nb_reparations_a_faire': nb_reparations_a_faire,
            'nb_reparations_urgentes': nb_reparations_urgentes,
            'has_reparations_a_faire': has_reparations_a_faire,
            'grade': grade,
            'grade_label': grade_label,
            'avis_details': avis_details_by_ouvrage.get(str(item['ouvrage_id']), []),
            'reparations_details': reparations_details_map.get(str(item['ouvrage_id']), []),
        })

    ouvrage_ids_set = {str(r['ouvrage_id']) for r in rows}

    volume_prevu = defaultdict(lambda: Decimal('0'))
    volume_collecte = defaultdict(lambda: Decimal('0'))

    releves_volume_qs = Releve.objects.filter(
        montant__isnull=False,
        montant__gt=0,
        point_eau__ouvrage__isnull=False
    ).filter(
        Q(datereleve__year__gte=2025) | Q(datereleve__year=2024, datereleve__month=12)
    ).exclude(
        remarque__icontains='coupe'
    ).values('point_eau__ouvrage_id', 'montant', 'datereleve')

    for rel in releves_volume_qs:
        oid = str(rel['point_eau__ouvrage_id']) if rel['point_eau__ouvrage_id'] else ''
        datereleve = rel.get('datereleve')
        if not datereleve:
            continue
        mois = datereleve.month
        annee_cible = datereleve.year + 1 if mois == 12 else datereleve.year
        if annee_cible != annee:
            continue
        if oid and oid in ouvrage_ids_set:
            volume_prevu[oid] += Decimal(str(rel['montant'] or 0))

    diamex_volume_qs = BaseDiameX.objects.filter(compte_code='707401')
    for entry in diamex_volume_qs:
        extraction = extraire_ouvrage_et_mois_generique(entry.description or '', '707401')
        extraction_items = extraction if isinstance(extraction, list) else [extraction]
        for ext in extraction_items:
            if not isinstance(ext, dict):
                continue
            ouvrage_obj = ext.get('ouvrage_obj')
            annee_facture = ext.get('annee')
            if not ouvrage_obj or annee_facture != annee:
                continue
            oid = str(ouvrage_obj.id)
            if oid in ouvrage_ids_set:
                montant_segment = ext.get('montant')
                montant_to_add = Decimal(str(montant_segment)) if montant_segment is not None else Decimal(str(entry.montant_in or 0))
                volume_collecte[oid] += montant_to_add

    forfait_prevu = defaultdict(lambda: Decimal('0'))
    forfait_collecte = defaultdict(lambda: Decimal('0'))

    pf_qs = PaiementForfaitaire.objects.filter(
        date_facture__year=annee,
        date_facture__lte=timezone.localdate(),
        point_eau__ouvrage__isnull=False
    ).values('point_eau__ouvrage_id', 'montant')

    for pf in pf_qs:
        oid = str(pf['point_eau__ouvrage_id']) if pf['point_eau__ouvrage_id'] else ''
        if oid and oid in ouvrage_ids_set:
            forfait_prevu[oid] += Decimal(str(pf['montant'] or 0))

    diamex_forfait_qs = BaseDiameX.objects.filter(compte_code='748411', date_m__year=annee)
    for entry in diamex_forfait_qs:
        extraction = extraire_ouvrage_et_mois_generique(entry.description or '', '748411')
        extraction_items = extraction if isinstance(extraction, list) else [extraction]
        use_entry_montant_once = len(extraction_items) == 1
        for ext in extraction_items:
            if not isinstance(ext, dict):
                continue
            ouvrage_obj = ext.get('ouvrage_obj')
            if not ouvrage_obj:
                continue
            oid = str(ouvrage_obj.id)
            if oid in ouvrage_ids_set:
                montant_segment = ext.get('montant')
                if montant_segment is not None:
                    montant_to_add = Decimal(str(montant_segment))
                elif use_entry_montant_once:
                    montant_to_add = Decimal(str(entry.montant_in or 0))
                else:
                    continue
                forfait_collecte[oid] += montant_to_add

    paiements_forfait_details = defaultdict(list)
    pf_details_qs = PaiementForfaitaire.objects.filter(
        date_facture__year=annee,
        date_facture__lte=timezone.localdate(),
        point_eau__ouvrage__isnull=False
    ).select_related('point_eau')
    for pf in pf_details_qs:
        oid = str(pf.point_eau.ouvrage_id) if pf.point_eau and pf.point_eau.ouvrage_id else ''
        if oid and oid in ouvrage_ids_set:
            paiements_forfait_details[oid].append({
                'date': pf.date_facture.isoformat() if pf.date_facture else '',
                'point_eau': getattr(pf.point_eau, 'nomabonne', None) or getattr(pf.point_eau, 'nom', None) or '-',
                'quantite': int(pf.quantite or 0),
                'montant': float(pf.montant or 0),
            })

    for row in rows:
        oid = str(row['ouvrage_id'])
        prevu_vol = volume_prevu.get(oid, Decimal('0'))
        col_vol = volume_collecte.get(oid, Decimal('0'))
        prevu_forf = forfait_prevu.get(oid, Decimal('0'))
        col_forf = forfait_collecte.get(oid, Decimal('0'))

        row['taux_volume'] = int((col_vol / prevu_vol) * 100) if prevu_vol > 0 else 0
        row['taux_forfaitaire'] = int((col_forf / prevu_forf) * 100) if prevu_forf > 0 else 0
        total_prevu = prevu_vol + prevu_forf
        total_collecte = col_vol + col_forf
        if prevu_vol <= 0 and prevu_forf > 0:
            row['taux_paiement'] = row['taux_forfaitaire']
        elif prevu_forf <= 0 and prevu_vol > 0:
            row['taux_paiement'] = row['taux_volume']
        else:
            row['taux_paiement'] = int((total_collecte / total_prevu) * 100) if total_prevu > 0 else 0
        row['paiements_details'] = {
            'volume': {
                'prevu': float(prevu_vol),
                'collecte': float(col_vol),
                'taux': row['taux_volume'],
            },
            'forfaitaire': {
                'prevu': float(prevu_forf),
                'collecte': float(col_forf),
                'taux': row['taux_forfaitaire'],
                'lignes': paiements_forfait_details.get(oid, []),
            },
            'global': {
                'prevu': float(total_prevu),
                'collecte': float(total_collecte),
                'taux': row['taux_paiement'],
            }
        }

    rows_all = list(rows)

    # Regle prioritaire: avis negatifs + taux < 100.
    # Fallback: si vide, montrer quand meme les ouvrages avec avis negatifs.
    rows_negatifs = [r for r in rows_all if r['avis_negatifs'] > 0]
    rows_filtre_taux = [r for r in rows_negatifs if r['taux_paiement'] < 100]
    rows = rows_filtre_taux if rows_filtre_taux else rows_negatifs

    rows.sort(key=lambda x: (x['avis_negatifs'], x['taux_negatif'], x['total_avis']), reverse=True)
    top_negatifs = rows[:12]

    stats = {
        # Total ouvrages du perimetre filtre (pas seulement la table affichee)
        'nb_ouvrages': len(all_ouvrage_ids_filtered),
        'nb_ouvrages_avis_negatifs': len([r for r in rows_all if r['avis_negatifs'] > 0]),
        'nb_ouvrages_saisonniers': len([r for r in rows_all if r['saisonnier']]),
        'nb_ouvrages_coupes': len([r for r in rows_all if r['has_coupure']]),
        'nb_ouvrages_reparations_a_faire': len([r for r in rows_all if r['has_reparations_a_faire']]),
        'nb_ouvrages_grade_a': len([r for r in rows_all if r['grade'] == 'A']),
        'nb_ouvrages_grade_b': len([r for r in rows_all if r['grade'] == 'B']),
        'nb_ouvrages_grade_b_panne': len([r for r in rows_all if r['grade'] == 'B_PANNE']),
        'nb_ouvrages_grade_d': len([r for r in rows_all if r['grade'] == 'D']),
        'nb_ouvrages_grade_d_panne': len([r for r in rows_all if r['grade'] == 'D_PANNE']),
        'total_avis': sum(r['total_avis'] for r in rows_all),
        'total_avis_negatifs': sum(r['avis_negatifs'] for r in rows_all),
    }
    stats['pct_ouvrages_avis_negatifs'] = int(
        round((stats['nb_ouvrages_avis_negatifs'] / stats['nb_ouvrages']) * 100)
    ) if stats['nb_ouvrages'] > 0 else 0

    points_scope_base = PointEau.objects.filter(ouvrage__isnull=False).exclude(
        ouvrage__type_ouvrage__nom_type_ouvrage__in=['Potentiel', 'Travaux en cours']
    )
    if allowed_ouvrage_ids is not None:
        points_scope_base = points_scope_base.filter(ouvrage_id__in=allowed_ouvrage_ids)

    region_ids_scope = points_scope_base.values_list(
        'parcelle__village__fokontany__commune__district__region_id', flat=True
    ).distinct()
    regions = Region.objects.filter(id__in=region_ids_scope).order_by('nom_region')

    districts_scope_qs = points_scope_base
    if region_id:
        districts_scope_qs = districts_scope_qs.filter(
            parcelle__village__fokontany__commune__district__region_id=region_id
        )
    district_ids_scope = districts_scope_qs.values_list(
        'parcelle__village__fokontany__commune__district_id', flat=True
    ).distinct()
    districts = District.objects.select_related('region').filter(id__in=district_ids_scope).order_by('nom_district')

    communes_scope_qs = points_scope_base
    if region_id:
        communes_scope_qs = communes_scope_qs.filter(
            parcelle__village__fokontany__commune__district__region_id=region_id
        )
    if district_id:
        communes_scope_qs = communes_scope_qs.filter(
            parcelle__village__fokontany__commune__district_id=district_id
        )
    commune_ids_scope = communes_scope_qs.values_list(
        'parcelle__village__fokontany__commune_id', flat=True
    ).distinct()
    communes = Commune.objects.select_related('district', 'district__region').filter(
        id__in=commune_ids_scope
    ).order_by('nom_commune')

    if region_id:
        communes = communes.filter(district__region_id=region_id)
    if district_id:
        communes = communes.filter(district_id=district_id)

    context = {
        'rows': rows,
        'top_negatifs': top_negatifs,
        'stats': stats,
        'annee': annee,
        'selected_annee': str(annee),
        'selected_actif': actif,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'selected_region': region_id,
        'selected_district': district_id,
        'selected_commune': commune_id,
        'search_query': search,
    }
    return render(request, 'usagers/representants_reparations_dashboard.html', context)


def build_representants_avis_evolution_payload(request, filters=None):
    """
    Donnees de la page evolution des avis representants.
    Les filtres explicites permettent la reutilisation dans d'autres rapports.
    """
    from apps.billing.models import PointEau, ModaliteGestion

    filters = filters or {}

    region_id = str(filters.get('region') if 'region' in filters else request.GET.get('region', '') or '').strip()
    district_id = str(filters.get('district') if 'district' in filters else request.GET.get('district', '') or '').strip()
    commune_id = str(filters.get('commune') if 'commune' in filters else request.GET.get('commune', '') or '').strip()
    organisation_id = str(filters.get('organisation') if 'organisation' in filters else request.GET.get('organisation', '') or '').strip()
    ouvrage_id = str(filters.get('ouvrage') if 'ouvrage' in filters else request.GET.get('ouvrage', '') or '').strip()
    search = str(filters.get('search') if 'search' in filters else request.GET.get('search', '') or '').strip()
    actif = str(filters.get('actif') if 'actif' in filters else request.GET.get('actif', 'tous') or 'tous').strip()
    annee_min_raw = str(filters.get('annee_min') if 'annee_min' in filters else request.GET.get('annee_min', '') or '').strip()
    annee_max_raw = str(filters.get('annee_max') if 'annee_max' in filters else request.GET.get('annee_max', '') or '').strip()
    if organisation_id == 'all':
        organisation_id = ''

    def _to_int(value):
        try:
            return int(value)
        except Exception:
            return None

    annee_min = _to_int(annee_min_raw)
    annee_max = _to_int(annee_max_raw)
    if annee_min and annee_max and annee_min > annee_max:
        annee_min, annee_max = annee_max, annee_min

    allowed_ouvrage_ids = _get_allowed_ouvrage_ids_for_scope(
        request.user,
        organisation_id=organisation_id,
    )

    points_scope_base = PointEau.objects.filter(ouvrage__isnull=False).exclude(
        ouvrage__type_ouvrage__nom_type_ouvrage__in=['Potentiel', 'Travaux en cours']
    )
    points_scope_base = points_scope_base.filter(ouvrage_id__in=allowed_ouvrage_ids)

    points_scope_filters = points_scope_base
    if region_id:
        points_scope_filters = points_scope_filters.filter(
            parcelle__village__fokontany__commune__district__region_id=region_id
        )
    if district_id:
        points_scope_filters = points_scope_filters.filter(
            parcelle__village__fokontany__commune__district_id=district_id
        )
    if commune_id:
        points_scope_filters = points_scope_filters.filter(
            parcelle__village__fokontany__commune_id=commune_id
        )
    if ouvrage_id:
        points_scope_filters = points_scope_filters.filter(ouvrage_id=ouvrage_id)
    if search:
        points_scope_filters = points_scope_filters.filter(
            Q(ouvrage__nom_ouvrage__icontains=search)
            | Q(parcelle__village__nom_village__icontains=search)
            | Q(parcelle__village__fokontany__commune__nom_commune__icontains=search)
            | Q(parcelle__village__fokontany__commune__district__nom_district__icontains=search)
            | Q(parcelle__village__fokontany__commune__district__region__nom_region__icontains=search)
        )

    region_ids_scope = points_scope_base.values_list(
        'parcelle__village__fokontany__commune__district__region_id', flat=True
    ).distinct()
    regions = Region.objects.filter(id__in=region_ids_scope).order_by('nom_region')

    districts_scope_qs = points_scope_base
    if region_id:
        districts_scope_qs = districts_scope_qs.filter(
            parcelle__village__fokontany__commune__district__region_id=region_id
        )
    district_ids_scope = districts_scope_qs.values_list(
        'parcelle__village__fokontany__commune__district_id', flat=True
    ).distinct()
    districts = District.objects.filter(id__in=district_ids_scope).order_by('nom_district')

    communes_scope_qs = points_scope_base
    if region_id:
        communes_scope_qs = communes_scope_qs.filter(
            parcelle__village__fokontany__commune__district__region_id=region_id
        )
    if district_id:
        communes_scope_qs = communes_scope_qs.filter(
            parcelle__village__fokontany__commune__district_id=district_id
        )
    commune_ids_scope = communes_scope_qs.values_list(
        'parcelle__village__fokontany__commune_id', flat=True
    ).distinct()
    communes = Commune.objects.filter(id__in=commune_ids_scope).order_by('nom_commune')

    ouvrages_scope_qs = points_scope_base
    if region_id:
        ouvrages_scope_qs = ouvrages_scope_qs.filter(
            parcelle__village__fokontany__commune__district__region_id=region_id
        )
    if district_id:
        ouvrages_scope_qs = ouvrages_scope_qs.filter(
            parcelle__village__fokontany__commune__district_id=district_id
        )
    if commune_id:
        ouvrages_scope_qs = ouvrages_scope_qs.filter(
            parcelle__village__fokontany__commune_id=commune_id
        )
    ouvrages_options = list(
        ouvrages_scope_qs.values('ouvrage_id', 'ouvrage__nom_ouvrage').distinct().order_by('ouvrage__nom_ouvrage')
    )

    village_scope_ids = set(
        points_scope_filters.values_list('parcelle__village_id', flat=True).distinct()
    )

    representants_qs = RepresentantUsager.objects.select_related(
        'village',
        'village__fokontany__commune__district__region'
    )
    if village_scope_ids:
        representants_qs = representants_qs.filter(village_id__in=village_scope_ids)
    else:
        representants_qs = representants_qs.none()

    if actif == 'oui':
        representants_qs = representants_qs.filter(actif=True)
    elif actif == 'non':
        representants_qs = representants_qs.filter(actif=False)

    if region_id:
        representants_qs = representants_qs.filter(village__fokontany__commune__district__region_id=region_id)
    if district_id:
        representants_qs = representants_qs.filter(village__fokontany__commune__district_id=district_id)
    if commune_id:
        representants_qs = representants_qs.filter(village__fokontany__commune_id=commune_id)
    if search:
        representants_qs = representants_qs.filter(
            Q(nom__icontains=search)
            | Q(contact__icontains=search)
            | Q(village__nom_village__icontains=search)
            | Q(village__fokontany__commune__nom_commune__icontains=search)
            | Q(village__fokontany__commune__district__nom_district__icontains=search)
            | Q(village__fokontany__commune__district__region__nom_region__icontains=search)
        )

    rep_ids = list(representants_qs.values_list('id', flat=True))

    avis_scope_qs = AvisRepresentant.objects.select_related(
        'representant',
        'representant__village__fokontany__commune__district__region',
        'employe'
    ).filter(representant_id__in=rep_ids)

    years_available = list(
        avis_scope_qs.values_list('date_avis__year', flat=True).distinct().order_by('date_avis__year')
    )

    avis_qs = avis_scope_qs
    if annee_min:
        avis_qs = avis_qs.filter(date_avis__year__gte=annee_min)
    if annee_max:
        avis_qs = avis_qs.filter(date_avis__year__lte=annee_max)

    def _negative_points_avis(avis):
        points_criteres = (
            (0 if avis.quantite_ok else 1)
            + (0 if avis.qualite_ok else 1)
            + (0 if avis.delai_reparation_ok else 1)
            + (0 if avis.relation_gestionnaire_ok else 1)
        )
        has_problem_text = (
            bool((avis.probleme_technique or '').strip())
            or bool((avis.probleme_recouvrement or '').strip())
            or bool((avis.probleme_regles_utilisation or '').strip())
        )
        if points_criteres == 0 and has_problem_text:
            return 1
        return points_criteres

    yearly = {}
    for avis in avis_qs.order_by('date_avis', 'id'):
        if not avis.date_avis:
            continue
        year = avis.date_avis.year
        bucket = yearly.setdefault(
            year,
            {
                'annee': year,
                'total_avis': 0,
                'points_negatifs': 0,
                'score_total': 0,
                'satisfaction_total': 0.0,
                'quantite_non_ok': 0,
                'qualite_non_ok': 0,
                'delai_non_ok': 0,
                'relation_non_ok': 0,
                'problemes_textes': 0,
            }
        )
        points_neg = _negative_points_avis(avis)
        bucket['total_avis'] += 1
        bucket['points_negatifs'] += int(points_neg)
        bucket['score_total'] += int(avis.score_satisfaction or 0)
        bucket['satisfaction_total'] += float(avis.pourcentage_satisfaction or 0)
        bucket['quantite_non_ok'] += int(not avis.quantite_ok)
        bucket['qualite_non_ok'] += int(not avis.qualite_ok)
        bucket['delai_non_ok'] += int(not avis.delai_reparation_ok)
        bucket['relation_non_ok'] += int(not avis.relation_gestionnaire_ok)
        bucket['problemes_textes'] += int(
            bool((avis.probleme_technique or '').strip())
            or bool((avis.probleme_recouvrement or '').strip())
            or bool((avis.probleme_regles_utilisation or '').strip())
        )

    yearly_rows = []
    for year in sorted(yearly.keys()):
        item = yearly[year]
        total_avis = item['total_avis']
        total_points_max = total_avis * 4
        taux_negatif = int(round((item['points_negatifs'] / total_points_max) * 100)) if total_points_max > 0 else 0
        score_moyen = round(item['score_total'] / total_avis, 2) if total_avis > 0 else 0.0
        satisfaction_moyenne = round(item['satisfaction_total'] / total_avis, 1) if total_avis > 0 else 0.0
        yearly_rows.append({
            'annee': year,
            'total_avis': total_avis,
            'points_negatifs': item['points_negatifs'],
            'taux_negatif': taux_negatif,
            'score_moyen': score_moyen,
            'satisfaction_moyenne': satisfaction_moyenne,
            'quantite_non_ok': item['quantite_non_ok'],
            'qualite_non_ok': item['qualite_non_ok'],
            'delai_non_ok': item['delai_non_ok'],
            'relation_non_ok': item['relation_non_ok'],
            'problemes_textes': item['problemes_textes'],
        })

    total_avis_global = sum(r['total_avis'] for r in yearly_rows)
    total_points_neg_global = sum(r['points_negatifs'] for r in yearly_rows)
    total_points_max_global = total_avis_global * 4
    score_total_global = sum(yearly[y]['score_total'] for y in yearly)
    satisfaction_total_global = sum(yearly[y]['satisfaction_total'] for y in yearly)

    stats = {
        'nb_representants': representants_qs.count(),
        'total_avis': total_avis_global,
        'total_points_negatifs': total_points_neg_global,
        'taux_negatif_global': int(round((total_points_neg_global / total_points_max_global) * 100)) if total_points_max_global > 0 else 0,
        'score_moyen_global': round(score_total_global / total_avis_global, 2) if total_avis_global > 0 else 0.0,
        'satisfaction_moyenne': round(satisfaction_total_global / total_avis_global, 1) if total_avis_global > 0 else 0.0,
    }

    chart_labels = [str(r['annee']) for r in yearly_rows]
    chart_volume = {
        'labels': chart_labels,
        'total_avis': [r['total_avis'] for r in yearly_rows],
        'points_negatifs': [r['points_negatifs'] for r in yearly_rows],
    }
    chart_quality = {
        'labels': chart_labels,
        'taux_negatif': [r['taux_negatif'] for r in yearly_rows],
        'satisfaction_moyenne': [r['satisfaction_moyenne'] for r in yearly_rows],
    }
    chart_criteres = {
        'labels': chart_labels,
        'quantite_non_ok': [r['quantite_non_ok'] for r in yearly_rows],
        'qualite_non_ok': [r['qualite_non_ok'] for r in yearly_rows],
        'delai_non_ok': [r['delai_non_ok'] for r in yearly_rows],
        'relation_non_ok': [r['relation_non_ok'] for r in yearly_rows],
    }

    return {
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages_options': ouvrages_options,
        'selected_region': region_id,
        'selected_district': district_id,
        'selected_commune': commune_id,
        'selected_ouvrage': ouvrage_id,
        'selected_actif': actif,
        'search_query': search,
        'selected_annee_min': str(annee_min) if annee_min else '',
        'selected_annee_max': str(annee_max) if annee_max else '',
        'years_available': years_available,
        'stats': stats,
        'yearly_rows': yearly_rows,
        'chart_volume': chart_volume,
        'chart_quality': chart_quality,
        'chart_criteres': chart_criteres,
        'chart_volume_json': json.dumps(chart_volume),
        'chart_quality_json': json.dumps(chart_quality),
        'chart_criteres_json': json.dumps(chart_criteres),
    }


@login_required
def representants_avis_evolution_dashboard(request):
    """
    Evolution annuelle des avis representants, avec zoom geographique:
    Region -> District -> Commune -> Ouvrage.
    """
    context = build_representants_avis_evolution_payload(request)
    return render(request, 'usagers/representants_avis_evolution_dashboard.html', context)


@login_required
@require_http_methods(["POST"])
def representant_create(request):
    """Créer un nouveau représentant"""
    try:
        village_id = request.POST.get('village_id')
        nom = request.POST.get('nom', '').strip()
        contact = request.POST.get('contact', '').strip()
        observation = request.POST.get('observation', '').strip()
        date_debut = clean_date(request.POST.get('date_debut'))
        date_fin = clean_date(request.POST.get('date_fin'))
        actif = resolve_representant_active_flag(
            date_debut,
            date_fin,
            explicit_actif=parse_bool_flag(request.POST.get('actif')),
            fallback=True,
        )

        if not nom or not village_id:
            return JsonResponse({
                'success': False,
                'message': 'Le nom et le village sont obligatoires'
            })

        if date_debut and date_fin and date_fin < date_debut:
            return JsonResponse({
                'success': False,
                'message': 'La date de fin doit être supérieure ou égale à la date de début'
            })

        village = get_object_or_404(
            Village,
            id=village_id,
            id__in=_get_allowed_village_ids_for_scope(request.user),
        )

        representant = RepresentantUsager.objects.create(
            village=village,
            nom=nom,
            contact=contact or None,
            observation=observation or None,
            date_debut=date_debut,
            date_fin=date_fin,
            actif=actif
        )

        return JsonResponse({
            'success': True,
            'message': f'Représentant "{nom}" créé avec succès',
            'representant_id': str(representant.id)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
def representant_update(request, representant_id):
    """Mettre à jour un représentant"""
    try:
        representant = get_object_or_404(
            _filter_representants_queryset_for_user(RepresentantUsager.objects.all(), request.user),
            id=representant_id,
        )

        village_id = request.POST.get('village_id')
        nom = request.POST.get('nom', '').strip()
        contact = request.POST.get('contact', '').strip()
        observation = request.POST.get('observation', '').strip()
        date_debut = clean_date(request.POST.get('date_debut'))
        date_fin = clean_date(request.POST.get('date_fin'))
        actif = resolve_representant_active_flag(
            date_debut,
            date_fin,
            explicit_actif=parse_bool_flag(request.POST.get('actif')),
            fallback=representant.actif,
        )

        if not nom or not village_id:
            return JsonResponse({
                'success': False,
                'message': 'Le nom et le village sont obligatoires'
            })

        if date_debut and date_fin and date_fin < date_debut:
            return JsonResponse({
                'success': False,
                'message': 'La date de fin doit être supérieure ou égale à la date de début'
            })

        village = get_object_or_404(
            Village,
            id=village_id,
            id__in=_get_allowed_village_ids_for_scope(request.user),
        )

        representant.village = village
        representant.nom = nom
        representant.contact = contact or None
        representant.observation = observation or None
        representant.date_debut = date_debut
        representant.date_fin = date_fin
        representant.actif = actif
        representant.save()

        return JsonResponse({
            'success': True,
            'message': f'Représentant "{nom}" mis à jour'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
def representant_delete(request, representant_id):
    """Supprimer un représentant"""
    try:
        representant = get_object_or_404(
            _filter_representants_queryset_for_user(RepresentantUsager.objects.all(), request.user),
            id=representant_id,
        )
        nom = representant.nom
        nb_avis = representant.avis.count()

        representant.delete()

        return JsonResponse({
            'success': True,
            'message': f'Représentant "{nom}" supprimé ({nb_avis} avis associés)'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def avis_list_json(request, representant_id):
    """Liste des avis d'un représentant en JSON avec infos géographiques"""
    try:
        representant = get_object_or_404(
            _filter_representants_queryset_for_user(
                RepresentantUsager.objects.select_related(
                'village',
                'village__fokontany',
                'village__fokontany__commune',
                'village__fokontany__commune__district',
                ),
                request.user,
            ),
            id=representant_id
        )
    except Exception:
        return JsonResponse({'success': False, 'avis': [], 'error': 'Représentante introuvable'})

    annee = parse_year_filter(request.GET.get('annee'))

    # Récupérer infos géographiques (sécurisé si village/fokontany absent)
    try:
        village = representant.village
        fokontany = village.fokontany if village else None
        commune = fokontany.commune if fokontany else None
        district = commune.district if commune else None

        district_nom = district.nom_district if district else 'District non spécifié'
        commune_nom = commune.nom_commune if commune else 'Commune non spécifiée'
    except Exception:
        district_nom = 'District non spécifié'
        commune_nom = 'Commune non spécifiée'

    # Récupérer les ouvrages liés au village
    ouvrages_noms = ['Sans ouvrage']
    try:
        from apps.billing.models import PointEau
        if representant.village_id:
            points_eau = PointEau.objects.filter(
                parcelle__village=representant.village,
                ouvrage_id__in=_get_allowed_ouvrage_ids_for_scope(request.user),
            ).select_related('ouvrage').distinct()
            noms = [pe.ouvrage.nom_ouvrage for pe in points_eau if pe.ouvrage]
            if noms:
                ouvrages_noms = noms
    except Exception:
        pass

    try:
        avis_list = get_canonical_avis_queryset(representant.avis.select_related('employe'))
        if annee:
            avis_list = avis_list.filter(date_avis__year=annee)
        avis_list = list(avis_list.order_by('-date_avis', '-updated_at', '-created_at', '-id'))
    except Exception as e:
        return JsonResponse({'success': False, 'avis': [], 'error': f'Erreur chargement avis: {str(e)}'})

    data = []
    for avis in avis_list:
        try:
            data.append({
                'id': str(avis.id),
                'date_avis': avis.date_avis.strftime('%d/%m/%Y') if avis.date_avis else '-',
                'date_avis_iso': avis.date_avis.strftime('%Y-%m-%d') if avis.date_avis else '',
                'employe': avis.employe.surnom if avis.employe else '-',
                'employe_id': str(avis.employe.id) if avis.employe else '',
                'quantite_ok': avis.quantite_ok,
                'qualite_ok': avis.qualite_ok,
                'delai_reparation_ok': avis.delai_reparation_ok,
                'relation_gestionnaire_ok': avis.relation_gestionnaire_ok,
                'probleme_technique': avis.probleme_technique or '',
                'probleme_recouvrement': avis.probleme_recouvrement or '',
                'probleme_regles_utilisation': avis.probleme_regles_utilisation or '',
                'score': avis.score_satisfaction,
                'pourcentage': avis.pourcentage_satisfaction,
                'remarque': avis.remarque or ''
            })
        except Exception:
            continue  # Ignorer les avis malformés

    return JsonResponse({
        'success': True,
        'avis': data,
        'representant': {
            'id': str(representant.id),
            'nom': representant.nom,
            'village': representant.village.nom_village if representant.village else 'Village inconnu'
        },
        'geographie': {
            'district': district_nom,
            'commune': commune_nom,
            'ouvrages': ouvrages_noms
        }
    })



@login_required
@require_http_methods(["POST"])
def avis_create(request, representant_id):
    """Créer un nouvel avis"""
    try:
        representant = get_object_or_404(
            _filter_representants_queryset_for_user(RepresentantUsager.objects.all(), request.user),
            id=representant_id,
        )

        date_avis_str = request.POST.get('date_avis')
        employe_id = request.POST.get('employe_id')
        reunion_id = request.POST.get('reunion_id')
        quantite_ok = request.POST.get('quantite_ok') == 'true'
        qualite_ok = request.POST.get('qualite_ok') == 'true'
        delai_reparation_ok = request.POST.get('delai_reparation_ok') == 'true'
        relation_gestionnaire_ok = request.POST.get('relation_gestionnaire_ok') == 'true'
        probleme_technique = request.POST.get('probleme_technique', '').strip()
        probleme_recouvrement = request.POST.get('probleme_recouvrement', '').strip()
        probleme_regles_utilisation = request.POST.get('probleme_regles_utilisation', '').strip()
        remarque = request.POST.get('remarque', '').strip()

        # Parser la date
        try:
            date_avis = datetime.strptime(date_avis_str, '%Y-%m-%d').date()
        except:
            return JsonResponse({
                'success': False,
                'message': 'Format de date invalide'
            })

        # Récupérer l'employé
        employe = None
        if employe_id:
            try:
                employe = Employe.objects.get(id=employe_id)
            except Employe.DoesNotExist:
                pass

        # Récupérer la réunion (optionnel)
        reunion = None
        if reunion_id:
            try:
                reunion = Reunion.objects.get(id=reunion_id)
            except Reunion.DoesNotExist:
                pass

        defaults = {
            'employe': employe,
            'reunion': reunion,
            'quantite_ok': quantite_ok,
            'qualite_ok': qualite_ok,
            'delai_reparation_ok': delai_reparation_ok,
            'relation_gestionnaire_ok': relation_gestionnaire_ok,
            'probleme_technique': probleme_technique or None,
            'probleme_recouvrement': probleme_recouvrement or None,
            'probleme_regles_utilisation': probleme_regles_utilisation or None,
            'remarque': remarque or None
        }
        avis = (
            AvisRepresentant.objects.filter(representant=representant, date_avis=date_avis)
            .order_by('-updated_at', '-created_at', '-id')
            .first()
        )
        created = avis is None
        if created:
            avis = AvisRepresentant.objects.create(
                representant=representant,
                date_avis=date_avis,
                **defaults
            )
        else:
            for field_name, field_value in defaults.items():
                setattr(avis, field_name, field_value)
            avis.save()

        return JsonResponse({
            'success': True,
            'message': 'Avis créé avec succès' if created else 'Un avis existait déjà pour cette date : il a été mis à jour',
            'avis_id': str(avis.id)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
def avis_update(request, avis_id):
    """Mettre à jour un avis"""
    try:
        avis = get_object_or_404(
            _filter_avis_queryset_for_user(AvisRepresentant.objects.all(), request.user),
            id=avis_id,
        )
        original_date_avis = avis.date_avis

        date_avis_str = request.POST.get('date_avis')
        employe_id = request.POST.get('employe_id')
        reunion_id = request.POST.get('reunion_id')
        quantite_ok = request.POST.get('quantite_ok') == 'true'
        qualite_ok = request.POST.get('qualite_ok') == 'true'
        delai_reparation_ok = request.POST.get('delai_reparation_ok') == 'true'
        relation_gestionnaire_ok = request.POST.get('relation_gestionnaire_ok') == 'true'
        probleme_technique = request.POST.get('probleme_technique', '').strip()
        probleme_recouvrement = request.POST.get('probleme_recouvrement', '').strip()
        probleme_regles_utilisation = request.POST.get('probleme_regles_utilisation', '').strip()
        remarque = request.POST.get('remarque', '').strip()

        # Parser la date
        try:
            avis.date_avis = datetime.strptime(date_avis_str, '%Y-%m-%d').date()
        except:
            return JsonResponse({
                'success': False,
                'message': 'Format de date invalide'
            })

        if avis.date_avis != original_date_avis and AvisRepresentant.objects.filter(
            representant=avis.representant,
            date_avis=avis.date_avis
        ).exclude(id=avis.id).exists():
            return JsonResponse({
                'success': False,
                'message': 'Un avis existe déjÃ  pour cette représentante Ã  cette date'
            })

        # Récupérer l'employé
        if employe_id:
            try:
                avis.employe = Employe.objects.get(id=employe_id)
            except Employe.DoesNotExist:
                avis.employe = None
        else:
            avis.employe = None

        # Récupérer la réunion (optionnel)
        if reunion_id:
            try:
                avis.reunion = Reunion.objects.get(id=reunion_id)
            except Reunion.DoesNotExist:
                avis.reunion = None
        else:
            avis.reunion = None

        avis.quantite_ok = quantite_ok
        avis.qualite_ok = qualite_ok
        avis.delai_reparation_ok = delai_reparation_ok
        avis.relation_gestionnaire_ok = relation_gestionnaire_ok
        avis.probleme_technique = probleme_technique or None
        avis.probleme_recouvrement = probleme_recouvrement or None
        avis.probleme_regles_utilisation = probleme_regles_utilisation or None
        avis.remarque = remarque or None
        avis.save()

        return JsonResponse({
            'success': True,
            'message': 'Avis mis à jour'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
def avis_delete(request, avis_id):
    """Supprimer un avis"""
    try:
        avis = get_object_or_404(
            _filter_avis_queryset_for_user(AvisRepresentant.objects.all(), request.user),
            id=avis_id,
        )
        date_avis = avis.date_avis.strftime('%d/%m/%Y')

        avis.delete()

        return JsonResponse({
            'success': True,
            'message': f'Avis du {date_avis} supprimé'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        })


# ==================== EXPORT/IMPORT EXCEL ====================

@login_required
def export_representants_excel(request):
    """Exporter la liste des representants vers Excel"""
    organisation_id = request.GET.get('organisation', '').strip() or (get_default_gestionnaire_filter_value(request.user) or '')
    representants = build_representants_queryset(
        region_id=request.GET.get('region', '').strip(),
        district_id=request.GET.get('district', '').strip(),
        commune_id=request.GET.get('commune', '').strip(),
        village_id=request.GET.get('village', '').strip(),
        organisation_id=organisation_id,
        actif=request.GET.get('actif', 'tous').strip(),
        search=request.GET.get('search', '').strip(),
        user=request.user,
    ).order_by('village__nom_village', 'nom')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Representants"
    ws.freeze_panes = 'A2'

    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    headers = [
        'ID',
        'Village',
        'Fokontany',
        'Commune',
        'District',
        'Region',
        'Nom',
        'Contact',
        'Observation',
        'Date debut',
        'Date fin',
        'Actif',
    ]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    for row_num, rep in enumerate(representants, 2):
        geography = get_representant_geography_names(rep)
        ws.cell(row=row_num, column=1, value=str(rep.id))
        ws.cell(row=row_num, column=2, value=rep.village.nom_village if rep.village else '')
        ws.cell(
            row=row_num,
            column=3,
            value=rep.village.fokontany.nom_fokontany if rep.village and rep.village.fokontany else '',
        )
        ws.cell(row=row_num, column=4, value=geography['commune'])
        ws.cell(row=row_num, column=5, value=geography['district'])
        ws.cell(row=row_num, column=6, value=geography['region'])
        ws.cell(row=row_num, column=7, value=rep.nom)
        ws.cell(row=row_num, column=8, value=rep.contact or '')
        ws.cell(row=row_num, column=9, value=rep.observation or '')
        date_debut_cell = ws.cell(row=row_num, column=10, value=rep.date_debut)
        if rep.date_debut:
            date_debut_cell.number_format = 'DD/MM/YYYY'
        date_fin_cell = ws.cell(row=row_num, column=11, value=rep.date_fin)
        if rep.date_fin:
            date_fin_cell.number_format = 'DD/MM/YYYY'
        ws.cell(row=row_num, column=12, value='Oui' if rep.actif else 'Non')

        for col_num in range(1, 13):
            cell = ws.cell(row=row_num, column=col_num)
            cell.border = border
            if col_num in (10, 11):
                cell.alignment = Alignment(horizontal='center', vertical='top')
            else:
                cell.alignment = Alignment(vertical='top')

    column_widths = {
        1: 38,
        2: 22,
        3: 22,
        4: 22,
        5: 22,
        6: 22,
        7: 24,
        8: 18,
        9: 30,
        10: 14,
        11: 14,
        12: 10,
    }
    for col_num, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=representants_usagers_{datetime.now().strftime("%Y%m%d")}.xlsx'

    return response


@login_required
def template_representants_excel(request):
    """Télécharger le template Excel pour l'import des représentants"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Représentants"

    # Styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    example_fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

    # En-têtes
    headers = ['ID Village*', 'Nom*', 'Contact', 'Observation', 'Date debut', 'Date fin', 'Actif']
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Exemples
    examples = [
        ['12345', 'Jean RAKOTO', '0340101010', 'Representant depuis 2020', '01/01/2020', '', 'Oui'],
        ['67890', 'Marie RABE', '0330202020', '', '15/06/2024', '31/12/2025', 'Non'],
    ]

    for row_num, example in enumerate(examples, 2):
        for col_num, value in enumerate(example, 1):
            cell = ws.cell(row=row_num, column=col_num, value=value)
            cell.fill = example_fill

    # Instructions
    ws_instructions = wb.create_sheet("Instructions")
    instructions = [
        "INSTRUCTIONS POUR L'IMPORT",
        "",
        "Colonnes obligatoires (*) :",
        "- ID Village : ID du village (UUID, voir feuille Villages)",
        "",
        "Colonnes optionnelles :",
        "- Nom : Nom complet du représentant",
        "- Contact : Numéro de téléphone (max 50 caractères)",
        "- Observation : Remarques diverses",
        "- Date debut : JJ/MM/AAAA ou AAAA-MM-JJ",
        "- Date fin : JJ/MM/AAAA ou AAAA-MM-JJ",
        "- Actif : 'Oui' ou 'Non' (optionnel si dates renseignees)",
        "",
        "IMPORTANT :",
        "- Ne pas modifier les en-têtes (ligne 1)",
        "- Supprimer les lignes d'exemple avant l'import",
        "- Les ID Village sont des UUID (format: 12345678-1234-1234-1234-123456789012)",
        "- Si une date debut ou fin est renseignee, le statut actif est calcule automatiquement",
        "- Seul l'ID Village est obligatoire",
    ]

    for row_num, instruction in enumerate(instructions, 1):
        ws_instructions.cell(row=row_num, column=1, value=instruction)

    # Feuille Villages de référence
    ws_villages = wb.create_sheet("Villages")
    ws_villages.cell(row=1, column=1, value="ID Village")
    ws_villages.cell(row=1, column=2, value="Nom Village")
    ws_villages.cell(row=1, column=3, value="Fokontany")
    ws_villages.cell(row=1, column=4, value="Commune")

    villages = Village.objects.select_related('fokontany', 'fokontany__commune').order_by('nom_village')[:500]
    for row_num, village in enumerate(villages, 2):
        ws_villages.cell(row=row_num, column=1, value=str(village.id))
        ws_villages.cell(row=row_num, column=2, value=village.nom_village)
        ws_villages.cell(row=row_num, column=3, value=village.fokontany.nom_fokontany if village.fokontany else '')
        ws_villages.cell(row=row_num, column=4, value=village.fokontany.commune.nom_commune if village.fokontany and village.fokontany.commune else '')

    # Ajuster les colonnes
    for ws_temp in [ws, ws_villages]:
        for col_num in range(1, 8):
            ws_temp.column_dimensions[get_column_letter(col_num)].width = 20

    # Préparer la réponse
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=template_representants.xlsx'

    return response


@login_required
def template_representants_dates_debut_excel(request):
    """Télécharger le template Excel pour l'import des dates de début des représentantes."""
    representants = _filter_representants_queryset_for_user(
        RepresentantUsager.objects.select_related(
            'village',
            'village__fokontany',
            'village__fokontany__commune',
        ).order_by('village__nom_village', 'nom'),
        request.user,
    )[:1000]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dates debut"

    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    example_fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

    headers = ['ID Representante', 'ID Village', 'Village', 'Nom', 'Date debut']
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    for row_num, rep in enumerate(representants, 2):
        ws.cell(row=row_num, column=1, value=str(rep.id))
        ws.cell(row=row_num, column=2, value=str(rep.village_id) if rep.village_id else '')
        ws.cell(row=row_num, column=3, value=rep.village.nom_village if rep.village else '')
        ws.cell(row=row_num, column=4, value=rep.nom or '')
        date_cell = ws.cell(row=row_num, column=5, value=rep.date_debut)
        if rep.date_debut:
            date_cell.number_format = 'DD/MM/YYYY'

    example_row = (len(representants) + 3) if representants else 2
    for col_num, value in enumerate([
        'Remplir de preference cette colonne',
        'Alternative si ID manquant',
        '',
        'Alternative si ID manquant',
        '01/01/2024',
    ], 1):
        cell = ws.cell(row=example_row, column=col_num, value=value)
        cell.fill = example_fill

    ws_instructions = wb.create_sheet("Instructions")
    instructions = [
        "IMPORT DATES DE DEBUT",
        "",
        "Colonnes attendues :",
        "- ID Representante : recommande pour une mise a jour fiable",
        "- ID Village + Nom : alternative si ID Representante vide",
        "- Date debut : obligatoire pour chaque ligne a mettre a jour",
        "",
        "Formats dates acceptes : JJ/MM/AAAA ou AAAA-MM-JJ",
        "",
        "IMPORTANT :",
        "- Ne pas modifier les en-tetes",
        "- Laisser uniquement les lignes a mettre a jour si besoin",
        "- Si ID Representante est renseigne, il est prioritaire",
        "- Si Date debut est vide, la ligne est ignoree",
    ]
    for row_num, instruction in enumerate(instructions, 1):
        ws_instructions.cell(row=row_num, column=1, value=instruction)

    column_widths = {1: 40, 2: 40, 3: 24, 4: 28, 5: 14}
    for col_num, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width
    ws_instructions.column_dimensions['A'].width = 90

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=template_representants_dates_debut.xlsx'

    return response


@login_required
@require_http_methods(["POST"])
def import_representants_excel(request):
    """Importer des représentants depuis un fichier Excel"""
    try:
        if 'file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'message': 'Aucun fichier fourni'
            })

        excel_file = request.FILES['file']
        wb = openpyxl.load_workbook(excel_file)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        with transaction.atomic():
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
                if not row or not any(row):
                    continue

                try:
                    village_id = str(row[0]).strip() if row[0] else None
                    nom = str(row[1]).strip() if row[1] else None
                    contact = str(row[2]).strip() if row[2] and len(str(row[2]).strip()) <= 50 else None
                    observation = str(row[3]).strip() if row[3] else None
                    date_debut = clean_date(row[4]) if len(row) > 4 and row[4] else None
                    date_fin = clean_date(row[5]) if len(row) > 5 and row[5] else None
                    actif_value = row[6] if len(row) > 6 else None
                    actif = resolve_representant_active_flag(
                        date_debut,
                        date_fin,
                        explicit_actif=parse_bool_flag(actif_value),
                        fallback=True,
                    )

                    if not village_id:
                        errors.append(f"Ligne {row_num}: ID Village obligatoire")
                        continue

                    if date_debut and date_fin and date_fin < date_debut:
                        errors.append(f"Ligne {row_num}: la date de fin doit être supérieure ou égale à la date de début")
                        continue

                    # Récupérer le village (ID est UUID, pas int)
                    try:
                        village = Village.objects.get(id=village_id)
                    except (Village.DoesNotExist, ValueError, TypeError):
                        errors.append(f"Ligne {row_num}: Village ID {village_id} introuvable")
                        continue

                    # Chercher un représentant existant
                    representant = RepresentantUsager.objects.filter(
                        village=village,
                        nom=nom
                    ).first()

                    if representant:
                        # Mise à jour
                        representant.contact = contact
                        representant.observation = observation
                        representant.date_debut = date_debut
                        representant.date_fin = date_fin
                        representant.actif = actif
                        representant.save()
                        updated_count += 1
                    else:
                        # Création
                        RepresentantUsager.objects.create(
                            village=village,
                            nom=nom,
                            contact=contact,
                            observation=observation,
                            date_debut=date_debut,
                            date_fin=date_fin,
                            actif=actif
                        )
                        imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: {str(e)}")

        return JsonResponse({
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de l\'import: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
def import_representants_dates_debut_excel(request):
    """Importer uniquement les dates de début des représentantes."""
    try:
        if 'file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'message': 'Aucun fichier fourni'
            })

        excel_file = request.FILES['file']
        wb = openpyxl.load_workbook(excel_file)
        ws = wb.active

        updated_count = 0
        skipped_count = 0
        errors = []

        scoped_representants = _filter_representants_queryset_for_user(
            RepresentantUsager.objects.select_related('village'),
            request.user,
        )

        with transaction.atomic():
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
                if not row or not any(row):
                    continue

                try:
                    representant_id = str(row[0]).strip() if len(row) > 0 and row[0] else ''
                    village_id = str(row[1]).strip() if len(row) > 1 and row[1] else ''
                    nom = str(row[3]).strip() if len(row) > 3 and row[3] else ''
                    raw_date = row[4] if len(row) > 4 else None

                    if not raw_date:
                        skipped_count += 1
                        continue

                    date_debut = clean_date(raw_date)

                    representant = None
                    if representant_id:
                        representant = scoped_representants.filter(id=representant_id).first()
                        if not representant:
                            errors.append(f"Ligne {row_num}: représentante ID {representant_id} introuvable")
                            continue
                    else:
                        if not village_id or not nom:
                            errors.append(f"Ligne {row_num}: renseigner ID Representante ou bien ID Village + Nom")
                            continue
                        representant = scoped_representants.filter(
                            village_id=village_id,
                            nom=nom
                        ).first()
                        if not representant:
                            errors.append(f"Ligne {row_num}: représentante introuvable pour village {village_id} / nom {nom}")
                            continue

                    representant.date_debut = date_debut
                    representant.actif = resolve_representant_active_flag(
                        representant.date_debut,
                        representant.date_fin,
                        explicit_actif=representant.actif,
                        fallback=representant.actif,
                    )
                    representant.save(update_fields=['date_debut', 'actif', 'updated_at'])
                    updated_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: {str(e)}")

        return JsonResponse({
            'success': True,
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': errors,
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de l\'import des dates de début: {str(e)}'
        })


@login_required
def export_avis_excel(request):
    """Exporter la liste des avis vers Excel"""
    organisation_id = request.GET.get('organisation', '').strip() or (get_default_gestionnaire_filter_value(request.user) or '')
    representants = build_representants_queryset(
        region_id=request.GET.get('region', '').strip(),
        district_id=request.GET.get('district', '').strip(),
        commune_id=request.GET.get('commune', '').strip(),
        village_id=request.GET.get('village', '').strip(),
        organisation_id=organisation_id,
        actif=request.GET.get('actif', 'tous').strip(),
        search=request.GET.get('search', '').strip(),
        user=request.user,
    )
    annee = parse_year_filter(request.GET.get('annee'))
    avis_list = list(
        get_filtered_avis_queryset(representants, annee=annee).order_by(
            '-date_avis',
            'representant__nom',
            '-updated_at',
            '-created_at',
            '-id'
        )
    )
    ouvrages_by_village = get_ouvrages_by_village_ids({avis.representant.village_id for avis in avis_list})

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Avis Representants"
    ws.freeze_panes = 'A2'

    header_fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    headers = [
        'ID',
        'Date',
        'Representant',
        'Village',
        'Commune',
        'District',
        'Region',
        'Ouvrage',
        'Quantite',
        'Qualite',
        'Delai Reparation',
        'Relation Gestionnaire',
        'Score',
        'Remarque',
    ]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    for row_num, avis in enumerate(avis_list, 2):
        geography = get_representant_geography_names(avis.representant)
        ouvrages = ouvrages_by_village.get(avis.representant.village_id, ['Sans ouvrage'])

        ws.cell(row=row_num, column=1, value=str(avis.id))
        date_cell = ws.cell(row=row_num, column=2, value=avis.date_avis)
        date_cell.number_format = 'DD/MM/YYYY'
        ws.cell(row=row_num, column=3, value=avis.representant.nom)
        ws.cell(row=row_num, column=4, value=avis.representant.village.nom_village if avis.representant.village else '')
        ws.cell(row=row_num, column=5, value=geography['commune'])
        ws.cell(row=row_num, column=6, value=geography['district'])
        ws.cell(row=row_num, column=7, value=geography['region'])

        ouvrage_cell = ws.cell(row=row_num, column=8, value='\n'.join(ouvrages))
        ouvrage_cell.alignment = Alignment(vertical='top', wrap_text=True)
        ws.cell(row=row_num, column=9, value=1 if avis.quantite_ok else 0)
        ws.cell(row=row_num, column=10, value=1 if avis.qualite_ok else 0)
        ws.cell(row=row_num, column=11, value=1 if avis.delai_reparation_ok else 0)
        ws.cell(row=row_num, column=12, value=1 if avis.relation_gestionnaire_ok else 0)
        ws.cell(row=row_num, column=13, value=f"{avis.score_satisfaction}/4")
        ws.cell(row=row_num, column=14, value=avis.remarque or '')

        for col_num in range(1, 15):
            cell = ws.cell(row=row_num, column=col_num)
            cell.border = border
            if col_num not in (2, 8):
                cell.alignment = Alignment(vertical='top')

    column_widths = {
        1: 38,
        2: 14,
        3: 24,
        4: 22,
        5: 22,
        6: 22,
        7: 22,
        8: 30,
        9: 12,
        10: 12,
        11: 12,
        12: 20,
        13: 12,
        14: 28,
    }
    for col_num, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    ws_analysis = wb.create_sheet("Analyse Croisee")
    ws_analysis.freeze_panes = 'A5'
    ws_analysis['A1'] = "Analyse croisee des avis representants"
    ws_analysis['A1'].font = Font(bold=True, size=14)
    ws_analysis['A2'] = f"Total avis: {len(avis_list)}"
    ws_analysis['A2'].font = Font(italic=True, color="666666")

    criterion_rows, commune_rows = build_avis_analysis_rows(avis_list)

    criterion_title_row = 4
    ws_analysis.cell(row=criterion_title_row, column=1, value="Analyse par critere").font = Font(bold=True)
    criterion_header_row = criterion_title_row + 1
    criterion_headers = ['Critere', 'Avis positifs', 'Avis negatifs', '% positifs', '% negatifs']
    for col_num, header in enumerate(criterion_headers, 1):
        cell = ws_analysis.cell(row=criterion_header_row, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    criterion_data_start_row = criterion_header_row + 1
    for offset, row in enumerate(criterion_rows):
        current_row = criterion_data_start_row + offset
        ws_analysis.cell(row=current_row, column=1, value=row['criterion'])
        ws_analysis.cell(row=current_row, column=2, value=row['positive'])
        ws_analysis.cell(row=current_row, column=3, value=row['negative'])
        ws_analysis.cell(row=current_row, column=4, value=row['positive_pct'])
        ws_analysis.cell(row=current_row, column=5, value=row['negative_pct'])

        for col_num in range(1, 6):
            cell = ws_analysis.cell(row=current_row, column=col_num)
            cell.border = border
            cell.alignment = Alignment(vertical='top')

        ws_analysis.cell(row=current_row, column=4).number_format = '0.0"%"'
        ws_analysis.cell(row=current_row, column=5).number_format = '0.0"%"'

    criterion_data_end_row = criterion_data_start_row + len(criterion_rows) - 1

    commune_title_row = max(criterion_data_end_row + 4, 12)
    ws_analysis.cell(
        row=commune_title_row,
        column=1,
        value="Analyse par region / district / commune / critere",
    ).font = Font(bold=True)
    commune_header_row = commune_title_row + 1
    commune_headers = [
        'Region',
        'District',
        'Commune',
        'Critere',
        'Avis positifs',
        'Avis negatifs',
        '% positifs',
        '% negatifs',
        'Libelle chart',
    ]
    for col_num, header in enumerate(commune_headers, 1):
        cell = ws_analysis.cell(row=commune_header_row, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    commune_data_start_row = commune_header_row + 1
    for offset, row in enumerate(commune_rows):
        current_row = commune_data_start_row + offset
        ws_analysis.cell(row=current_row, column=1, value=row['region'])
        ws_analysis.cell(row=current_row, column=2, value=row['district'])
        ws_analysis.cell(row=current_row, column=3, value=row['commune'])
        ws_analysis.cell(row=current_row, column=4, value=row['criterion'])
        ws_analysis.cell(row=current_row, column=5, value=row['positive'])
        ws_analysis.cell(row=current_row, column=6, value=row['negative'])
        ws_analysis.cell(row=current_row, column=7, value=row['positive_pct'])
        ws_analysis.cell(row=current_row, column=8, value=row['negative_pct'])
        ws_analysis.cell(row=current_row, column=9, value=row['chart_label'])

        for col_num in range(1, 10):
            cell = ws_analysis.cell(row=current_row, column=col_num)
            cell.border = border
            cell.alignment = Alignment(vertical='top')

        ws_analysis.cell(row=current_row, column=7).number_format = '0.0"%"'
        ws_analysis.cell(row=current_row, column=8).number_format = '0.0"%"'

    commune_data_end_row = commune_data_start_row + len(commune_rows) - 1
    chart_left_col = "K"
    chart_right_col = "X"
    add_export_stacked_chart(
        ws_analysis,
        title="Avis positifs / negatifs par critere",
        category_col=1,
        data_start_col=2,
        header_row=criterion_header_row,
        data_start_row=criterion_data_start_row,
        data_end_row=criterion_data_end_row,
        anchor=f"{chart_left_col}{criterion_title_row}",
        y_axis_title="Nombre d'avis",
        x_axis_title="Critere",
        grouping='clustered',
    )
    add_export_stacked_chart(
        ws_analysis,
        title="Pourcentage d'avis par critere",
        category_col=1,
        data_start_col=4,
        header_row=criterion_header_row,
        data_start_row=criterion_data_start_row,
        data_end_row=criterion_data_end_row,
        anchor=f"{chart_right_col}{criterion_title_row}",
        y_axis_title="% d'avis",
        x_axis_title="Critere",
        grouping='clustered',
    )
    add_export_stacked_chart(
        ws_analysis,
        title="Avis positifs / negatifs par commune",
        category_col=9,
        data_start_col=5,
        header_row=commune_header_row,
        data_start_row=commune_data_start_row,
        data_end_row=commune_data_end_row,
        anchor=f"{chart_left_col}{commune_title_row}",
        y_axis_title="Nombre d'avis",
        x_axis_title="Commune / Critere",
        show_data_labels=False,
        grouping='clustered',
    )
    add_export_stacked_chart(
        ws_analysis,
        title="Pourcentage d'avis par commune",
        category_col=9,
        data_start_col=7,
        header_row=commune_header_row,
        data_start_row=commune_data_start_row,
        data_end_row=commune_data_end_row,
        anchor=f"{chart_right_col}{commune_title_row}",
        y_axis_title="% d'avis",
        x_axis_title="Commune / Critere",
        show_data_labels=False,
        grouping='clustered',
    )

    analysis_column_widths = {
        1: 20,
        2: 22,
        3: 22,
        4: 22,
        5: 14,
        6: 14,
        7: 12,
        8: 12,
        9: 34,
    }
    for col_num, width in analysis_column_widths.items():
        ws_analysis.column_dimensions[get_column_letter(col_num)].width = width
    ws_analysis.column_dimensions['I'].hidden = True

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=avis_representants_{datetime.now().strftime("%Y%m%d")}.xlsx'

    return response


@login_required
def template_avis_excel(request):
    """Télécharger le template Excel pour l'import des avis"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Avis"

    # Styles
    header_fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    example_fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

    # En-têtes
    headers = ['ID Représentant*', 'Date*', 'Surnom Employé', 'Quantité OK*', 'Qualité OK*', 'Délai Réparation OK*', 'Relation Gestionnaire OK*', 'Remarque']
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Exemples
    examples = [
        ['uuid-representant-1', '01/01/2025', 'Victorien', 'Oui', 'Oui', 'Non', 'Oui', 'Problème de pression'],
        ['uuid-representant-2', '15/01/2025', 'Michel', 'Oui', 'Oui', 'Oui', 'Oui', ''],
    ]

    for row_num, example in enumerate(examples, 2):
        for col_num, value in enumerate(example, 1):
            cell = ws.cell(row=row_num, column=col_num, value=value)
            cell.fill = example_fill

    # Instructions
    ws_instructions = wb.create_sheet("Instructions")
    instructions = [
        "INSTRUCTIONS POUR L'IMPORT",
        "",
        "Colonnes obligatoires (*) :",
        "- ID Représentant : UUID du représentant (voir feuille Représentants)",
        "- Date : Format DD/MM/YYYY",
        "- Quantité OK, Qualité OK, etc. : 'Oui' ou 'Non'",
        "",
        "Colonnes optionnelles :",
        "- Surnom Employé : Surnom de l'employé (voir feuille Employés)",
        "- Remarque : Texte libre",
    ]

    for row_num, instruction in enumerate(instructions, 1):
        ws_instructions.cell(row=row_num, column=1, value=instruction)

    # Feuilles de référence
    ws_reps = wb.create_sheet("Représentants")
    ws_reps.cell(row=1, column=1, value="ID")
    ws_reps.cell(row=1, column=2, value="Nom")
    ws_reps.cell(row=1, column=3, value="Village")

    representants = RepresentantUsager.objects.select_related('village').filter(actif=True).order_by('nom')[:200]
    for row_num, rep in enumerate(representants, 2):
        ws_reps.cell(row=row_num, column=1, value=str(rep.id))
        ws_reps.cell(row=row_num, column=2, value=rep.nom)
        ws_reps.cell(row=row_num, column=3, value=rep.village.nom_village)

    ws_employes = wb.create_sheet("Employés")
    ws_employes.cell(row=1, column=1, value="Surnom")
    ws_employes.cell(row=1, column=2, value="Nom Complet")

    employes = Employe.objects.filter(salarie=True).order_by('surnom')[:100]
    for row_num, emp in enumerate(employes, 2):
        ws_employes.cell(row=row_num, column=1, value=emp.surnom)
        ws_employes.cell(row=row_num, column=2, value=f"{emp.prenom} {emp.nom}")

    # Ajuster les colonnes
    for ws_temp in [ws, ws_reps, ws_employes]:
        for col_num in range(1, 9):
            ws_temp.column_dimensions[get_column_letter(col_num)].width = 20

    # Préparer la réponse
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=template_avis.xlsx'

    return response


@login_required
@require_http_methods(["POST"])
def import_avis_excel(request):
    """Importer des avis depuis un fichier Excel"""
    try:
        if 'file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'message': 'Aucun fichier fourni'
            })

        excel_file = request.FILES['file']
        wb = openpyxl.load_workbook(excel_file)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        print(f"🔍 Début import avis - Nombre total de lignes: {ws.max_row}")

        # Import ligne par ligne SANS transaction.atomic() pour permettre import partiel
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            # Ignorer les lignes vides
            if not row or not any(row):
                print(f"⏭️ Ligne {row_num}: vide, ignorée")
                continue

            try:
                # Extraire les données
                representant_id = str(row[0]).strip() if row[0] else None
                date_str = str(row[1]).strip() if row[1] else None
                employe_surnom = str(row[2]).strip() if row[2] else None
                quantite_ok_str = str(row[3]).strip().lower() if row[3] else 'non'
                qualite_ok_str = str(row[4]).strip().lower() if row[4] else 'non'
                delai_reparation_ok_str = str(row[5]).strip().lower() if row[5] else 'non'
                relation_gestionnaire_ok_str = str(row[6]).strip().lower() if row[6] else 'non'
                remarque = str(row[7]).strip() if row[7] and str(row[7]).strip() else None

                print(f"📋 Ligne {row_num}: Représentant={representant_id}, Date={date_str}, Employé={employe_surnom}")

                # Validation champs obligatoires
                if not representant_id:
                    errors.append(f"Ligne {row_num}: ID Représentant obligatoire (colonne A)")
                    print(f"❌ Ligne {row_num}: ID Représentant manquant")
                    continue

                if not date_str:
                    errors.append(f"Ligne {row_num}: Date obligatoire (colonne B)")
                    print(f"❌ Ligne {row_num}: Date manquante")
                    continue

                # Récupérer le représentant
                try:
                    representant = RepresentantUsager.objects.get(id=representant_id)
                    print(f"✅ Représentant trouvé: {representant.nom}")
                except RepresentantUsager.DoesNotExist:
                    errors.append(f"Ligne {row_num}: Représentant avec ID '{representant_id}' introuvable")
                    print(f"❌ Ligne {row_num}: Représentant ID '{representant_id}' introuvable")
                    continue
                except (ValueError, TypeError) as e:
                    errors.append(f"Ligne {row_num}: ID Représentant invalide '{representant_id}' - doit être un UUID")
                    print(f"❌ Ligne {row_num}: ID invalide - {str(e)}")
                    continue

                # Parser la date en utilisant clean_date()
                try:
                    date_avis = clean_date(date_str)
                    print(f"✅ Date parsée: {date_avis}")
                except Exception as e:
                    errors.append(f"Ligne {row_num}: {str(e)}")
                    print(f"❌ Ligne {row_num}: Erreur parsing date - {str(e)}")
                    continue


                # Récupérer l'employé par surnom (optionnel)
                employe = None
                if employe_surnom and employe_surnom.lower() not in ['', 'none', 'null']:
                    try:
                        employe = Employe.objects.get(surnom__iexact=employe_surnom)
                        print(f"✅ Employé trouvé: {employe.surnom}")
                    except Employe.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Warning - Employé '{employe_surnom}' introuvable (avis créé sans employé)")
                        print(f"⚠️ Ligne {row_num}: Employé '{employe_surnom}' introuvable")
                    except Employe.MultipleObjectsReturned:
                        employe = Employe.objects.filter(surnom__iexact=employe_surnom).first()
                        errors.append(f"Ligne {row_num}: Warning - Plusieurs employés '{employe_surnom}', premier utilisé")
                        print(f"⚠️ Ligne {row_num}: Plusieurs employés trouvés, premier utilisé")

                # Convertir Oui/Non en booléens
                quantite_ok = quantite_ok_str in ['oui', 'yes', '1', 'true', 'vrai']
                qualite_ok = qualite_ok_str in ['oui', 'yes', '1', 'true', 'vrai']
                delai_reparation_ok = delai_reparation_ok_str in ['oui', 'yes', '1', 'true', 'vrai']
                relation_gestionnaire_ok = relation_gestionnaire_ok_str in ['oui', 'yes', '1', 'true', 'vrai']

                defaults = {
                    'employe': employe,
                    'quantite_ok': quantite_ok,
                    'qualite_ok': qualite_ok,
                    'delai_reparation_ok': delai_reparation_ok,
                    'relation_gestionnaire_ok': relation_gestionnaire_ok,
                    'remarque': remarque,
                }
                avis = (
                    AvisRepresentant.objects.filter(representant=representant, date_avis=date_avis)
                    .order_by('-updated_at', '-created_at', '-id')
                    .first()
                )
                if avis is None:
                    avis = AvisRepresentant.objects.create(
                        representant=representant,
                        date_avis=date_avis,
                        **defaults
                    )
                    imported_count += 1
                    print(f"âœ… Ligne {row_num}: Avis créé avec succès (ID: {avis.id})")
                else:
                    for field_name, field_value in defaults.items():
                        setattr(avis, field_name, field_value)
                    avis.save()
                    updated_count += 1
                    print(f"âœ… Ligne {row_num}: Avis existant mis Ã  jour (ID: {avis.id})")
                continue

            except Exception as e:
                error_msg = f"Ligne {row_num}: Erreur inattendue - {str(e)}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()

        print(f"🎉 Import terminé: {imported_count} avis créés, {updated_count} avis mis à jour, {len(errors)} erreurs")

        return JsonResponse({
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'errors': errors
        })

    except Exception as e:
        error_msg = f'Erreur lors de l\'import: {str(e)}'
        print(f"❌ ERREUR GLOBALE: {error_msg}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': error_msg
        })
