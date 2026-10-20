"""
API pour annuler un Repos ou Jour férié et créer une Récupération automatique
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json

from .models import Planning, Activite
from apps.employees.models_recuperations import Recuperation


@csrf_exempt
@require_http_methods(["POST"])
def api_annuler_repos_ferie(request, planning_id):
    """
    Annuler un Planning de type Repos ou Jour férié

    Règles:
    - Supprimer le Planning
    - SI Dimanche OU Jour férié → Créer une Récupération automatique
    - SI Samedi → PAS de récupération (non récupérable)

    Args:
        planning_id: UUID du Planning à annuler

    Returns:
        JSON: {
            'success': bool,
            'message': str,
            'recuperation_creee': bool,
            'recuperation_id': str (si créée)
        }
    """
    try:
        # Récupérer le planning
        try:
            planning = Planning.objects.select_related('employe', 'activite').get(id=planning_id)
        except Planning.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Planning non trouvé'
            }, status=404)

        # Vérifier que c'est bien un Repos ou Jour férié
        activite_nom = planning.activite.nom if planning.activite else ''
        if activite_nom not in ['Repos', 'Jour férié']:
            return JsonResponse({
                'success': False,
                'error': f'Ce planning n\'est pas un Repos/Jour férié (activité: {activite_nom})'
            }, status=400)

        # Récupérer les infos avant suppression
        employe = planning.employe
        date_planning = planning.date.date() if hasattr(planning.date, 'date') else planning.date
        jour_semaine = date_planning.weekday()  # 0=Lundi, 5=Samedi, 6=Dimanche

        # Déterminer si on doit créer une récupération
        creer_recuperation = False
        motif_acquisition = None

        if activite_nom == 'Jour férié':
            # Jour férié → Toujours récupérable
            creer_recuperation = True
            motif_acquisition = 'jour_ferie'

        elif activite_nom == 'Repos':
            if jour_semaine == 6:  # Dimanche
                creer_recuperation = True
                motif_acquisition = 'dimanche'
            elif jour_semaine == 5:  # Samedi
                creer_recuperation = False  # Samedi NON récupérable
            else:
                # Autre jour de la semaine (cas rare)
                creer_recuperation = False

        # Supprimer le planning
        planning.delete()

        # Créer la récupération si nécessaire
        recuperation_id = None
        if creer_recuperation:
            # Vérifier qu'une récupération n'existe pas déjà
            existing_recup = Recuperation.objects.filter(
                employe=employe,
                date_travail_exceptionnel=date_planning
            ).first()

            if not existing_recup:
                recuperation = Recuperation.objects.create(
                    employe=employe,
                    date_travail_exceptionnel=date_planning,
                    motif_acquisition=motif_acquisition,
                    nb_jours_acquis=1.0,
                    statut='acquise',
                    planning_travail=None,  # Pas de lien vers planning (supprimé)
                )
                recuperation_id = str(recuperation.id)

        # Message de succès
        if creer_recuperation and recuperation_id:
            message = f"Planning annulé. Une récupération a été créée automatiquement ({motif_acquisition.replace('_', ' ')})"
        elif creer_recuperation and not recuperation_id:
            message = "Planning annulé. Une récupération existait déjà pour cette date"
        else:
            if jour_semaine == 5:
                message = "Planning annulé (Samedi non récupérable)"
            else:
                message = "Planning annulé"

        return JsonResponse({
            'success': True,
            'message': message,
            'recuperation_creee': bool(recuperation_id),
            'recuperation_id': recuperation_id
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
