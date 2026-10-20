# -*- coding: utf-8 -*-
"""
Vues pour l'analyse des données météorologiques
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Avg, Sum, Count, Min, Max
from datetime import datetime
from collections import defaultdict

from apps.geography.models import DonneeMeteo, Village, Commune, District, Region


@login_required
def analyse_meteo(request):
    """
    Page d'analyse des données météorologiques
    """

    # Récupérer l'année de filtre (année courante par défaut)
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    try:
        annee_int = int(annee_filter)
    except ValueError:
        annee_int = datetime.now().year

    # Récupérer les filtres géographiques
    region_id = request.GET.get('region')
    district_id = request.GET.get('district')
    commune_id = request.GET.get('commune')
    village_id = request.GET.get('village')

    # Filtrer les villages avec coordonnées GPS
    villages_qs = Village.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).exclude(latitude=0).exclude(longitude=0)

    # Appliquer les filtres géographiques
    if village_id and village_id != 'all':
        villages_qs = villages_qs.filter(id=village_id)
    elif commune_id and commune_id != 'all':
        villages_qs = villages_qs.filter(fokontany__commune_id=commune_id)
    elif district_id and district_id != 'all':
        villages_qs = villages_qs.filter(fokontany__commune__district_id=district_id)
    elif region_id and region_id != 'all':
        villages_qs = villages_qs.filter(fokontany__commune__district__region_id=region_id)

    nb_villages = villages_qs.count()

    # Récupérer les données météo pour l'année sélectionnée
    meteo_qs = DonneeMeteo.objects.filter(
        village__in=villages_qs,
        date__year=annee_int
    ).select_related('village')

    nb_mesures_total = meteo_qs.count()

    # Calculer les statistiques annuelles
    stats_annuelles = meteo_qs.aggregate(
        temp_max_moy=Avg('temperature_max'),
        temp_min_moy=Avg('temperature_min'),
        temp_max_abs=Max('temperature_max'),
        temp_min_abs=Min('temperature_min'),
        precipitation_totale=Sum('precipitation'),
        precipitation_moy=Avg('precipitation'),
        humidite_moy=Avg('humidite')
    )

    # Statistiques par mois
    mois_liste = list(range(1, 13))
    mois_noms = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

    stats_par_mois = []
    precipitations_par_mois = {mois: [] for mois in mois_liste}
    temperatures_max_par_mois = {mois: [] for mois in mois_liste}
    temperatures_min_par_mois = {mois: [] for mois in mois_liste}
    humidites_par_mois = {mois: [] for mois in mois_liste}
    nb_mesures_par_mois = {mois: 0 for mois in mois_liste}

    for donnee in meteo_qs:
        if donnee.date:
            mois = donnee.date.month
            nb_mesures_par_mois[mois] += 1

            if donnee.precipitation is not None:
                precipitations_par_mois[mois].append(float(donnee.precipitation))
            if donnee.temperature_max is not None:
                temperatures_max_par_mois[mois].append(float(donnee.temperature_max))
            if donnee.temperature_min is not None:
                temperatures_min_par_mois[mois].append(float(donnee.temperature_min))
            if donnee.humidite is not None:
                humidites_par_mois[mois].append(float(donnee.humidite))

    for mois in mois_liste:
        precip_list = precipitations_par_mois[mois]
        temp_max_list = temperatures_max_par_mois[mois]
        temp_min_list = temperatures_min_par_mois[mois]
        humidite_list = humidites_par_mois[mois]

        stats_par_mois.append({
            'mois': mois,
            'mois_nom': mois_noms[mois - 1],
            'precipitation_totale': round(sum(precip_list), 1) if precip_list else 0,
            'precipitation_moyenne': round(sum(precip_list) / len(precip_list), 1) if precip_list else 0,
            'temperature_max_moy': round(sum(temp_max_list) / len(temp_max_list), 1) if temp_max_list else 0,
            'temperature_min_moy': round(sum(temp_min_list) / len(temp_min_list), 1) if temp_min_list else 0,
            'humidite_moy': round(sum(humidite_list) / len(humidite_list), 1) if humidite_list else 0,
            'nb_mesures': nb_mesures_par_mois[mois]
        })

    # Préparer les données pour les graphiques
    import json
    graphique_meteo = {
        'labels': [s['mois_nom'][:3] for s in stats_par_mois],
        'precipitations': [s['precipitation_totale'] for s in stats_par_mois],
        'temperatures_max': [s['temperature_max_moy'] for s in stats_par_mois],
        'temperatures_min': [s['temperature_min_moy'] for s in stats_par_mois],
        'humidites': [s['humidite_moy'] for s in stats_par_mois],
        'nb_mesures': [s['nb_mesures'] for s in stats_par_mois]
    }

    # Listes pour les filtres
    regions = Region.objects.all().order_by('nom_region')
    districts = District.objects.all().order_by('nom_district')
    communes = Commune.objects.all().order_by('nom_commune')
    villages = Village.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).exclude(latitude=0).exclude(longitude=0).order_by('nom_village')

    context = {
        'annee_filter': annee_filter,
        'annee_int': annee_int,
        'annees_liste': list(range(2020, 2027)),  # Liste des années pour le filtre
        'nb_villages': nb_villages,
        'nb_mesures_total': nb_mesures_total,
        'stats_annuelles': stats_annuelles,
        'stats_par_mois': stats_par_mois,
        'graphique_meteo': json.dumps(graphique_meteo),
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'villages': villages,
        'region_id': region_id or '',
        'district_id': district_id or '',
        'commune_id': commune_id or '',
        'village_id': village_id or ''
    }

    return render(request, 'planning/analyse_meteo.html', context)
