"""
Vues pour la gestion des fiches de poste
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
import json

from apps.employees.models_evaluation import FichePoste


def fiches_poste_list(request):
    """Page de liste et gestion des fiches de poste"""
    return render(request, 'employees/fiches_poste_list.html', {})


@csrf_exempt
@require_http_methods(["GET"])
def api_fiches_poste_list(request):
    """API pour récupérer toutes les fiches de poste"""
    try:
        fiches = FichePoste.objects.all().order_by('ordre', 'tache')

        data = []
        for fiche in fiches:
            data.append({
                'id': str(fiche.id),
                'tache': fiche.tache,
                'description': fiche.description,
                'outils': fiche.outils,
                'ordre': fiche.ordre,
                'preuve_obligatoire': fiche.preuve_obligatoire,
                'preuve_type': fiche.preuve_type,
                'preuve_type': fiche.preuve_type,
            })

        return JsonResponse({
            'success': True,
            'fiches': data,
            'count': len(data)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)




@csrf_exempt
@require_http_methods(["GET"])
def api_fiches_poste_by_poste(request, poste_id):
    """API pour récupérer toutes les fiches d'un poste"""
    try:
        fiches = FichePoste.objects.filter(activites_postes__poste_id=poste_id).distinct().order_by('ordre', 'tache')

        data = []
        for fiche in fiches:
            data.append({
                'id': str(fiche.id),
                'tache': fiche.tache,
                'description': fiche.description,
                'outils': fiche.outils,
                'ordre': fiche.ordre,
                'preuve_obligatoire': fiche.preuve_obligatoire,
                'preuve_type': fiche.preuve_type,
                'preuve_type': fiche.preuve_type,
            })

        return JsonResponse({
            'success': True,
            'fiches': data,
            'count': len(data)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_fiche_poste_create(request):
    """API pour créer une fiche de poste"""
    try:
        data = json.loads(request.body)

        tache = data.get('tache', '').strip()
        description = data.get('description', '').strip()
        outils = data.get('outils', '').strip()
        ordre = data.get('ordre', 0)

        # Validation
        if not tache:
            return JsonResponse({
                'success': False,
                'error': 'Le nom de la tâche est obligatoire'
            }, status=400)

        if not description:
            return JsonResponse({
                'success': False,
                'error': 'La description est obligatoire'
            }, status=400)

        # Vérifier que le poste existe

        # Créer la fiche
        fiche = FichePoste.objects.create(
            tache=tache,
            description=description,
            outils=outils,
            ordre=ordre,
            preuve_obligatoire=bool(data.get('preuve_obligatoire', False)),
            preuve_type=data.get('preuve_type') or 'piece_jointe'
        )

        return JsonResponse({
            'success': True,
            'message': 'Fiche de poste créée avec succès',
            'fiche': {
                'id': str(fiche.id),
                'tache': fiche.tache,
                'description': fiche.description,
                'outils': fiche.outils,
                'ordre': fiche.ordre,
                'preuve_obligatoire': fiche.preuve_obligatoire,
                'preuve_type': fiche.preuve_type,
                'preuve_type': fiche.preuve_type,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_fiche_poste_update(request, fiche_id):
    """API pour modifier une fiche de poste"""
    try:
        data = json.loads(request.body)
        fiche = get_object_or_404(FichePoste, id=fiche_id)

        tache = data.get('tache', '').strip()
        description = data.get('description', '').strip()
        outils = data.get('outils', '').strip()
        ordre = data.get('ordre', fiche.ordre)
        preuve_obligatoire = data.get('preuve_obligatoire', fiche.preuve_obligatoire)
        preuve_type = data.get('preuve_type', fiche.preuve_type)

        # Validation
        if not tache:
            return JsonResponse({
                'success': False,
                'error': 'Le nom de la tâche est obligatoire'
            }, status=400)

        if not description:
            return JsonResponse({
                'success': False,
                'error': 'La description est obligatoire'
            }, status=400)

        # Mise à jour
        fiche.tache = tache
        fiche.description = description
        fiche.outils = outils
        fiche.ordre = ordre
        fiche.preuve_obligatoire = bool(preuve_obligatoire)
        fiche.preuve_type = preuve_type or fiche.preuve_type
        fiche.save()

        return JsonResponse({
            'success': True,
            'message': 'Fiche de poste modifiée avec succès',
            'fiche': {
                'id': str(fiche.id),
                'tache': fiche.tache,
                'description': fiche.description,
                'outils': fiche.outils,
                'ordre': fiche.ordre,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_fiche_poste_delete(request, fiche_id):
    """API pour supprimer une fiche de poste"""
    try:
        fiche = get_object_or_404(FichePoste, id=fiche_id)

        # Vérifier s'il y a des évaluations liées
        nb_evaluations = fiche.evaluations_details.count()

        # Supprimer la fiche (les évaluations seront préservées avec fiche_poste=NULL)
        fiche.delete()

        message = 'Fiche de poste supprimée avec succès'
        if nb_evaluations > 0:
            message += f' ({nb_evaluations} évaluation(s) conservée(s))'

        return JsonResponse({
            'success': True,
            'message': message
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
