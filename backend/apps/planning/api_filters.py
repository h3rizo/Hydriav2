"""
API endpoints pour les filtres en cascade du formulaire de planning
"""
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from apps.planning.models import (
    Activite, ActivitePoste, Designation, DesignationTypeActivite,
    DesignationCompte, Deplacement
)
from apps.infrastructure.models import EquipementConstitutif
from apps.billing.models import PointEau
from apps.geography.models import Village
from apps.employees.models import Employe


@require_GET
def get_activites_by_poste(request):
    """Récupère les activités filtrées par type d'activité et poste de l'employé"""
    type_activite_id = request.GET.get('type_activite_id')
    employe_id = request.GET.get('employe_id')

    if not type_activite_id or not employe_id:
        return JsonResponse({'error': 'Paramètres manquants'}, status=400)

    try:
        employe = Employe.objects.get(id=employe_id)
        poste = employe.poste

        if not poste:
            # Si pas de poste, retourner toutes les activités du type
            activites = Activite.objects.filter(
                type_activite_id=type_activite_id,
                is_active=True
            ).values('id', 'nom')
        else:
            # Filtrer par les activités autorisées pour ce poste
            activite_ids = ActivitePoste.objects.filter(
                activite__type_activite_id=type_activite_id,
                poste=poste,
                is_active=True
            ).values_list('activite_id', flat=True)

            activites = Activite.objects.filter(
                id__in=activite_ids,
                is_active=True
            ).values('id', 'nom')

        return JsonResponse({
            'success': True,
            'activites': list(activites)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def get_equipements_by_ouvrage(request):
    """Récupère les équipements constitutifs d'un ouvrage"""
    ouvrage_id = request.GET.get('ouvrage_id')

    if not ouvrage_id:
        return JsonResponse({'error': 'ouvrage_id manquant'}, status=400)

    try:
        equipements = EquipementConstitutif.objects.filter(
            ouvrage_id=ouvrage_id
        ).values('id', 'nom')

        return JsonResponse({
            'success': True,
            'equipements': list(equipements)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def get_points_eau_by_ouvrage(request):
    """Récupère les points d'eau d'un ouvrage"""
    ouvrage_id = request.GET.get('ouvrage_id')

    if not ouvrage_id:
        return JsonResponse({'error': 'ouvrage_id manquant'}, status=400)

    try:
        points_eau = PointEau.objects.filter(
            ouvrage_id=ouvrage_id
        ).values('id', 'idxlsx', 'tarif_forfaitaire')

        return JsonResponse({
            'success': True,
            'points_eau': list(points_eau)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def get_designations_by_type_activite(request):
    """Récupère les désignations filtrées par type d'activité"""
    type_activite_id = request.GET.get('type_activite_id')

    if not type_activite_id:
        return JsonResponse({'error': 'type_activite_id manquant'}, status=400)

    try:
        # Récupérer les IDs des désignations liées à ce type d'activité
        designation_ids = DesignationTypeActivite.objects.filter(
            type_activite_id=type_activite_id,
            is_active=True
        ).values_list('designation_id', flat=True)

        designations = Designation.objects.filter(
            id__in=designation_ids,
            actif=True
        ).values(
            'id', 'nom', 'prix_unitaire', 'type_avance_caissiere'
        )

        return JsonResponse({
            'success': True,
            'designations': list(designations)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def get_compte_by_designation(request):
    """Récupère le compte par défaut d'une désignation"""
    designation_id = request.GET.get('designation_id')

    if not designation_id:
        return JsonResponse({'error': 'designation_id manquant'}, status=400)

    try:
        # Récupérer le premier compte actif lié à cette désignation
        designation_compte = DesignationCompte.objects.filter(
            designation_id=designation_id,
            is_active=True
        ).select_related('compte').first()

        if designation_compte:
            return JsonResponse({
                'success': True,
                'compte': {
                    'id': str(designation_compte.compte.id),
                    'nom': designation_compte.compte.nom_compte
                }
            })
        else:
            return JsonResponse({
                'success': True,
                'compte': None
            })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def get_designation_details(request):
    """Récupère les détails complets d'une désignation"""
    designation_id = request.GET.get('designation_id')

    if not designation_id:
        return JsonResponse({'error': 'designation_id manquant'}, status=400)

    try:
        designation = Designation.objects.get(id=designation_id)

        # Récupérer le compte par défaut
        designation_compte = DesignationCompte.objects.filter(
            designation_id=designation_id,
            is_active=True
        ).select_related('compte').first()

        compte_data = None
        if designation_compte:
            compte_data = {
                'id': str(designation_compte.compte.id),
                'nom': designation_compte.compte.nom_compte
            }

        return JsonResponse({
            'success': True,
            'designation': {
                'id': str(designation.id),
                'nom': designation.nom,
                'prix_unitaire': float(designation.prix_unitaire) if designation.prix_unitaire else None,
                'type_avance_caissiere': designation.type_avance_caissiere,
                'compte': compte_data
            }
        })
    except Designation.DoesNotExist:
        return JsonResponse({'error': 'Désignation non trouvée'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def get_villages_by_point_a(request):
    """Récupère les villages de destination possibles depuis un point A"""
    point_a_id = request.GET.get('point_a_id')

    if not point_a_id:
        return JsonResponse({'error': 'point_a_id manquant'}, status=400)

    try:
        # Récupérer tous les villages accessibles depuis point_a via la table deplacements
        village_ids = Deplacement.objects.filter(
            point_a_id=point_a_id
        ).values_list('point_b_id', flat=True).distinct()

        villages = Village.objects.filter(
            id__in=village_ids
        ).values('id', 'nom_village')

        return JsonResponse({
            'success': True,
            'villages': list(villages)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def get_prix_deplacement(request):
    """Récupère le prix unitaire d'un déplacement"""
    point_a_id = request.GET.get('point_a_id')
    point_b_id = request.GET.get('point_b_id')
    moyen_transport = request.GET.get('moyen_transport', 'taxi-brousse')

    if not point_a_id or not point_b_id:
        return JsonResponse({'error': 'Paramètres manquants'}, status=400)

    try:
        # Récupérer le déplacement le plus récent
        deplacement = Deplacement.objects.filter(
            point_a_id=point_a_id,
            point_b_id=point_b_id,
            moyen_transport=moyen_transport
        ).order_by('-date_prix').first()

        if deplacement:
            return JsonResponse({
                'success': True,
                'prix_unitaire': float(deplacement.prix_unitaire)
            })
        else:
            return JsonResponse({
                'success': True,
                'prix_unitaire': None
            })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def get_tarif_forfaitaire_point_eau(request):
    """Récupère le tarif forfaitaire d'un point d'eau"""
    point_eau_id = request.GET.get('point_eau_id')

    if not point_eau_id:
        return JsonResponse({'error': 'point_eau_id manquant'}, status=400)

    try:
        point_eau = PointEau.objects.get(id=point_eau_id)

        return JsonResponse({
            'success': True,
            'tarif_forfaitaire': float(point_eau.tarif_forfaitaire) if point_eau.tarif_forfaitaire else None
        })
    except PointEau.DoesNotExist:
        return JsonResponse({'error': 'Point d\'eau non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
