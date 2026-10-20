"""
Vues pour la gestion des natures de déclaration de communication.
Interface CRUD complète pour configurer les natures de déclaration.
"""

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

from .models import ConfigDeclarationCommunication


def natures_declaration_list(request):
    """Page de gestion des natures de déclaration"""
    return render(request, 'accounting/natures_declaration_list.html')


@require_http_methods(["GET"])
def api_natures_declaration_list(request):
    """API pour lister les natures de déclaration"""
    try:
        # Récupérer toutes les natures, triées par ordre
        natures = ConfigDeclarationCommunication.objects.all().order_by('ordre', 'nom')

        data = []
        for nature in natures:
            data.append({
                'id': str(nature.id),
                'nom': nature.nom,
                'ordre': nature.ordre,
                'actif': nature.actif,
                'created_at': nature.created_at.strftime('%d/%m/%Y %H:%M'),
                'updated_at': nature.updated_at.strftime('%d/%m/%Y %H:%M'),
            })

        return JsonResponse({
            'success': True,
            'data': data,
            'total': len(data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_nature_declaration_create(request):
    """API pour créer une nature de déclaration"""
    try:
        data = json.loads(request.body)

        nom = data.get('nom', '').strip()
        ordre = data.get('ordre', 0)
        actif = data.get('actif', True)

        if not nom:
            return JsonResponse({
                'success': False,
                'error': 'Le nom est obligatoire'
            }, status=400)

        # Vérifier si le nom existe déjà
        if ConfigDeclarationCommunication.objects.filter(nom=nom).exists():
            return JsonResponse({
                'success': False,
                'error': 'Une nature avec ce nom existe déjà'
            }, status=400)

        # Créer la nature
        nature = ConfigDeclarationCommunication.objects.create(
            nom=nom,
            ordre=ordre,
            actif=actif
        )

        return JsonResponse({
            'success': True,
            'message': 'Nature de déclaration créée avec succès',
            'data': {
                'id': str(nature.id),
                'nom': nature.nom,
                'ordre': nature.ordre,
                'actif': nature.actif
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_nature_declaration_update(request, nature_id):
    """API pour modifier une nature de déclaration"""
    try:
        data = json.loads(request.body)

        # Récupérer la nature
        try:
            nature = ConfigDeclarationCommunication.objects.get(id=nature_id)
        except ConfigDeclarationCommunication.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Nature de déclaration non trouvée'
            }, status=404)

        nom = data.get('nom', '').strip()
        ordre = data.get('ordre', nature.ordre)
        actif = data.get('actif', nature.actif)

        if not nom:
            return JsonResponse({
                'success': False,
                'error': 'Le nom est obligatoire'
            }, status=400)

        # Vérifier si le nom existe déjà (sauf pour la nature actuelle)
        if ConfigDeclarationCommunication.objects.filter(nom=nom).exclude(id=nature_id).exists():
            return JsonResponse({
                'success': False,
                'error': 'Une nature avec ce nom existe déjà'
            }, status=400)

        # Mettre à jour
        nature.nom = nom
        nature.ordre = ordre
        nature.actif = actif
        nature.save()

        return JsonResponse({
            'success': True,
            'message': 'Nature de déclaration mise à jour avec succès',
            'data': {
                'id': str(nature.id),
                'nom': nature.nom,
                'ordre': nature.ordre,
                'actif': nature.actif
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_nature_declaration_delete(request, nature_id):
    """API pour supprimer une nature de déclaration"""
    try:
        # Récupérer la nature
        try:
            nature = ConfigDeclarationCommunication.objects.get(id=nature_id)
        except ConfigDeclarationCommunication.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Nature de déclaration non trouvée'
            }, status=404)

        # Vérifier si la nature est utilisée par des comptes
        nb_comptes = nature.comptes.count()
        if nb_comptes > 0:
            return JsonResponse({
                'success': False,
                'error': f'Cette nature est utilisée par {nb_comptes} compte(s). Impossible de la supprimer.'
            }, status=400)

        nom = nature.nom
        nature.delete()

        return JsonResponse({
            'success': True,
            'message': f'Nature "{nom}" supprimée avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
