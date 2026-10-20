from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import datetime
from collections import defaultdict

from apps.geography.models import Region, District, Commune
from apps.organization.models import Ouvrage
from apps.billing.models import Releve, ModaliteGestion, PointEau, TypePointEau


@login_required
def tableau_points_eau(request):
    """Tableau comparatif de tous les points d'eau avec leurs statistiques"""

    # Filtres
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    regions_ids = request.GET.getlist('regions')
    districts_ids = request.GET.getlist('districts')
    communes_ids = request.GET.getlist('communes')
    ouvrages_ids = request.GET.getlist('ouvrages')
    types_pe_ids = request.GET.getlist('types_pe')
    modalite_paiement_filter = request.GET.get('modalite_paiement', '')

    # Récupérer les ouvrages selon la modalité
    modalite_query = ModaliteGestion.objects.filter(date_fin__isnull=True)
    if modalite_paiement_filter:
        if modalite_paiement_filter == 'au_volume':
            modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])
        elif modalite_paiement_filter == 'forfaitaire':
            modalite_query = modalite_query.filter(modalitepaiement='forfaitaire')
        elif modalite_paiement_filter == 'mixte':
            modalite_query = modalite_query.filter(modalitepaiement='mixte')
    else:
        modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])

    ouvrages_ids_modalite = list(modalite_query.values_list('ouvrage_id', flat=True).distinct())

    # Base queryset des points d'eau
    points_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_ids_modalite
    ).select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune__district__region'
    )

    # Appliquer les filtres
    if regions_ids and regions_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district__region_id__in=regions_ids
        )
    if districts_ids and districts_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district_id__in=districts_ids
        )
    if communes_ids and communes_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune_id__in=communes_ids
        )
    if ouvrages_ids and ouvrages_ids != ['']:
        points_eau_qs = points_eau_qs.filter(ouvrage_id__in=ouvrages_ids)
    if types_pe_ids and types_pe_ids != ['']:
        points_eau_qs = points_eau_qs.filter(type_point_eau_id__in=types_pe_ids)

    # Calculer les statistiques pour chaque point d'eau
    annee_int = int(annee_filter)
    points_eau_stats = []

    for pe in points_eau_qs:
        stats = calculer_stats_point_eau(pe, annee_int)
        if stats['nb_releves'] > 0:  # N'afficher que les points avec des relevés
            points_eau_stats.append({
                'point_eau': pe,
                'stats': stats,
                'ouvrage_nom': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A'
            })

    # Tri par défaut : par IDxls puis ouvrage
    sort_by = request.GET.get('sort', 'idxls')
    if sort_by == 'moyenne_asc':
        points_eau_stats.sort(key=lambda x: x['stats']['moyenne_mensuelle'])
    elif sort_by == 'moyenne_desc':
        points_eau_stats.sort(key=lambda x: x['stats']['moyenne_mensuelle'], reverse=True)
    elif sort_by == 'volume_asc':
        points_eau_stats.sort(key=lambda x: x['stats']['volume_total'])
    elif sort_by == 'volume_desc':
        points_eau_stats.sort(key=lambda x: x['stats']['volume_total'], reverse=True)
    elif sort_by == 'idxls':
        # Tri par idxls (numérique si possible) puis ouvrage
        points_eau_stats.sort(key=lambda x: (
            int(x['point_eau'].idxls) if x['point_eau'].idxls and str(x['point_eau'].idxls).isdigit() else 99999999,
            x['point_eau'].ouvrage.nom_ouvrage if x['point_eau'].ouvrage else ''
        ))

    # Assigner des couleurs aux ouvrages pour différenciation visuelle
    ouvrage_colors = [
        'primary', 'secondary', 'accent', 'info', 'success', 'warning',
        'error', 'purple', 'pink', 'indigo'
    ]
    ouvrage_color_map = {}
    color_index = 0

    for item in points_eau_stats:
        ouvrage_nom = item['ouvrage_nom']
        if ouvrage_nom not in ouvrage_color_map:
            ouvrage_color_map[ouvrage_nom] = ouvrage_colors[color_index % len(ouvrage_colors)]
            color_index += 1
        item['ouvrage_color'] = ouvrage_color_map[ouvrage_nom]

        # Catégoriser par médiane de consommation
        mediane = item['stats']['mediane_mensuelle']
        if mediane < 3:
            item['categorie_conso'] = {
                'label': '< 3 m³/mois',
                'badge_color': 'info',
                'icon': 'fa-tint',
                'order': 1
            }
        elif mediane < 4:
            item['categorie_conso'] = {
                'label': '3-4 m³/mois',
                'badge_color': 'success',
                'icon': 'fa-tint',
                'order': 2
            }
        elif mediane < 10:
            item['categorie_conso'] = {
                'label': '4-10 m³/mois',
                'badge_color': 'warning',
                'icon': 'fa-tint',
                'order': 3
            }
        else:
            item['categorie_conso'] = {
                'label': '> 10 m³/mois',
                'badge_color': 'error',
                'icon': 'fa-tint',
                'order': 4
            }

    # Listes pour les dropdowns - filtrer pour afficher seulement les entités avec des relevés
    # Récupérer tous les points d'eau qui ont des relevés
    points_eau_avec_releves = PointEau.objects.filter(
        releves__isnull=False
    ).select_related(
        'parcelle__village__fokontany__commune__district__region',
        'type_point_eau',
        'ouvrage'
    ).distinct()

    # Extraire les IDs des entités géographiques liées à ces points d'eau
    communes_ids_avec_releves = points_eau_avec_releves.exclude(
        parcelle__village__fokontany__commune__isnull=True
    ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()

    districts_ids_avec_releves = points_eau_avec_releves.exclude(
        parcelle__village__fokontany__commune__district__isnull=True
    ).values_list('parcelle__village__fokontany__commune__district_id', flat=True).distinct()

    regions_ids_avec_releves = points_eau_avec_releves.exclude(
        parcelle__village__fokontany__commune__district__region__isnull=True
    ).values_list('parcelle__village__fokontany__commune__district__region_id', flat=True).distinct()

    types_pe_ids_avec_releves = points_eau_avec_releves.exclude(
        type_point_eau__isnull=True
    ).values_list('type_point_eau_id', flat=True).distinct()

    # Filtrer les listes pour n'afficher que celles qui ont des relevés
    regions = Region.objects.filter(id__in=regions_ids_avec_releves).order_by('nom_region')
    districts = District.objects.filter(id__in=districts_ids_avec_releves).order_by('nom_district')
    communes = Commune.objects.filter(id__in=communes_ids_avec_releves).order_by('nom_commune')
    ouvrages = Ouvrage.objects.filter(id__in=ouvrages_ids_modalite).order_by('nom_ouvrage')
    types_pe = TypePointEau.objects.filter(id__in=types_pe_ids_avec_releves).order_by('nom_type')

    # Mode d'affichage : table ou card
    view_mode = request.GET.get('view', 'table')

    context = {
        'title': 'Tableau Comparatif des Points d\'Eau',
        'annee_filter': annee_filter,
        'regions_ids': regions_ids,
        'districts_ids': districts_ids,
        'communes_ids': communes_ids,
        'ouvrages_ids': ouvrages_ids,
        'types_pe_ids': types_pe_ids,
        'modalite_paiement_filter': modalite_paiement_filter,
        'sort_by': sort_by,
        'view_mode': view_mode,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'types_pe': types_pe,
        'points_eau_stats': points_eau_stats,
        'nb_points_eau': len(points_eau_stats),
    }

    return render(request, 'planning/tableau_points_eau.html', context)


def calculer_stats_point_eau(point_eau, annee):
    """Calcule moyenne, médiane et nombre de relevés pour un point d'eau"""
    from dateutil.relativedelta import relativedelta

    releves = Releve.objects.filter(
        point_eau=point_eau,
        datereleve__year=annee
    ).order_by('datereleve')

    volumes_mensuels = []
    volume_total = 0

    releves_list = list(releves)

    for i, releve in enumerate(releves_list):
        volume = float(releve.volume_facture) if releve.volume_facture else 0
        if volume <= 0:
            continue

        # Trouver le relevé précédent
        if i > 0:
            date_debut = releves_list[i-1].datereleve
        else:
            releve_precedent = Releve.objects.filter(
                point_eau=point_eau,
                datereleve__lt=releve.datereleve
            ).order_by('-datereleve').first()

            if releve_precedent and releve_precedent.datereleve:
                date_debut = releve_precedent.datereleve
            else:
                date_debut = releve.datereleve.replace(day=1)

        date_fin = releve.datereleve
        delta_jours = (date_fin - date_debut).days
        if delta_jours <= 0:
            delta_jours = 1

        # Calculer le volume mensuel moyen sur la période
        nb_mois = max(1, delta_jours / 30.44)  # Moyenne de jours par mois
        volume_mensuel = volume / nb_mois

        volumes_mensuels.append(volume_mensuel)
        volume_total += volume

    # Calculer moyenne et médiane
    if volumes_mensuels:
        moyenne = sum(volumes_mensuels) / len(volumes_mensuels)
        volumes_sorted = sorted(volumes_mensuels)
        n = len(volumes_sorted)
        if n % 2 == 0:
            mediane = (volumes_sorted[n//2 - 1] + volumes_sorted[n//2]) / 2
        else:
            mediane = volumes_sorted[n//2]
    else:
        moyenne = 0
        mediane = 0

    return {
        'volume_total': volume_total,
        'nb_releves': releves.count(),
        'moyenne_mensuelle': moyenne,
        'mediane_mensuelle': mediane,
    }
