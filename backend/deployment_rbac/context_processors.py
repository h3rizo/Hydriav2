"""
Context processors pour les employés
Fournit des données globales sur l'employé connecté dans tous les templates
"""
from django.utils import timezone
from datetime import timedelta
from .models import PositionGPSEmploye
from .permissions import (
    has_admin_compta_access,
    has_admin_access,
    has_compta_access,
    is_directeur_poste,
)


def employee_tracking_info(request):
    """
    Ajoute les informations de tracking GPS de l'employé connecté
    - Dernière position GPS
    - Village le plus proche
    - Cumul temps de connexion du mois
    """
    context = {
        'employee_tracking': {
            'has_position': False,
            'latitude': None,
            'longitude': None,
            'village_proche': None,
            'distance_village': None,
            'temps_connexion_mois': 0,
            'last_update': None,
        }
    }

    # Vérifier si l'utilisateur est connecté et a un employé associé
    if not request.user.is_authenticated:
        return context

    try:
        employe = request.user.employe
    except AttributeError:
        return context

    # Récupérer la dernière position GPS de l'employé
    derniere_position = PositionGPSEmploye.objects.filter(
        employe=employe
    ).select_related('village_proche').order_by('-date_enregistrement').first()

    if derniere_position:
        context['employee_tracking'].update({
            'has_position': True,
            'latitude': float(derniere_position.latitude) if derniere_position.latitude else None,
            'longitude': float(derniere_position.longitude) if derniere_position.longitude else None,
            'village_proche': derniere_position.village_proche.nom_village if derniere_position.village_proche else None,
            'distance_village': float(derniere_position.distance_village) if derniere_position.distance_village else None,
            'last_update': derniere_position.date_enregistrement,
        })

    # Calculer le cumul du temps de connexion du mois en cours
    now = timezone.now()
    debut_mois = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Récupérer toutes les positions du mois
    positions_mois = PositionGPSEmploye.objects.filter(
        employe=employe,
        date_enregistrement__gte=debut_mois
    ).order_by('date_enregistrement')

    # Calculer la durée totale
    duree_totale = timedelta(0)
    positions_list = list(positions_mois)

    for i, pos in enumerate(positions_list):
        # Trouver la position suivante
        if i + 1 < len(positions_list):
            next_pos = positions_list[i + 1]
            diff = next_pos.date_enregistrement - pos.date_enregistrement

            # Limiter à 8h max entre deux positions (sinon c'est une nouvelle session)
            if diff <= timedelta(hours=8):
                duree_totale += diff

    # Convertir en heures
    heures_totales = duree_totale.total_seconds() / 3600

    context['employee_tracking']['temps_connexion_mois'] = round(heures_totales, 1)

    return context


def permissions(request):
    """
    Ajoute les fonctions de vérification des permissions dans le contexte des templates.
    Permet d'utiliser has_admin_compta_access, has_admin_access, has_compta_access dans les templates.
    """
    return {
        'has_admin_compta_access': has_admin_compta_access(request.user),
        'has_admin_access': has_admin_access(request.user),
        'has_compta_access': has_compta_access(request.user),
        'is_directeur_poste': is_directeur_poste(request.user),
    }
