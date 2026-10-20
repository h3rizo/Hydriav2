"""
Vues pour la gestion des photos de désignations via Unsplash
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
try:
    import requests
except ImportError:
    requests = None
from apps.planning.models import Designation


# Clé API Unsplash (gratuite - 50 requêtes/heure)
# Vous pouvez créer votre propre clé sur https://unsplash.com/developers
UNSPLASH_ACCESS_KEY = 'E0TM2VUn7FcWYhtG31IyPUhyrsszVyifbp_vjJOcF8s'  # ⬅️ Remplacez par votre Access Key


@login_required
@require_http_methods(["GET"])
def api_search_photos(request, designation_id):
    """
    Rechercher des photos sur Unsplash pour une désignation
    """
    if requests is None:
        return JsonResponse({
            'success': False,
            'error': 'Module requests non installé. Installez-le avec: pip install requests'
        }, status=500)

    try:
        designation = Designation.objects.get(id=designation_id)

        # Construire la requête de recherche
        # Utiliser le nom de la désignation + type si disponible
        search_query = designation.nom
        if designation.type_designation:
            search_query += f" {designation.type_designation.nom}"

        # Appel à l'API Unsplash
        url = "https://api.unsplash.com/search/photos"
        params = {
            'query': search_query,
            'per_page': 6,  # 6 suggestions
            'orientation': 'squarish',  # Photos carrées pour les cards
        }
        headers = {
            'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'
        }

        # Si pas de clé API, utiliser des photos de placeholder
        if UNSPLASH_ACCESS_KEY == 'votre_cle_api_ici':
            # Générer des URLs de placeholder
            photos = [
                {
                    'id': f'placeholder-{i}',
                    'url': f'https://via.placeholder.com/400x400/3B82F6/FFFFFF?text={designation.nom[:20]}',
                    'thumb': f'https://via.placeholder.com/200x200/3B82F6/FFFFFF?text={designation.nom[:20]}',
                    'author': 'Placeholder',
                    'source': 'placeholder'
                }
                for i in range(6)
            ]
        else:
            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                photos = [
                    {
                        'id': photo['id'],
                        'url': photo['urls']['regular'],
                        'thumb': photo['urls']['thumb'],
                        'author': photo['user']['name'],
                        'source': 'unsplash'
                    }
                    for photo in data.get('results', [])
                ]
            else:
                return JsonResponse({
                    'success': False,
                    'error': f'Erreur API Unsplash: {response.status_code}'
                }, status=500)

        return JsonResponse({
            'success': True,
            'designation_id': str(designation_id),
            'designation_nom': designation.nom,
            'search_query': search_query,
            'photos': photos,
            'count': len(photos)
        })

    except Designation.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Désignation non trouvée'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_save_photo(request, designation_id):
    """
    Sauvegarder l'URL de la photo sélectionnée pour une désignation
    """
    try:
        import json
        designation = Designation.objects.get(id=designation_id)

        data = json.loads(request.body)
        photo_url = data.get('photo_url')

        if not photo_url:
            return JsonResponse({
                'success': False,
                'error': 'URL de photo manquante'
            }, status=400)

        # Sauvegarder l'URL dans le champ photo
        designation.photo = photo_url
        designation.save()

        return JsonResponse({
            'success': True,
            'message': f'Photo sauvegardée pour {designation.nom}',
            'designation_id': str(designation_id),
            'photo_url': photo_url
        })

    except Designation.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Désignation non trouvée'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_clear_photo(request, designation_id):
    """
    Supprimer la photo d'une désignation
    """
    try:
        designation = Designation.objects.get(id=designation_id)

        # Supprimer le fichier uploadé s'il existe
        if designation.photo_file:
            designation.photo_file.delete(save=False)

        designation.photo = None
        designation.photo_file = None
        designation.save()

        return JsonResponse({
            'success': True,
            'message': f'Photo supprimée pour {designation.nom}',
            'designation_id': str(designation_id)
        })

    except Designation.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Désignation non trouvée'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_upload_photo(request, designation_id):
    """
    Uploader une photo depuis l'ordinateur ou l'appareil photo (mobile)
    Supporte les fichiers envoyés via FormData avec le champ 'photo'
    """
    try:
        designation = Designation.objects.get(id=designation_id)

        # Vérifier qu'un fichier a été envoyé
        if 'photo' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'Aucun fichier fourni'
            }, status=400)

        photo_file = request.FILES['photo']

        # Vérifier le type de fichier (images seulement)
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if photo_file.content_type not in allowed_types:
            return JsonResponse({
                'success': False,
                'error': 'Type de fichier non autorisé. Utilisez JPG, PNG, GIF ou WebP.'
            }, status=400)

        # Vérifier la taille (max 5 MB)
        if photo_file.size > 5 * 1024 * 1024:
            return JsonResponse({
                'success': False,
                'error': 'Fichier trop volumineux. Taille maximale: 5 MB.'
            }, status=400)

        # Supprimer l'ancienne photo si elle existe
        if designation.photo_file:
            designation.photo_file.delete(save=False)

        # Sauvegarder la nouvelle photo
        designation.photo_file = photo_file
        designation.photo = None  # Priorité au fichier local
        designation.save()

        return JsonResponse({
            'success': True,
            'message': f'Photo uploadée avec succès pour {designation.nom}',
            'designation_id': str(designation_id),
            'photo_url': designation.photo_file.url
        })

    except Designation.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Désignation non trouvée'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
