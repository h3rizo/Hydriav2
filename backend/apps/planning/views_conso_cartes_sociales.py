from django.shortcuts import render
from django.db.models import Q, Sum, Count, F, Avg, Case, When, IntegerField
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import json
import pytz

from apps.billing.models import PointEau, Releve, ModaliteGestion
from apps.geography.models import Commune, District, Region
from apps.organization.models import Ouvrage
from apps.infrastructure.models import CarteSociale
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_user_accessible_gestionnaire_ids,
)


def _get_scoped_cartes_sociales_ouvrage_ids(user):
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    modalites_qs = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['au_volume', 'mixte']
    )
    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            modalites_qs = modalites_qs.filter(gestionnaire_id__in=gestionnaire_ids)
        else:
            modalites_qs = modalites_qs.none()

    ouvrage_ids = set(modalites_qs.values_list('ouvrage_id', flat=True).distinct())
    return apply_user_responsable_ouvrage_scope(
        ouvrage_ids,
        user,
        allow_same_base_support_roles=True,
    )


def gestion_conso_cartes_sociales_global(request):
    """Vue globale des paiements cartes sociales par commune"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    region_filter = request.GET.get('region', '')
    district_filter = request.GET.get('district', '')
    communes_filter = request.GET.getlist('communes')  # Peut être multiple
    ouvrage_id = request.GET.get('ouvrage', '')

    # Récupérer les modalités actives (au volume ou mixte)
    modalites_ids = _get_scoped_cartes_sociales_ouvrage_ids(request.user)

    # Récupérer les points d'eau qui ont des cartes sociales actives
    points_eau_avec_cartes = PointEau.objects.filter(
        ouvrage_id__in=modalites_ids,
        cartes_sociales__statut='active'
    ).distinct().select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district__region'
    )

    # Appliquer filtres géographiques
    if region_filter:
        points_eau_avec_cartes = points_eau_avec_cartes.filter(
            parcelle__village__fokontany__commune__district__region_id=region_filter
        )
    if district_filter:
        points_eau_avec_cartes = points_eau_avec_cartes.filter(
            parcelle__village__fokontany__commune__district_id=district_filter
        )
    if communes_filter:
        points_eau_avec_cartes = points_eau_avec_cartes.filter(
            parcelle__village__fokontany__commune_id__in=communes_filter
        )
    if ouvrage_id:
        points_eau_avec_cartes = points_eau_avec_cartes.filter(ouvrage_id=ouvrage_id)

    # Récupérer TOUS les relevés de ces points d'eau (pas de filtre volume_carte_sociale)
    points_eau_ids = points_eau_avec_cartes.values_list('id', flat=True)
    releves = Releve.objects.filter(
        point_eau_id__in=points_eau_ids
    ).select_related(
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune__district__region'
    )

    # Filtrer par année (en Python pour gérer le timezone)
    releves_filtres = []
    for releve in releves:
        if releve.datereleve:
            # Vérifier si c'est un datetime ou un date
            if hasattr(releve.datereleve, 'tzinfo'):
                # C'est un datetime
                date_aware = releve.datereleve if releve.datereleve.tzinfo else timezone.make_aware(releve.datereleve)
                date_madagascar = date_aware.astimezone(tz_madagascar)
                annee = date_madagascar.year
            else:
                # C'est un date (pas de timezone)
                annee = releve.datereleve.year

            if annee == int(annee_filter):
                releves_filtres.append(releve)

    # Grouper hiérarchiquement par région > district > commune
    data_hierarchique = {}
    for releve in releves_filtres:
        if releve.point_eau and releve.point_eau.parcelle:
            village = releve.point_eau.parcelle.village
            fokontany = village.fokontany
            commune = fokontany.commune
            district = commune.district
            region = district.region

            # Initialiser la structure si nécessaire
            region_nom = region.nom_region
            if region_nom not in data_hierarchique:
                data_hierarchique[region_nom] = {
                    'region': region,
                    'districts': {},
                    'nombre_total': 0,
                    'nombre_payes': 0,
                    'nombre_non_payes': 0,
                    'nombre_cartes': 0
                }

            district_nom = district.nom_district
            if district_nom not in data_hierarchique[region_nom]['districts']:
                data_hierarchique[region_nom]['districts'][district_nom] = {
                    'district': district,
                    'communes': {},
                    'nombre_total': 0,
                    'nombre_payes': 0,
                    'nombre_non_payes': 0,
                    'nombre_cartes': 0
                }

            commune_nom = commune.nom_commune
            if commune_nom not in data_hierarchique[region_nom]['districts'][district_nom]['communes']:
                data_hierarchique[region_nom]['districts'][district_nom]['communes'][commune_nom] = {
                    'commune': commune,
                    'nombre_total': 0,
                    'nombre_payes': 0,
                    'nombre_non_payes': 0,
                    'points_eau': set(),
                    'cartes_sociales': set()
                }

            # Compter payés vs non payés (basé sur numeroDiameX uniquement)
            est_paye = releve.numeroDiameX is not None and releve.numeroDiameX.strip() != ''

            # Commune level
            commune_data = data_hierarchique[region_nom]['districts'][district_nom]['communes'][commune_nom]
            commune_data['nombre_total'] += 1
            commune_data['points_eau'].add(releve.point_eau.nomabonne)

            # Compter les cartes sociales actives pour ce point d'eau
            nb_cartes = releve.point_eau.cartes_sociales.filter(statut='active').count()
            if nb_cartes > 0:
                for carte in releve.point_eau.cartes_sociales.filter(statut='active'):
                    commune_data['cartes_sociales'].add(carte.id)

            if est_paye:
                commune_data['nombre_payes'] += 1
            else:
                commune_data['nombre_non_payes'] += 1

            # District level
            district_data = data_hierarchique[region_nom]['districts'][district_nom]
            district_data['nombre_total'] += 1
            if est_paye:
                district_data['nombre_payes'] += 1
            else:
                district_data['nombre_non_payes'] += 1

            # Region level
            region_data = data_hierarchique[region_nom]
            region_data['nombre_total'] += 1
            if est_paye:
                region_data['nombre_payes'] += 1
            else:
                region_data['nombre_non_payes'] += 1

    # Calculer les totaux et pourcentages
    for region_nom, region_data in data_hierarchique.items():
        # Calculer taux région
        if region_data['nombre_total'] > 0:
            region_data['taux_paiement'] = int((region_data['nombre_payes'] / region_data['nombre_total']) * 100)
        else:
            region_data['taux_paiement'] = 0

        # Compter cartes au niveau région
        cartes_region = set()
        for district_nom, district_data in region_data['districts'].items():
            # Calculer taux district
            if district_data['nombre_total'] > 0:
                district_data['taux_paiement'] = int((district_data['nombre_payes'] / district_data['nombre_total']) * 100)
            else:
                district_data['taux_paiement'] = 0

            # Compter cartes au niveau district
            cartes_district = set()
            for commune_nom, commune_data in district_data['communes'].items():
                # Commune: convertir sets et calculer
                commune_data['nombre_points_eau'] = len(commune_data['points_eau'])
                commune_data['nombre_cartes'] = len(commune_data['cartes_sociales'])
                commune_data['points_eau'] = list(commune_data['points_eau'])

                # Calculer taux commune
                if commune_data['nombre_total'] > 0:
                    commune_data['taux_paiement'] = int((commune_data['nombre_payes'] / commune_data['nombre_total']) * 100)
                else:
                    commune_data['taux_paiement'] = 0

                # Agréger cartes pour district et région
                cartes_district.update(commune_data['cartes_sociales'])
                cartes_region.update(commune_data['cartes_sociales'])

                del commune_data['cartes_sociales']  # Supprimer le set (pas nécessaire dans le template)

            district_data['nombre_cartes'] = len(cartes_district)

        region_data['nombre_cartes'] = len(cartes_region)

    # Statistiques globales
    nombre_total = sum(r['nombre_total'] for r in data_hierarchique.values())
    nombre_payes = sum(r['nombre_payes'] for r in data_hierarchique.values())
    nombre_non_payes = sum(r['nombre_non_payes'] for r in data_hierarchique.values())
    taux_global = int((nombre_payes / nombre_total * 100)) if nombre_total > 0 else 0

    # Compter communes total
    nombre_communes = sum(
        len(region_data['districts'][district_nom]['communes'])
        for region_data in data_hierarchique.values()
        for district_nom in region_data['districts'].keys()
    )

    # Listes pour les dropdowns
    regions = Region.objects.all().order_by('nom_region')
    districts = District.objects.all().order_by('nom_district')
    communes = Commune.objects.all().order_by('nom_commune')
    ouvrages = Ouvrage.objects.filter(id__in=modalites_ids).order_by('nom_ouvrage')

    context = {
        'data_hierarchique': data_hierarchique,
        'nombre_total': nombre_total,
        'nombre_payes': nombre_payes,
        'nombre_non_payes': nombre_non_payes,
        'taux_global': taux_global,
        'nombre_communes': nombre_communes,
        'annee_filter': annee_filter,
        'region_filter': region_filter,
        'district_filter': district_filter,
        'communes_filter': communes_filter,
        'ouvrage_id': ouvrage_id,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
    }

    return render(request, 'planning/conso_cartes_sociales_global.html', context)


@require_http_methods(["GET"])
def api_commune_details(request, commune_id):
    """API pour récupérer les détails d'une commune pour le modal"""
    try:
        # Timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Récupérer la commune
        commune = Commune.objects.select_related('district__region').get(id=commune_id)

        # Année filtre
        annee_filter = request.GET.get('annee', str(datetime.now().year))

        # Récupérer les modalités actives (au volume ou mixte)
        modalites_ids = _get_scoped_cartes_sociales_ouvrage_ids(request.user)

        # Récupérer les points d'eau de cette commune avec cartes sociales actives
        points_eau_avec_cartes = PointEau.objects.filter(
            ouvrage_id__in=modalites_ids,
            cartes_sociales__statut='active',
            parcelle__village__fokontany__commune_id=commune_id
        ).distinct().select_related('ouvrage')

        # Récupérer TOUS les relevés de ces points d'eau
        points_eau_ids = points_eau_avec_cartes.values_list('id', flat=True)
        releves = Releve.objects.filter(
            point_eau_id__in=points_eau_ids
        ).select_related('point_eau', 'point_eau__ouvrage')

        # Filtrer par année (en Python pour gérer le timezone)
        releves_filtres = []
        for releve in releves:
            if releve.datereleve:
                if hasattr(releve.datereleve, 'tzinfo'):
                    date_aware = releve.datereleve if releve.datereleve.tzinfo else timezone.make_aware(releve.datereleve)
                    date_madagascar = date_aware.astimezone(tz_madagascar)
                    annee = date_madagascar.year
                else:
                    annee = releve.datereleve.year

                if annee == int(annee_filter):
                    releves_filtres.append(releve)

        # Grouper par point d'eau
        data_points_eau = {}
        for releve in releves_filtres:
            if releve.point_eau:
                pe_nom = releve.point_eau.nomabonne

                if pe_nom not in data_points_eau:
                    # Compter cartes sociales actives
                    nb_cartes = releve.point_eau.cartes_sociales.filter(statut='active').count()

                    data_points_eau[pe_nom] = {
                        'id': str(releve.point_eau.id),
                        'nom': pe_nom,
                        'ouvrage': releve.point_eau.ouvrage.nom_ouvrage if releve.point_eau.ouvrage else '',
                        'nombre_cartes': nb_cartes,
                        'nombre_total': 0,
                        'nombre_payes': 0,
                        'nombre_non_payes': 0,
                    }

                # Compter payés vs non payés
                est_paye = releve.numeroDiameX is not None and releve.numeroDiameX.strip() != ''

                data_points_eau[pe_nom]['nombre_total'] += 1
                if est_paye:
                    data_points_eau[pe_nom]['nombre_payes'] += 1
                else:
                    data_points_eau[pe_nom]['nombre_non_payes'] += 1

        # Calculer taux de paiement pour chaque point d'eau
        for pe_data in data_points_eau.values():
            if pe_data['nombre_total'] > 0:
                pe_data['taux_paiement'] = int((pe_data['nombre_payes'] / pe_data['nombre_total']) * 100)
            else:
                pe_data['taux_paiement'] = 0

        # Statistiques globales de la commune
        nombre_total = sum(pe['nombre_total'] for pe in data_points_eau.values())
        nombre_payes = sum(pe['nombre_payes'] for pe in data_points_eau.values())
        nombre_non_payes = sum(pe['nombre_non_payes'] for pe in data_points_eau.values())
        taux_global = int((nombre_payes / nombre_total * 100)) if nombre_total > 0 else 0
        nombre_cartes_total = sum(pe['nombre_cartes'] for pe in data_points_eau.values())

        return JsonResponse({
            'success': True,
            'commune': {
                'nom': commune.nom_commune,
                'district': commune.district.nom_district,
                'region': commune.district.region.nom_region
            },
            'stats': {
                'nombre_total': nombre_total,
                'nombre_payes': nombre_payes,
                'nombre_non_payes': nombre_non_payes,
                'taux_global': taux_global,
                'nombre_points_eau': len(data_points_eau),
                'nombre_cartes': nombre_cartes_total
            },
            'points_eau': list(data_points_eau.values())
        })

    except Commune.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Commune introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def gestion_conso_cartes_sociales(request):
    """Vue détaillée des paiements cartes sociales par point d'eau avec hiérarchie Région → District → Commune → Ouvrage"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))

    # Récupérer les modalités actives
    modalites_ids = _get_scoped_cartes_sociales_ouvrage_ids(request.user)

    # Filtrer les points d'eau qui ont des cartes sociales
    points_eau = PointEau.objects.filter(
        ouvrage_id__in=modalites_ids,
        cartes_sociales__statut='active'
    ).distinct().select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune__district__region'
    ).order_by(
        'parcelle__village__fokontany__commune__district__region__nom_region',
        'parcelle__village__fokontany__commune__district__nom_district',
        'parcelle__village__fokontany__commune__nom_commune',
        'ouvrage__nom_ouvrage',
        'nomabonne'
    )

    # Structure hiérarchique : Région → District → Commune → Ouvrage → Points d'eau
    hierarchie = {}
    total_cartes = 0
    nombre_total_releves = 0
    nombre_payes = 0
    nombre_non_payes = 0

    for pe in points_eau:
        # Récupérer hiérarchie géographique
        if not pe.parcelle or not pe.parcelle.village:
            continue

        region = pe.parcelle.village.fokontany.commune.district.region
        district = pe.parcelle.village.fokontany.commune.district
        commune = pe.parcelle.village.fokontany.commune
        ouvrage = pe.ouvrage

        region_nom = region.nom_region
        district_nom = district.nom_district
        commune_nom = commune.nom_commune
        ouvrage_nom = ouvrage.nom_ouvrage

        # Initialiser structure
        if region_nom not in hierarchie:
            hierarchie[region_nom] = {
                'region': region,
                'districts': {},
                'stats': {'cartes': 0, 'releves': 0, 'payes': 0, 'non_payes': 0}
            }

        if district_nom not in hierarchie[region_nom]['districts']:
            hierarchie[region_nom]['districts'][district_nom] = {
                'district': district,
                'communes': {},
                'stats': {'cartes': 0, 'releves': 0, 'payes': 0, 'non_payes': 0}
            }

        if commune_nom not in hierarchie[region_nom]['districts'][district_nom]['communes']:
            hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom] = {
                'commune': commune,
                'ouvrages': {},
                'stats': {'cartes': 0, 'releves': 0, 'payes': 0, 'non_payes': 0}
            }

        if ouvrage_nom not in hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['ouvrages']:
            hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['ouvrages'][ouvrage_nom] = {
                'ouvrage': ouvrage,
                'points_eau': [],
                'stats': {'cartes': 0, 'releves': 0, 'payes': 0, 'non_payes': 0}
            }

        # Récupérer les cartes sociales actives pour ce point d'eau
        cartes_actives = pe.cartes_sociales.filter(statut='active')
        nb_cartes = cartes_actives.count()
        total_habitants = cartes_actives.aggregate(
            total=Sum('nombre_habitants')
        )['total'] or 0

        # Préparer les données par carte sociale avec paiements mensuels
        cartes_data = []
        total_payes_pe = 0
        total_non_payes_pe = 0

        for carte in cartes_actives:
            # Récupérer TOUS les relevés du point d'eau (pas de filtre volume_carte_sociale)
            releves = Releve.objects.filter(
                point_eau=pe
            ).order_by('datereleve')

            # Regrouper par mois
            paiements_par_mois = {i: {'paye': False, 'releve_id': None} for i in range(1, 13)}

            for releve in releves:
                if releve.datereleve:
                    if hasattr(releve.datereleve, 'tzinfo'):
                        date_aware = releve.datereleve if releve.datereleve.tzinfo else timezone.make_aware(releve.datereleve)
                        date_madagascar = date_aware.astimezone(tz_madagascar)
                        annee = date_madagascar.year
                        mois = date_madagascar.month
                    else:
                        annee = releve.datereleve.year
                        mois = releve.datereleve.month

                    if annee == int(annee_filter):
                        # Vérifier si payé (numeroDiameX renseigné)
                        est_paye = releve.numeroDiameX and releve.numeroDiameX.strip() != ''
                        paiements_par_mois[mois] = {
                            'paye': est_paye,
                            'releve_id': releve.id
                        }

            # Compter payés/non payés pour cette carte
            nb_payes_carte = sum(1 for m in range(1, 13) if paiements_par_mois[m]['paye'])
            nb_releves_carte = sum(1 for m in range(1, 13) if paiements_par_mois[m]['releve_id'] is not None)
            nb_non_payes_carte = nb_releves_carte - nb_payes_carte

            total_payes_pe += nb_payes_carte
            total_non_payes_pe += nb_non_payes_carte

            cartes_data.append({
                'carte': carte,
                'numero': carte.numero_carte or f"CS-{str(carte.id)[:8]}",
                'beneficiaire': carte.nom_beneficiaire,
                'habitants': carte.nombre_habitants or 0,
                'paiements_par_mois': paiements_par_mois,  # {1: {'paye': True/False, 'releve_id': ...}, ...}
                'nb_payes': nb_payes_carte,
                'nb_non_payes': nb_non_payes_carte,
            })

        nb_releves_pe = total_payes_pe + total_non_payes_pe
        taux_paiement_pe = int((total_payes_pe / nb_releves_pe * 100)) if nb_releves_pe > 0 else 0

        # Ajouter au point d'eau
        hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['ouvrages'][ouvrage_nom]['points_eau'].append({
            'point_eau': pe,
            'nb_cartes': nb_cartes,
            'total_habitants': total_habitants,
            'nb_releves': nb_releves_pe,
            'nb_payes': total_payes_pe,
            'nb_non_payes': total_non_payes_pe,
            'taux_paiement': taux_paiement_pe,
            'cartes': cartes_data,  # Liste des cartes avec paiements mensuels
        })

        # Compter le nombre de relevés pour ce point d'eau (somme des relevés de toutes les cartes)
        nb_releves_pe = sum(1 for m in range(1, 13)
                           for carte in cartes_data
                           if carte['paiements_par_mois'][m]['releve_id'] is not None)

        # Cumuler dans stats ouvrage
        hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['ouvrages'][ouvrage_nom]['stats']['cartes'] += nb_cartes
        hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['ouvrages'][ouvrage_nom]['stats']['releves'] += nb_releves_pe
        hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['ouvrages'][ouvrage_nom]['stats']['payes'] += total_payes_pe
        hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['ouvrages'][ouvrage_nom]['stats']['non_payes'] += total_non_payes_pe

        # Cumuler dans stats commune
        hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['stats']['cartes'] += nb_cartes
        hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['stats']['releves'] += nb_releves_pe
        hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['stats']['payes'] += total_payes_pe
        hierarchie[region_nom]['districts'][district_nom]['communes'][commune_nom]['stats']['non_payes'] += total_non_payes_pe

        # Cumuler dans stats district
        hierarchie[region_nom]['districts'][district_nom]['stats']['cartes'] += nb_cartes
        hierarchie[region_nom]['districts'][district_nom]['stats']['releves'] += nb_releves_pe
        hierarchie[region_nom]['districts'][district_nom]['stats']['payes'] += total_payes_pe
        hierarchie[region_nom]['districts'][district_nom]['stats']['non_payes'] += total_non_payes_pe

        # Cumuler dans stats région
        hierarchie[region_nom]['stats']['cartes'] += nb_cartes
        hierarchie[region_nom]['stats']['releves'] += nb_releves_pe
        hierarchie[region_nom]['stats']['payes'] += total_payes_pe
        hierarchie[region_nom]['stats']['non_payes'] += total_non_payes_pe

        # Cumuler dans totaux globaux
        total_cartes += nb_cartes
        nombre_total_releves += nb_releves_pe
        nombre_payes += total_payes_pe
        nombre_non_payes += total_non_payes_pe

    taux_global = int((nombre_payes / nombre_total_releves * 100)) if nombre_total_releves > 0 else 0

    context = {
        'hierarchie': hierarchie,
        'total_cartes': total_cartes,
        'nombre_total': nombre_total_releves,
        'nombre_payes': nombre_payes,
        'nombre_non_payes': nombre_non_payes,
        'taux_global': taux_global,
        'annee_filter': annee_filter,
    }

    return render(request, 'planning/conso_cartes_sociales.html', context)


def impression_conso_cartes_sociales(request):
    """Page d'impression des paiements cartes sociales (hiérarchie commune → ouvrage → point d'eau → mois)"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    commune_filter = request.GET.get('commune', '')  # Filtre unique au lieu de multi-sélection
    ouvrage_id = request.GET.get('ouvrage', '')

    # Récupérer les modalités actives
    modalites_ids = _get_scoped_cartes_sociales_ouvrage_ids(request.user)

    # Récupérer les points d'eau qui ont des cartes sociales actives
    points_eau_avec_cartes = PointEau.objects.filter(
        ouvrage_id__in=modalites_ids,
        cartes_sociales__statut='active'
    ).distinct().select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune'
    )

    if commune_filter:
        points_eau_avec_cartes = points_eau_avec_cartes.filter(
            parcelle__village__fokontany__commune_id=commune_filter
        )
    if ouvrage_id:
        points_eau_avec_cartes = points_eau_avec_cartes.filter(ouvrage_id=ouvrage_id)

    # Récupérer TOUS les relevés de ces points d'eau (pas de filtre volume_carte_sociale)
    points_eau_ids = points_eau_avec_cartes.values_list('id', flat=True)
    releves = Releve.objects.filter(
        point_eau_id__in=points_eau_ids
    ).select_related(
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune'
    )

    # Filtrer par année
    releves_filtres = []
    for releve in releves:
        if releve.datereleve:
            # Vérifier si c'est un datetime ou un date
            if hasattr(releve.datereleve, 'tzinfo'):
                # C'est un datetime
                date_aware = releve.datereleve if releve.datereleve.tzinfo else timezone.make_aware(releve.datereleve)
                date_madagascar = date_aware.astimezone(tz_madagascar)
                annee = date_madagascar.year
            else:
                # C'est un date (pas de timezone)
                annee = releve.datereleve.year

            if annee == int(annee_filter):
                releves_filtres.append(releve)

    # Grouper par commune → ouvrage → point d'eau → carte → mois
    data_par_commune = {}

    for pe in points_eau_avec_cartes:
        if not pe.parcelle or not pe.parcelle.village:
            continue

        commune = pe.parcelle.village.fokontany.commune
        commune_nom = commune.nom_commune
        ouvrage_nom = pe.ouvrage.nom_ouvrage
        point_eau_nom = pe.nomabonne

        # Initialiser structure
        if commune_nom not in data_par_commune:
            data_par_commune[commune_nom] = {
                'commune': commune,
                'ouvrages': {},
                'total_payes': 0,
                'total_non_payes': 0,
            }

        if ouvrage_nom not in data_par_commune[commune_nom]['ouvrages']:
            data_par_commune[commune_nom]['ouvrages'][ouvrage_nom] = {
                'ouvrage': pe.ouvrage,
                'points_eau': {},
                'total_payes': 0,
                'total_non_payes': 0,
            }

        if point_eau_nom not in data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau']:
            data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'][point_eau_nom] = {
                'point_eau': pe,
                'cartes': {},  # Grouper par carte
                'total_payes': 0,
                'total_non_payes': 0,
            }

        # Récupérer les cartes sociales actives pour ce point d'eau
        cartes_actives = pe.cartes_sociales.filter(statut='active')

        for carte in cartes_actives:
            carte_numero = carte.numero_carte or f"CS-{str(carte.id)[:8]}"

            # Initialiser la carte
            if carte_numero not in data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'][point_eau_nom]['cartes']:
                data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'][point_eau_nom]['cartes'][carte_numero] = {
                    'carte': carte,
                    'numero': carte_numero,
                    'beneficiaire': carte.nom_beneficiaire,
                    'habitants': carte.nombre_habitants or 0,
                    'mois': {i: {'paye': False} for i in range(1, 13)},
                    'total_payes': 0,
                    'total_non_payes': 0,
                }

            # Récupérer tous les relevés du point d'eau pour cette année
            for releve in releves_filtres:
                if releve.point_eau_id != pe.id:
                    continue

                # Extraire le mois
                if hasattr(releve.datereleve, 'tzinfo'):
                    date_aware = releve.datereleve if releve.datereleve.tzinfo else timezone.make_aware(releve.datereleve)
                    date_madagascar = date_aware.astimezone(tz_madagascar)
                    mois = date_madagascar.month
                else:
                    mois = releve.datereleve.month

                # Vérifier si payé
                est_paye = releve.numeroDiameX is not None and releve.numeroDiameX.strip() != ''

                # Enregistrer le paiement pour cette carte ce mois-ci
                data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'][point_eau_nom]['cartes'][carte_numero]['mois'][mois] = {
                    'paye': est_paye
                }

            # Compter les paiements pour cette carte
            carte_data = data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'][point_eau_nom]['cartes'][carte_numero]
            nb_payes = sum(1 for m in range(1, 13) if carte_data['mois'][m]['paye'])
            nb_non_payes = sum(1 for m in range(1, 13) if not carte_data['mois'][m]['paye']) - (12 - len([m for m in range(1, 13) if carte_data['mois'][m]['paye']]))  # Compter seulement les mois avec relevés

            # Recalculer en comptant seulement les relevés existants
            nb_releves_carte = 0
            nb_payes_carte = 0
            for m in range(1, 13):
                # Vérifier si un relevé existe pour ce mois
                releve_existe = any(
                    releve.point_eau_id == pe.id and
                    (releve.datereleve.month if isinstance(releve.datereleve, datetime) else releve.datereleve.month) == m
                    for releve in releves_filtres
                )
                if releve_existe:
                    nb_releves_carte += 1
                    if carte_data['mois'][m]['paye']:
                        nb_payes_carte += 1

            nb_non_payes_carte = nb_releves_carte - nb_payes_carte

            carte_data['total_payes'] = nb_payes_carte
            carte_data['total_non_payes'] = nb_non_payes_carte

            # Cumuler dans le point d'eau
            data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'][point_eau_nom]['total_payes'] += nb_payes_carte
            data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'][point_eau_nom]['total_non_payes'] += nb_non_payes_carte

        # Cumuler dans l'ouvrage
        data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['total_payes'] = sum(
            pe_data['total_payes']
            for pe_data in data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'].values()
        )
        data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['total_non_payes'] = sum(
            pe_data['total_non_payes']
            for pe_data in data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'].values()
        )

        # Cumuler dans la commune
        data_par_commune[commune_nom]['total_payes'] = sum(
            ouvrage_data['total_payes']
            for ouvrage_data in data_par_commune[commune_nom]['ouvrages'].values()
        )
        data_par_commune[commune_nom]['total_non_payes'] = sum(
            ouvrage_data['total_non_payes']
            for ouvrage_data in data_par_commune[commune_nom]['ouvrages'].values()
        )

    # Totaux globaux
    total_payes = sum(c['total_payes'] for c in data_par_commune.values())
    total_non_payes = sum(c['total_non_payes'] for c in data_par_commune.values())

    # Labels des mois
    mois_labels = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']

    # Listes pour les filtres
    annees_disponibles = [2024, 2025, 2026]

    # Communes disponibles (avec cartes sociales actives)
    # Récupérer les IDs des communes depuis les points d'eau
    commune_ids = points_eau_avec_cartes.values_list(
        'parcelle__village__fokontany__commune_id', flat=True
    ).distinct()
    communes_disponibles = Commune.objects.filter(
        id__in=commune_ids
    ).order_by('nom_commune')

    # Ouvrages disponibles (avec modalités volumétriques/mixtes actives)
    # Ajouter commune_id pour le filtrage en cascade
    ouvrages_disponibles = []
    for ouvrage in Ouvrage.objects.filter(id__in=modalites_ids).order_by('nom_ouvrage'):
        # Récupérer la commune via la relation: Ouvrage → PointEau → Parcelle → Village → Fokontany → Commune
        commune = None
        point_eau = ouvrage.pointeau_set.select_related(
            'parcelle__village__fokontany__commune'
        ).first()
        if point_eau and point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany:
            commune = point_eau.parcelle.village.fokontany.commune

        # Créer un objet dictionnaire avec les données nécessaires
        ouvrage_data = {
            'id': str(ouvrage.id),
            'nom_ouvrage': ouvrage.nom_ouvrage,
            'commune_id': str(commune.id) if commune else '',
        }
        ouvrages_disponibles.append(ouvrage_data)

    context = {
        'data_par_commune': data_par_commune,
        'total_payes': total_payes,
        'total_non_payes': total_non_payes,
        'nombre_communes': len(data_par_commune),
        'annee_filter': annee_filter,
        'date_impression': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'mois_labels': mois_labels,
        # Données pour les filtres
        'annees_disponibles': annees_disponibles,
        'communes_disponibles': communes_disponibles,
        'ouvrages_disponibles': ouvrages_disponibles,
        'communes_filter': [commune_filter] if commune_filter else [],  # Liste avec une seule commune pour compatibilité template
        'ouvrage_id': ouvrage_id,
    }

    return render(request, 'planning/conso_cartes_sociales_impression.html', context)


