# -*- coding: utf-8 -*-
"""
Vues pour l'analyse de la consommation des cartes sociales
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
import calendar
import json

from django.db.models import Sum, Count, Q, F, Case, When, Value, IntegerField
from django.db.models.functions import ExtractMonth
from django.utils import timezone
from datetime import datetime
from collections import defaultdict
from decimal import Decimal

from apps.billing.models import ConsoCarteSociale, PointEau, TypePointEau
from apps.infrastructure.models import CarteSociale
from apps.organization.models import Ouvrage
from apps.geography.models import Commune, District, Region, Village


MOIS_NOMS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
             'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
MOIS_COURTS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']


def mois_clos_pour_annee(annee):
    """Mois entièrement écoulés de l'année (le mois en cours et les mois futurs sont exclus)."""
    aujourd_hui = timezone.localdate()
    if annee < aujourd_hui.year:
        return list(range(1, 13))
    if annee == aujourd_hui.year:
        return list(range(1, aujourd_hui.month))
    return []


def periode_label(annee, mois_clos):
    if not mois_clos:
        return f"aucun mois clos en {annee}"
    if len(mois_clos) == 12:
        return f"année {annee}"
    if len(mois_clos) == 1:
        return f"janvier {annee}"
    return f"janvier – {MOIS_NOMS[mois_clos[-1] - 1].lower()} {annee}"


def filtrer_cartes_par_zone(cartes_qs, region_id, district_id, commune_id, village_id, ouvrage_ids=None):
    """Applique le filtre géographique le plus fin renseigné (via l'ouvrage de la carte)."""
    base = 'ouvrage__pointeau__parcelle__village'
    if ouvrage_ids:
        return cartes_qs.filter(ouvrage_id__in=ouvrage_ids)
    if village_id and village_id != 'all':
        return cartes_qs.filter(**{f'{base}_id': village_id}).distinct()
    if commune_id and commune_id != 'all':
        return cartes_qs.filter(**{f'{base}__fokontany__commune_id': commune_id}).distinct()
    if district_id and district_id != 'all':
        return cartes_qs.filter(**{f'{base}__fokontany__commune__district_id': district_id}).distinct()
    if region_id and region_id != 'all':
        return cartes_qs.filter(**{f'{base}__fokontany__commune__district__region_id': region_id}).distinct()
    return cartes_qs


