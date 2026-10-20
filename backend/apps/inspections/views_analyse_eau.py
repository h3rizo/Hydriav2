"""
Vues pour la gestion des analyses d'eau.
"""

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count
from django.utils import timezone
from datetime import datetime
from decimal import Decimal
import json
import pytz
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from io import BytesIO

from .models_analyse_eau import AnalyseEau
from apps.infrastructure.models import EquipementConstitutif
from apps.billing.models import PointEau
from apps.geography.models import Commune
from apps.organization.scoping import get_user_accessible_gestionnaire_ids

# Timezone Madagascar (UTC+3)
tz_madagascar = pytz.timezone('Indian/Antananarivo')


def analyses_eau_list(request):
    """Page principale de gestion des analyses d'eau"""
    # Récupérer les communes pour le filtre
    communes = Commune.objects.all().order_by('nom_commune')

    # Récupérer les équipements avec leurs relations pour cascade
    equipements = EquipementConstitutif.objects.select_related(
        'ouvrage',
        'type_equipement'
    ).order_by('nom')

    # Récupérer les points d'eau avec leurs relations pour cascade
    points_eau = PointEau.objects.select_related(
        'ouvrage', 'parcelle__village__fokontany__commune',
        'type_point_eau'
    ).order_by('code_point_eau')

    # Récupérer les années disponibles
    annees = AnalyseEau.objects.dates('date_prelevement', 'year', order='DESC')
    annees_list = [d.year for d in annees]

    if not annees_list:
        annees_list = [datetime.now().year]

    # Préparer les données JSON pour le JavaScript (cascade de filtres)
    import json

    # Dictionnaire équipements par ouvrage et commune
    equipements_data = []
    for eq in equipements:
        commune_id = None
        # Récupérer commune via ouvrage → point d'eau → parcelle → village → fokontany → commune
        if eq.ouvrage:
            pe_premier = eq.ouvrage.pointeau_set.select_related(
                'parcelle__village__fokontany__commune'
            ).first()
            if pe_premier and pe_premier.parcelle:
                parcelle = pe_premier.parcelle
                if parcelle.village and parcelle.village.fokontany and parcelle.village.fokontany.commune:
                    commune_id = str(parcelle.village.fokontany.commune.id)

        equipements_data.append({
            'id': str(eq.id),
            'nom': eq.nom,
            'ouvrage_id': str(eq.ouvrage.id) if eq.ouvrage else None,
            'ouvrage_nom': eq.ouvrage.nom_ouvrage if eq.ouvrage else '',
            'commune_id': commune_id
        })

    # Dictionnaire points d'eau par ouvrage et commune
    points_eau_data = []
    for pe in points_eau:
        commune_id = None
        if pe.parcelle:
            if pe.parcelle.village and pe.parcelle.village.fokontany and pe.parcelle.village.fokontany.commune:
                commune_id = str(pe.parcelle.village.fokontany.commune.id)

        points_eau_data.append({
            'id': str(pe.id),
            'code': pe.code_point_eau,
            'ouvrage_id': str(pe.ouvrage.id) if pe.ouvrage else None,
            'ouvrage_nom': pe.ouvrage.nom_ouvrage if pe.ouvrage else '',
            'commune_id': commune_id
        })

    context = {
        'communes': communes,
        'equipements_json': json.dumps(equipements_data),
        'points_eau_json': json.dumps(points_eau_data),
        'annees': annees_list,
        'annee_actuelle': datetime.now().year,
        'cache_bust': int(datetime.now().timestamp() * 1000)  # Timestamp milliseconde pour cache busting
    }

    # Désactiver le cache pour cette page
    response = render(request, 'inspections/analyses_eau_list.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@require_http_methods(["GET"])
def api_analyses_eau_list(request):
    """API pour lister les analyses d'eau avec filtres"""
    try:
        # Récupérer tous les analyses
        analyses = AnalyseEau.objects.all().select_related(
            'equipement',
            'equipement__ouvrage',
            'point_eau',
            'point_eau__parcelle__village__fokontany__commune',
            'created_by'
        )

        # Filtres
        annee = request.GET.get('annee')
        commune_id = request.GET.get('commune_id')
        type_prelevement = request.GET.get('type_prelevement')
        resultat = request.GET.get('resultat')  # 'positif', 'negatif'
        search = request.GET.get('search', '').strip()

        if annee:
            analyses = analyses.filter(date_prelevement__year=int(annee))

        if type_prelevement:
            analyses = analyses.filter(type_prelevement=type_prelevement)

        # Filtre par résultat
        if resultat == 'positif':
            analyses = analyses.filter(
                Q(tnc=True) | Q(nombre_coliformes__gt=0)
            )
        elif resultat == 'negatif':
            analyses = analyses.filter(tnc=False, nombre_coliformes=0)

        # Recherche
        if search:
            analyses = analyses.filter(
                Q(description_lieu__icontains=search) |
                Q(observation__icontains=search) |
                Q(equipement__nom__icontains=search) |
                Q(point_eau__code_point_eau__icontains=search)
            )

        # Convertir en liste
        data = []
        for analyse in analyses:
            # Filtrer par commune si spécifié
            if commune_id and commune_id != 'all':
                if analyse.commune_nom != Commune.objects.get(id=commune_id).nom_commune:
                    continue

            # Convertir dates UTC → Madagascar AVANT formatage (TIMEZONE_GUIDE.md)
            date_prelevement_mg = analyse.date_prelevement.astimezone(tz_madagascar) if analyse.date_prelevement.tzinfo else tz_madagascar.localize(analyse.date_prelevement)
            date_analyse_mg = analyse.date_analyse.astimezone(tz_madagascar) if analyse.date_analyse.tzinfo else tz_madagascar.localize(analyse.date_analyse)
            date_resultat_mg = analyse.date_resultat.astimezone(tz_madagascar) if analyse.date_resultat.tzinfo else tz_madagascar.localize(analyse.date_resultat)

            data.append({
                'id': str(analyse.id),
                'type_prelevement': analyse.type_prelevement,
                'type_prelevement_display': analyse.get_type_prelevement_display(),
                'lieu': analyse.lieu_affichage,
                'description_lieu': analyse.description_lieu,
                'date_prelevement': date_prelevement_mg.strftime('%d/%m/%Y %H:%M'),
                'date_analyse': date_analyse_mg.strftime('%d/%m/%Y %H:%M'),
                'date_resultat': date_resultat_mg.strftime('%d/%m/%Y %H:%M'),
                'volume_analyse': analyse.volume_analyse,
                'nombre_coliformes': analyse.nombre_coliformes,
                'tnc': analyse.tnc,
                'nombre_pour_100ml': analyse.nombre_pour_100ml,
                'ph': float(analyse.ph) if analyse.ph else None,
                'observation': analyse.observation,
                'est_positif': analyse.est_positif,
                'commune': analyse.commune_nom,
                'village': analyse.village_nom,
                'equipement_id': str(analyse.equipement.id) if analyse.equipement else None,
                'point_eau_id': str(analyse.point_eau.id) if analyse.point_eau else None,
            })

        return JsonResponse({
            'success': True,
            'total': len(data),
            'data': data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_analyse_eau_create(request):
    """API pour créer une nouvelle analyse d'eau"""
    try:
        data = json.loads(request.body)

        # Validation des champs obligatoires
        required_fields = ['type_prelevement', 'date_prelevement', 'date_analyse',
                          'date_resultat', 'volume_analyse']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({
                    'success': False,
                    'error': f'Le champ {field} est obligatoire'
                }, status=400)

        # Créer l'analyse
        analyse = AnalyseEau(
            type_prelevement=data['type_prelevement'],
            date_prelevement=datetime.strptime(data['date_prelevement'], '%Y-%m-%dT%H:%M'),
            date_analyse=datetime.strptime(data['date_analyse'], '%Y-%m-%dT%H:%M'),
            date_resultat=datetime.strptime(data['date_resultat'], '%Y-%m-%dT%H:%M'),
            volume_analyse=int(data['volume_analyse']),
            description_lieu=data.get('description_lieu', ''),
            tnc=data.get('tnc', False),
            observation=data.get('observation', ''),
            created_by=request.user if request.user.is_authenticated else None
        )

        # Relations optionnelles
        if data.get('equipement_id'):
            try:
                analyse.equipement = EquipementConstitutif.objects.get(id=data['equipement_id'])
            except EquipementConstitutif.DoesNotExist:
                pass

        if data.get('point_eau_id'):
            try:
                analyse.point_eau = PointEau.objects.get(id=data['point_eau_id'])
            except PointEau.DoesNotExist:
                pass

        # Nombre de coliformes (uniquement si pas TNC)
        if not analyse.tnc and data.get('nombre_coliformes') is not None:
            analyse.nombre_coliformes = int(data['nombre_coliformes'])

        # pH
        if data.get('ph'):
            analyse.ph = Decimal(str(data['ph']))

        analyse.save()

        return JsonResponse({
            'success': True,
            'message': 'Analyse d\'eau créée avec succès',
            'id': str(analyse.id)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_analyse_eau_update(request, analyse_id):
    """API pour modifier une analyse d'eau"""
    try:
        analyse = AnalyseEau.objects.get(id=analyse_id)
        data = json.loads(request.body)

        # Mettre à jour les champs
        if 'type_prelevement' in data:
            analyse.type_prelevement = data['type_prelevement']

        if 'date_prelevement' in data:
            analyse.date_prelevement = datetime.strptime(data['date_prelevement'], '%Y-%m-%dT%H:%M')

        if 'date_analyse' in data:
            analyse.date_analyse = datetime.strptime(data['date_analyse'], '%Y-%m-%dT%H:%M')

        if 'date_resultat' in data:
            analyse.date_resultat = datetime.strptime(data['date_resultat'], '%Y-%m-%dT%H:%M')

        if 'volume_analyse' in data:
            analyse.volume_analyse = int(data['volume_analyse'])

        if 'description_lieu' in data:
            analyse.description_lieu = data['description_lieu']

        if 'tnc' in data:
            analyse.tnc = data['tnc']

        if 'nombre_coliformes' in data and not analyse.tnc:
            analyse.nombre_coliformes = int(data['nombre_coliformes']) if data['nombre_coliformes'] is not None else None

        if 'ph' in data:
            analyse.ph = Decimal(str(data['ph'])) if data['ph'] else None

        if 'observation' in data:
            analyse.observation = data['observation']

        # Relations
        if 'equipement_id' in data:
            if data['equipement_id']:
                try:
                    analyse.equipement = EquipementConstitutif.objects.get(id=data['equipement_id'])
                except EquipementConstitutif.DoesNotExist:
                    pass
            else:
                analyse.equipement = None

        if 'point_eau_id' in data:
            if data['point_eau_id']:
                try:
                    analyse.point_eau = PointEau.objects.get(id=data['point_eau_id'])
                except PointEau.DoesNotExist:
                    pass
            else:
                analyse.point_eau = None

        analyse.save()

        return JsonResponse({
            'success': True,
            'message': 'Analyse d\'eau mise à jour avec succès'
        })

    except AnalyseEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Analyse d\'eau introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_analyse_eau_delete(request, analyse_id):
    """API pour supprimer une analyse d'eau"""
    try:
        analyse = AnalyseEau.objects.get(id=analyse_id)
        analyse.delete()

        return JsonResponse({
            'success': True,
            'message': 'Analyse d\'eau supprimée avec succès'
        })

    except AnalyseEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Analyse d\'eau introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_analyses_eau_delete_all(request):
    """API pour supprimer TOUTES les analyses d'eau (pour réimport propre)"""
    try:
        # Compter avant suppression
        count = AnalyseEau.objects.count()

        # Supprimer toutes les analyses
        AnalyseEau.objects.all().delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} analyse(s) supprimée(s) avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_analyse_eau_detail(request, analyse_id):
    """API pour récupérer les détails d'une analyse"""
    try:
        analyse = AnalyseEau.objects.select_related(
            'equipement',
            'point_eau',
            'created_by'
        ).get(id=analyse_id)

        # Convertir dates UTC → Madagascar AVANT formatage (TIMEZONE_GUIDE.md)
        date_prelevement_mg = analyse.date_prelevement.astimezone(tz_madagascar) if analyse.date_prelevement.tzinfo else tz_madagascar.localize(analyse.date_prelevement)
        date_analyse_mg = analyse.date_analyse.astimezone(tz_madagascar) if analyse.date_analyse.tzinfo else tz_madagascar.localize(analyse.date_analyse)
        date_resultat_mg = analyse.date_resultat.astimezone(tz_madagascar) if analyse.date_resultat.tzinfo else tz_madagascar.localize(analyse.date_resultat)

        # Récupérer commune_id et ouvrage_id pour les cascades
        commune_id = None
        ouvrage_id = None

        if analyse.equipement:
            ouvrage_id = str(analyse.equipement.ouvrage_id) if analyse.equipement.ouvrage else None
            # Récupérer commune via ouvrage → point d'eau → parcelle → village → fokontany → commune
            if analyse.equipement.ouvrage:
                point_eau = analyse.equipement.ouvrage.pointeau_set.select_related(
                    'parcelle__village__fokontany__commune'
                ).first()
                if point_eau and point_eau.parcelle and point_eau.parcelle.village:
                    if point_eau.parcelle.village.fokontany:
                        commune_id = str(point_eau.parcelle.village.fokontany.commune_id) if point_eau.parcelle.village.fokontany.commune else None

        elif analyse.point_eau:
            ouvrage_id = str(analyse.point_eau.ouvrage_id) if analyse.point_eau.ouvrage else None
            # Récupérer commune via point d'eau → parcelle → village → fokontany → commune
            if analyse.point_eau.parcelle and analyse.point_eau.parcelle.village:
                if analyse.point_eau.parcelle.village.fokontany:
                    commune_id = str(analyse.point_eau.parcelle.village.fokontany.commune_id) if analyse.point_eau.parcelle.village.fokontany.commune else None

        return JsonResponse({
            'success': True,
            'analyse': {
                'id': str(analyse.id),
                'type_prelevement': analyse.type_prelevement,
                'description_lieu': analyse.description_lieu,
                'date_prelevement': date_prelevement_mg.strftime('%d/%m/%Y %H:%M'),
                'date_analyse': date_analyse_mg.strftime('%d/%m/%Y %H:%M'),
                'date_resultat': date_resultat_mg.strftime('%d/%m/%Y %H:%M'),
                'volume_analyse': analyse.volume_analyse,
                'nombre_coliformes': analyse.nombre_coliformes,
                'tnc': analyse.tnc,
                'ph': float(analyse.ph) if analyse.ph else None,
                'observation': analyse.observation,
                'equipement_constitutif_id': str(analyse.equipement.id) if analyse.equipement else None,
                'point_eau_id': str(analyse.point_eau.id) if analyse.point_eau else None,
                'commune_id': commune_id,
                'ouvrage_id': ouvrage_id,
            }
        })

    except AnalyseEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Analyse d\'eau introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def analyses_eau_dashboard(request):
    """Tableau de bord des résultats d'analyse"""
    # Récupérer les communes pour le filtre
    communes = Commune.objects.all().order_by('nom_commune')

    # Récupérer les années disponibles
    annees = AnalyseEau.objects.dates('date_prelevement', 'year', order='DESC')
    annees_list = [d.year for d in annees]

    if not annees_list:
        annees_list = [datetime.now().year]

    context = {
        'communes': communes,
        'annees': annees_list,
        'annee_actuelle': datetime.now().year
    }

    return render(request, 'inspections/analyses_eau_dashboard.html', context)


@require_http_methods(["GET"])
def api_analyses_eau_dashboard(request):
    """API pour le tableau de bord avec filtres"""
    try:
        # Récupérer tous les analyses
        analyses = AnalyseEau.objects.all().select_related(
            'equipement',
            'equipement__ouvrage',
            'point_eau',
            'point_eau__parcelle__village__fokontany__commune'
        )

        # Filtres
        annee = request.GET.get('annee')
        commune_id = request.GET.get('commune_id')
        resultat = request.GET.get('resultat')  # 'positif', 'zero'

        if annee:
            analyses = analyses.filter(date_analyse__year=int(annee))

        # Filtre par résultat
        if resultat == 'positif':
            analyses = analyses.filter(
                Q(tnc=True) | Q(nombre_coliformes__gt=0)
            )
        elif resultat == 'zero':
            analyses = analyses.filter(tnc=False, nombre_coliformes=0)

        # Convertir en liste
        data = []
        for analyse in analyses:
            # Filtrer par commune si spécifié
            commune_nom = analyse.commune_nom
            if commune_id and commune_id != 'all':
                try:
                    commune_obj = Commune.objects.get(id=commune_id)
                    if commune_nom != commune_obj.nom_commune:
                        continue
                except Commune.DoesNotExist:
                    continue

            # Formater nombre pour 100mL
            if analyse.tnc:
                nombre_100ml_display = "TNC"
            elif analyse.nombre_pour_100ml is not None:
                nombre_100ml_display = str(analyse.nombre_pour_100ml)
            else:
                nombre_100ml_display = "N/A"

            data.append({
                'id': str(analyse.id),
                'commune': commune_nom,
                'village': analyse.village_nom,
                'lieu': analyse.lieu_affichage,
                'date_analyse': analyse.date_analyse.strftime('%d/%m/%Y'),
                'nombre_pour_100ml': nombre_100ml_display,
                'observation': analyse.observation,
                'est_positif': analyse.est_positif,
            })

        # Trier par commune, village, date
        data.sort(key=lambda x: (x['commune'], x['village'], x['date_analyse']))

        return JsonResponse({
            'success': True,
            'total': len(data),
            'data': data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
@require_http_methods(["GET"])
def api_analyses_eau_stats_globales(request):
    """API pour les statistiques globales du dashboard"""
    try:
        from apps.organization.models import Ouvrage
        from apps.billing.models import ModaliteGestion

        # Filtres optionnels
        annee = request.GET.get('annee')
        commune_id = request.GET.get('commune_id')
        organisation_id = request.GET.get('organisation_id')
        gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)

        # === 1. OUVRAGES VIA MODALITÉS ACTIVES ===
        modalites_actives = ModaliteGestion.objects.filter(date_fin__isnull=True)

        if organisation_id and organisation_id != 'all':
            if gestionnaire_ids is not None and organisation_id not in {str(_id) for _id in gestionnaire_ids}:
                modalites_actives = modalites_actives.none()
            else:
                modalites_actives = modalites_actives.filter(gestionnaire_id=organisation_id)
        elif gestionnaire_ids is not None:
            if gestionnaire_ids:
                modalites_actives = modalites_actives.filter(gestionnaire_id__in=gestionnaire_ids)
            else:
                modalites_actives = modalites_actives.none()

        ouvrages_ids = modalites_actives.values_list('ouvrage_id', flat=True).distinct()
        ouvrages = Ouvrage.objects.filter(id__in=ouvrages_ids)

        # Filtrer par commune si spécifié
        if commune_id and commune_id != 'all':
            # Via points d'eau
            points_eau_commune = PointEau.objects.filter(
                parcelle__village__fokontany__commune_id=commune_id
            ).values_list('ouvrage_id', flat=True).distinct()
            ouvrages = ouvrages.filter(id__in=points_eau_commune)

        total_ouvrages = ouvrages.count()

        # === 2. POINTS D'EAU DES OUVRAGES ===
        points_eau = PointEau.objects.filter(ouvrage_id__in=ouvrages_ids)

        if commune_id and commune_id != 'all':
            points_eau = points_eau.filter(
                parcelle__village__fokontany__commune_id=commune_id
            )

        total_points_eau = points_eau.count()
        points_eau_ids = list(points_eau.values_list('id', flat=True))

        # === 3. ÉQUIPEMENTS DES OUVRAGES ===
        equipements = EquipementConstitutif.objects.filter(ouvrage_id__in=ouvrages_ids)
        total_equipements = equipements.count()
        equipements_ids = list(equipements.values_list('id', flat=True))

        # === 4. ANALYSES ===
        analyses = AnalyseEau.objects.all()

        if annee:
            analyses = analyses.filter(date_analyse__year=int(annee))

        # Séparer par type de prélèvement
        analyses_points_eau = analyses.filter(
            type_prelevement='point_eau',
            point_eau_id__in=points_eau_ids
        )

        analyses_equipements = analyses.filter(
            type_prelevement='equipement',
            equipement_id__in=equipements_ids
        )

        analyses_traditionnels = analyses.filter(type_prelevement='point_eau_traditionnel')
        analyses_bouteilles = analyses.filter(type_prelevement='bouteille')

        # === 5. POINTS D'EAU ANALYSÉS ===
        points_eau_analyses_ids = analyses_points_eau.values_list('point_eau_id', flat=True).distinct()
        nb_points_eau_analyses = len(set(points_eau_analyses_ids))

        # Contamination
        points_eau_contamines_ids = analyses_points_eau.filter(
            Q(tnc=True) | Q(nombre_coliformes__gt=0)
        ).values_list('point_eau_id', flat=True).distinct()
        nb_points_eau_contamines = len(set(points_eau_contamines_ids))

        # Pourcentages
        pct_points_eau_analyses = int((nb_points_eau_analyses / total_points_eau * 100) if total_points_eau > 0 else 0)
        pct_points_eau_contamines = int((nb_points_eau_contamines / nb_points_eau_analyses * 100) if nb_points_eau_analyses > 0 else 0)

        # === 6. ÉQUIPEMENTS ANALYSÉS ===
        equipements_analyses_ids = analyses_equipements.values_list('equipement_id', flat=True).distinct()
        nb_equipements_analyses = len(set(equipements_analyses_ids))

        # Contamination
        equipements_contamines_ids = analyses_equipements.filter(
            Q(tnc=True) | Q(nombre_coliformes__gt=0)
        ).values_list('equipement_id', flat=True).distinct()
        nb_equipements_contamines = len(set(equipements_contamines_ids))

        # Pourcentages
        pct_equipements_analyses = int((nb_equipements_analyses / total_equipements * 100) if total_equipements > 0 else 0)
        pct_equipements_contamines = int((nb_equipements_contamines / nb_equipements_analyses * 100) if nb_equipements_analyses > 0 else 0)

        # === 7. ANALYSES PAR OUVRAGE ===
        analyses_par_ouvrage = []
        for ouvrage in ouvrages[:10]:  # Top 10
            nb_analyses = analyses_points_eau.filter(point_eau__ouvrage=ouvrage).count()
            nb_analyses += analyses_equipements.filter(equipement__ouvrage=ouvrage).count()

            if nb_analyses > 0:
                analyses_par_ouvrage.append({
                    'ouvrage_nom': ouvrage.nom_ouvrage,
                    'nb_analyses': nb_analyses
                })

        # Trier par nombre d'analyses
        analyses_par_ouvrage.sort(key=lambda x: x['nb_analyses'], reverse=True)

        # === 8. STATISTIQUES PACKS (TÉMOINS) ===
        nb_temoins_positifs = analyses_traditionnels.filter(
            Q(tnc=True) | Q(nombre_coliformes__gt=0)
        ).count()
        nb_bouteilles_contaminees = analyses_bouteilles.filter(
            Q(tnc=True) | Q(nombre_coliformes__gt=0)
        ).count()

        return JsonResponse({
            'success': True,
            'stats': {
                # Ouvrages
                'total_ouvrages': total_ouvrages,
                'total_points_eau': total_points_eau,
                'total_equipements': total_equipements,

                # Points d'eau
                'nb_points_eau_analyses': nb_points_eau_analyses,
                'pct_points_eau_analyses': pct_points_eau_analyses,
                'nb_points_eau_contamines': nb_points_eau_contamines,
                'pct_points_eau_contamines': pct_points_eau_contamines,
                'nb_points_eau_conformes': nb_points_eau_analyses - nb_points_eau_contamines,

                # Équipements
                'nb_equipements_analyses': nb_equipements_analyses,
                'pct_equipements_analyses': pct_equipements_analyses,
                'nb_equipements_contamines': nb_equipements_contamines,
                'pct_equipements_contamines': pct_equipements_contamines,
                'nb_equipements_conformes': nb_equipements_analyses - nb_equipements_contamines,

                # Analyses totales
                'total_analyses': analyses.count(),
                'analyses_points_eau': analyses_points_eau.count(),
                'analyses_equipements': analyses_equipements.count(),
                'analyses_traditionnels': analyses_traditionnels.count(),
                'analyses_bouteilles': analyses_bouteilles.count(),

                # Témoins
                'nb_temoins_positifs': nb_temoins_positifs,
                'nb_bouteilles_contaminees': nb_bouteilles_contaminees,

                # Top analyses par ouvrage
                'analyses_par_ouvrage': analyses_par_ouvrage[:10]
            }
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@require_http_methods(["GET"])
def api_ouvrages_par_commune(request):
    """API pour récupérer les ouvrages filtrés par commune"""
    try:
        from apps.organization.models import Ouvrage
        from apps.billing.models import PointEau

        commune_id = request.GET.get('commune_id')

        if commune_id:
            # Filtrer les ouvrages via les points d'eau de la commune
            points_eau_commune = PointEau.objects.filter(
                parcelle__village__fokontany__commune_id=commune_id
            ).values_list('ouvrage_id', flat=True).distinct()

            ouvrages = Ouvrage.objects.filter(id__in=points_eau_commune)
        else:
            # Tous les ouvrages
            ouvrages = Ouvrage.objects.all()

        data = []
        for ouvrage in ouvrages.order_by('nom_ouvrage'):
            data.append({
                'id': str(ouvrage.id),
                'nom_ouvrage': ouvrage.nom_ouvrage
            })

        return JsonResponse({
            'success': True,
            'ouvrages': data
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@require_http_methods(["GET"])
def api_equipements_par_ouvrage(request):
    """API pour récupérer les équipements d'un ouvrage"""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')

        if not ouvrage_id:
            return JsonResponse({
                'success': False,
                'error': 'ouvrage_id requis'
            }, status=400)

        equipements = EquipementConstitutif.objects.filter(
            ouvrage_id=ouvrage_id
        ).select_related('type_equipement')

        data = []
        for equip in equipements.order_by('type_equipement__nom_type'):
            data.append({
                'id': str(equip.id),
                'nom': f"{equip.type_equipement.nom_type if equip.type_equipement else 'Équipement'} - {equip.ouvrage.nom_ouvrage}",
                'type': equip.type_equipement.nom_type if equip.type_equipement else ''
            })

        return JsonResponse({
            'success': True,
            'equipements': data
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@require_http_methods(["GET"])
def api_points_eau_par_ouvrage(request):
    """API pour récupérer les points d'eau d'un ouvrage"""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')

        if not ouvrage_id:
            return JsonResponse({
                'success': False,
                'error': 'ouvrage_id requis'
            }, status=400)

        points_eau = PointEau.objects.filter(
            ouvrage_id=ouvrage_id
        ).select_related('type_point_eau')

        data = []
        for pe in points_eau.order_by('type_point_eau__nom_type'):
            type_nom = pe.type_point_eau.nom_type if pe.type_point_eau else "Point d'eau"
            data.append({
                'id': str(pe.id),
                'nom': f"{type_nom} - {pe.ouvrage.nom_ouvrage}",
                'type': pe.type_point_eau.nom_type if pe.type_point_eau else ''
            })

        return JsonResponse({
            'success': True,
            'points_eau': data
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


# Force reload
# Reload mer. 24 déc. 2025 06:03:54