def api_conso_cartes_sociales_data(request):
    """API JSON pour récupérer les données de paiements cartes sociales"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')

    # Récupérer les modalités actives
    modalites_ids = _get_scoped_cartes_sociales_ouvrage_ids(request.user)

    # Filtrer les points d'eau
    points_eau = PointEau.objects.filter(
        ouvrage_id__in=modalites_ids,
        cartes_sociales__statut='active'
    ).distinct().select_related('ouvrage', 'parcelle__village__fokontany__commune')

    if commune_id:
        points_eau = points_eau.filter(parcelle__village__fokontany__commune_id=commune_id)
    if ouvrage_id:
        points_eau = points_eau.filter(ouvrage_id=ouvrage_id)

    # Construire les données par point d'eau
    data = []
    for pe in points_eau:
        # Initialiser les paiements par mois
        paiements_mois = {i: {'payes': 0, 'non_payes': 0, 'montant': 0} for i in range(1, 13)}

        # Récupérer TOUS les relevés du point d'eau (pas de filtre volume_carte_sociale)
        releves = Releve.objects.filter(
            point_eau=pe
        ).order_by('datereleve')

        # Remplir les paiements réels
        for releve in releves:
            if releve.datereleve:
                # Vérifier si c'est un datetime ou un date
                if hasattr(releve.datereleve, 'tzinfo'):
                    # C'est un datetime
                    date_aware = releve.datereleve if releve.datereleve.tzinfo else timezone.make_aware(releve.datereleve)
                    date_madagascar = date_aware.astimezone(tz_madagascar)
                    annee = date_madagascar.year
                    mois = date_madagascar.month
                else:
                    # C'est un date (pas de timezone)
                    annee = releve.datereleve.year
                    mois = releve.datereleve.month

                if annee == int(annee_filter):
                    est_paye = releve.numeroDiameX is not None and releve.numeroDiameX.strip() != ''
                    montant = float(releve.montant or Decimal('0'))

                    if est_paye:
                        paiements_mois[mois]['payes'] += 1
                    else:
                        paiements_mois[mois]['non_payes'] += 1

                    paiements_mois[mois]['montant'] += montant

        # Nombre de cartes actives
        nb_cartes = pe.cartes_sociales.filter(statut='active').count()

        # Total annuel
        total_payes = sum(m['payes'] for m in paiements_mois.values())
        total_non_payes = sum(m['non_payes'] for m in paiements_mois.values())
        montant_total = sum(m['montant'] for m in paiements_mois.values())

        point_data = {
            'id': str(pe.id),
            'nom': pe.nomabonne,
            'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else '-',
            'commune': pe.parcelle.village.fokontany.commune.nom_commune if pe.parcelle else '-',
            'nb_cartes': nb_cartes,
            'paiements': list(paiements_mois.values()),
            'total_payes': total_payes,
            'total_non_payes': total_non_payes,
            'montant_total': round(montant_total, 2)
        }

        data.append(point_data)

    return JsonResponse({'success': True, 'data': data})