@login_required
def analyse_cartes_sociales(request):
    """
    Page d'analyse de la consommation des cartes sociales
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
    ouvrage_id = request.GET.get('ouvrage')

    # Filtrer les cartes sociales actives
    cartes_qs = CarteSociale.objects.filter(statut='active')

    # Appliquer les filtres géographiques via ouvrage
    ouvrage_ids = [ouvrage_id] if ouvrage_id and ouvrage_id != 'all' else None
    cartes_qs = filtrer_cartes_par_zone(cartes_qs, region_id, district_id, commune_id, village_id, ouvrage_ids)

    # Statistiques globales
    nb_cartes_sociales = cartes_qs.count()

    # Calculer la population couverte (4 personnes si non renseigné)
    population_cartes_sociales = 0
    for carte in cartes_qs:
        if carte.nombre_habitants and carte.nombre_habitants > 0:
            population_cartes_sociales += carte.nombre_habitants
        else:
            population_cartes_sociales += 4

    # Seuls les mois clos sont analysés : le mois en cours et les mois futurs sont masqués
    mois_clos = mois_clos_pour_annee(annee_int)
    jours_couverts = sum(calendar.monthrange(annee_int, m)[1] for m in mois_clos)

    # Récupérer les consommations des mois clos de l'année
    consos_qs = ConsoCarteSociale.objects.filter(
        carte_sociale__in=cartes_qs,
        date__year=annee_int,
        date__month__in=mois_clos,
    )

    totaux = consos_qs.aggregate(volume=Sum('volume_total'), montant=Sum('montant_paye'))
    volume_total_annuel = float(totaux['volume'] or 0)
    montant_total_annuel = float(totaux['montant'] or 0)

    # Calculer la consommation moyenne par carte
    conso_moyenne_par_carte = volume_total_annuel / nb_cartes_sociales if nb_cartes_sociales > 0 else 0

    # Consommation par habitant par jour (en litres) sur la période close
    if population_cartes_sociales > 0 and jours_couverts > 0:
        conso_hab_jour = (volume_total_annuel * 1000) / population_cartes_sociales / jours_couverts
    else:
        conso_hab_jour = 0

    # Statistiques par mois (agrégées en base)
    par_mois = {
        row['mois']: row
        for row in consos_qs.annotate(mois=ExtractMonth('date')).values('mois').annotate(
            volume=Sum('volume_total'),
            montant=Sum('montant_paye'),
            nb_cartes=Count('carte_sociale', distinct=True),
        )
    }

    stats_par_mois = []
    for mois in mois_clos:
        row = par_mois.get(mois, {})
        volume_mois = float(row.get('volume') or 0)
        jours_mois = calendar.monthrange(annee_int, mois)[1]
        if population_cartes_sociales > 0:
            conso_hab_mois = (volume_mois * 1000) / population_cartes_sociales / jours_mois
        else:
            conso_hab_mois = 0

        stats_par_mois.append({
            'mois': mois,
            'mois_nom': MOIS_NOMS[mois - 1],
            'volume_total': round(volume_mois, 2),
            'montant_total': round(float(row.get('montant') or 0), 2),
            'nb_cartes_actives': row.get('nb_cartes') or 0,
            'conso_hab_jour': round(conso_hab_mois, 1)
        })

    # Préparer les données pour les graphiques
    graphique_volumes = {
        'labels': [MOIS_COURTS[s['mois'] - 1] for s in stats_par_mois],
        'volumes': [s['volume_total'] for s in stats_par_mois],
        'montants': [s['montant_total'] for s in stats_par_mois],
        'nb_cartes': [s['nb_cartes_actives'] for s in stats_par_mois],
        'conso_hab': [s['conso_hab_jour'] for s in stats_par_mois]
    }

    # Listes pour les filtres
    regions = Region.objects.all().order_by('nom_region')
    districts = District.objects.all().order_by('nom_district')
    communes = Commune.objects.all().order_by('nom_commune')
    villages = Village.objects.all().order_by('nom_village')
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    context = {
        'annee_filter': annee_filter,
        'annee_int': annee_int,
        'annees_liste': list(range(2020, timezone.localdate().year + 1)),
        'periode_label': periode_label(annee_int, mois_clos),
        'nb_cartes_sociales': nb_cartes_sociales,
        'population_cartes_sociales': population_cartes_sociales,
        'volume_total_annuel': round(volume_total_annuel, 2),
        'montant_total_annuel': round(montant_total_annuel, 2),
        'conso_moyenne_par_carte': round(conso_moyenne_par_carte, 2),
        'conso_hab_jour_annuelle': round(conso_hab_jour, 1),
        'stats_par_mois': stats_par_mois,
        'graphique_volumes': json.dumps(graphique_volumes),
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'villages': villages,
        'ouvrages': ouvrages,
        'region_id': region_id or '',
        'district_id': district_id or '',
        'commune_id': commune_id or '',
        'village_id': village_id or '',
        'ouvrage_id': ouvrage_id or ''
    }

    return render(request, 'planning/analyse_cartes_sociales.html', context)


def evaluer_ouvrage(conso_hab_jour, taux_activite):
    """
    Classe un ouvrage pour la comparaison.
    Retourne (libellé, classe de badge DaisyUI).
    """
    # Seuils calés sur le terrain (moyenne observée ~0,6 L/hab/jour), pas sur les normes OMS
    if not conso_hab_jour and not taux_activite:
        return ('Aucune conso', 'badge-ghost')
    if taux_activite < 30:
        return ('Cartes peu utilisées', 'badge-error')
    if conso_hab_jour < 0.5:
        return ('Faible usage', 'badge-warning')
    if conso_hab_jour >= 1.5 and taux_activite >= 60:
        return ('Bon usage', 'badge-success')
    return ('Usage moyen', 'badge-info')


@login_required
def comparaison_ouvrages_cartes_sociales(request):
    """
    Compare la consommation des cartes sociales entre ouvrages (mois clos uniquement).
    """
    annee_filter = request.GET.get('annee', str(timezone.localdate().year))
    try:
        annee_int = int(annee_filter)
    except ValueError:
        annee_int = timezone.localdate().year

    region_id = request.GET.get('region') or ''
    district_id = request.GET.get('district') or ''
    commune_id = request.GET.get('commune') or ''
    village_id = request.GET.get('village') or ''
    ouvrage_ids = [o for o in request.GET.getlist('ouvrages') if o and o != 'all']
    tri = request.GET.get('tri', 'conso_hab_jour')

    mois_clos = mois_clos_pour_annee(annee_int)
    jours_couverts = sum(calendar.monthrange(annee_int, m)[1] for m in mois_clos)

    cartes_qs = filtrer_cartes_par_zone(
        CarteSociale.objects.filter(statut='active'),
        region_id, district_id, commune_id, village_id, ouvrage_ids or None,
    )
    cartes_ids = cartes_qs.values('id')

    # Cartes et population par ouvrage (4 personnes par carte si non renseigné)
    population_expr = Case(
        When(nombre_habitants__gt=0, then=F('nombre_habitants')),
        default=Value(4),
        output_field=IntegerField(),
    )
    lignes = {}
    for row in (CarteSociale.objects.filter(id__in=cartes_ids)
                .values('ouvrage_id', 'ouvrage__nom_ouvrage')
                .annotate(nb_cartes=Count('id'), population=Sum(population_expr))):
        lignes[row['ouvrage_id']] = {
            'ouvrage_id': str(row['ouvrage_id']),
            'nom': row['ouvrage__nom_ouvrage'],
            'nb_cartes': row['nb_cartes'],
            'population': row['population'] or 0,
            'volume': 0.0,
            'montant': 0.0,
            'cartes_consommatrices': 0,
            'volumes_mois': {m: 0.0 for m in mois_clos},
            'cartes_mois': {m: 0 for m in mois_clos},
        }

    consos_qs = ConsoCarteSociale.objects.filter(
        carte_sociale__in=cartes_ids,
        date__year=annee_int,
        date__month__in=mois_clos,
    )
    for row in (consos_qs.values('carte_sociale__ouvrage_id')
                .annotate(volume=Sum('volume_total'), montant=Sum('montant_paye'),
                          cartes=Count('carte_sociale', distinct=True))):
        ligne = lignes.get(row['carte_sociale__ouvrage_id'])
        if ligne:
            ligne['volume'] = float(row['volume'] or 0)
            ligne['montant'] = float(row['montant'] or 0)
            ligne['cartes_consommatrices'] = row['cartes']

    for row in (consos_qs.annotate(mois=ExtractMonth('date'))
                .values('carte_sociale__ouvrage_id', 'mois')
                .annotate(volume=Sum('volume_total'), cartes=Count('carte_sociale', distinct=True))):
        ligne = lignes.get(row['carte_sociale__ouvrage_id'])
        if ligne and row['mois'] in ligne['volumes_mois']:
            ligne['volumes_mois'][row['mois']] = round(float(row['volume'] or 0), 2)
            ligne['cartes_mois'][row['mois']] = row['cartes']

    comparaison = []
    for ligne in lignes.values():
        pop = ligne['population']
        nb = ligne['nb_cartes']
        ligne['conso_hab_jour'] = round(ligne['volume'] * 1000 / pop / jours_couverts, 1) if pop and jours_couverts else 0
        ligne['conso_par_carte'] = round(ligne['volume'] / nb, 2) if nb else 0
        ligne['taux_activite'] = round(100 * ligne['cartes_consommatrices'] / nb, 1) if nb else 0
        ligne['prix_m3'] = round(ligne['montant'] / ligne['volume']) if ligne['volume'] else 0
        ligne['volume'] = round(ligne['volume'], 2)
        ligne['montant'] = round(ligne['montant'])
        ligne['serie_mois'] = [ligne['volumes_mois'][m] for m in mois_clos]
        ligne['serie_cartes_mois'] = [ligne['cartes_mois'][m] for m in mois_clos]
        ligne['evaluation'], ligne['evaluation_badge'] = evaluer_ouvrage(ligne['conso_hab_jour'], ligne['taux_activite'])
        comparaison.append(ligne)

    tris_autorises = {
        'conso_hab_jour': 'Conso/hab/jour', 'volume': 'Volume', 'montant': 'Montant',
        'nb_cartes': 'Nb cartes', 'taux_activite': "Taux d'activité", 'conso_par_carte': 'Conso/carte',
    }
    if tri not in tris_autorises:
        tri = 'conso_hab_jour'
    comparaison.sort(key=lambda l: (l[tri], l['nom'] or ''), reverse=True)

    # Moyenne de référence sur l'ensemble du périmètre
    total_volume = sum(l['volume'] for l in comparaison)
    total_population = sum(l['population'] for l in comparaison)
    moyenne_hab_jour = round(total_volume * 1000 / total_population / jours_couverts, 1) if total_population and jours_couverts else 0

    graphique = {
        'labels': [l['nom'] for l in comparaison],
        'conso_hab_jour': [l['conso_hab_jour'] for l in comparaison],
        'moyenne_hab_jour': moyenne_hab_jour,
        'mois': [MOIS_COURTS[m - 1] for m in mois_clos],
        'series': [{'nom': l['nom'], 'data': l['serie_mois']} for l in comparaison[:10]],
        'series_cartes': [{'nom': l['nom'], 'data': l['serie_cartes_mois']} for l in comparaison[:10]],
    }
    # Une carte n'appartient qu'à un ouvrage : le total mensuel est la somme des ouvrages
    total_cartes_mois = [sum(l['serie_cartes_mois'][i] for l in comparaison) for i in range(len(mois_clos))]

    ouvrages_selectionnables = Ouvrage.objects.filter(
        cartes_sociales_infra__statut='active'
    ).distinct().order_by('nom_ouvrage')

    context = {
        'annee_int': annee_int,
        'annees_liste': list(range(2020, timezone.localdate().year + 1)),
        'periode_label': periode_label(annee_int, mois_clos),
        'mois_clos_noms': [MOIS_COURTS[m - 1] for m in mois_clos],
        'comparaison': comparaison,
        'nb_ouvrages': len(comparaison),
        'total_cartes': sum(l['nb_cartes'] for l in comparaison),
        'total_cartes_mois': total_cartes_mois,
        'total_volume': round(total_volume, 2),
        'total_montant': sum(l['montant'] for l in comparaison),
        'moyenne_hab_jour': moyenne_hab_jour,
        'graphique': json.dumps(graphique),
        'tri': tri,
        'tris_autorises': tris_autorises,
        'regions': Region.objects.all().order_by('nom_region'),
        'districts': District.objects.all().order_by('nom_district'),
        'communes': Commune.objects.all().order_by('nom_commune'),
        'villages': Village.objects.all().order_by('nom_village'),
        'ouvrages': ouvrages_selectionnables,
        'region_id': region_id,
        'district_id': district_id,
        'commune_id': commune_id,
        'village_id': village_id,
        'ouvrage_ids': ouvrage_ids,
    }
    return render(request, 'planning/comparaison_ouvrages_cartes_sociales.html', context)
