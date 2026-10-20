"""
Vues pour la gestion des uploads de photos pour Points d'Eau et Équipements
"""
import os
import uuid
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.conf import settings
from django.utils import timezone

from apps.billing.models import PointEau
from apps.infrastructure.models import EquipementConstitutif


@csrf_exempt
@require_http_methods(["POST"])
def upload_point_eau_photos(request, point_eau_id):
    """
    Upload de photos pour un point d'eau
    """
    print(f"\n{'='*60}")
    print(f"[LOG] Upload photos pour point_eau_id: {point_eau_id}")
    print(f"[LOG] request.FILES keys: {list(request.FILES.keys())}")
    print(f"[LOG] request.POST keys: {list(request.POST.keys())}")
    print(f"[LOG] Content-Type: {request.META.get('CONTENT_TYPE', 'N/A')}")
    print(f"{'='*60}\n")

    try:
        point_eau = PointEau.objects.get(id=point_eau_id)
        print(f"[OK] Point d'eau trouvé: {point_eau.nomabonne}")
    except PointEau.DoesNotExist:
        print(f"[ERROR] Point d'eau {point_eau_id} introuvable")
        return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable'}, status=404)
    except Exception as e:
        print(f"[ERROR] Erreur lors de la récupération du point d'eau: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Erreur: {str(e)}'}, status=500)

    # Récupérer les photos depuis la requête
    photos = request.FILES.getlist('photos')
    print(f"[LOG] Nombre de photos reçues: {len(photos)}")

    if not photos:
        print(f"[ERROR] Aucune photo fournie dans request.FILES")
        print(f"[INFO] Clés disponibles dans FILES: {list(request.FILES.keys())}")
        return JsonResponse({'success': False, 'error': 'Aucune photo fournie. Vérifiez le nom du champ.'}, status=400)

    # Créer le dossier si nécessaire
    upload_dir = os.path.join('photos', 'points_eau', str(point_eau_id))
    os.makedirs(os.path.join(settings.MEDIA_ROOT, upload_dir), exist_ok=True)

    # Récupérer les photos existantes ou initialiser
    existing_photos = point_eau.photos if point_eau.photos else []

    uploaded_count = 0
    for photo in photos:
        # Vérifier la taille (max 5MB)
        if photo.size > 5 * 1024 * 1024:
            continue

        # Vérifier le type
        if not photo.content_type.startswith('image/'):
            continue

        # Générer un nom unique
        ext = os.path.splitext(photo.name)[1]
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(upload_dir, filename)

        # Sauvegarder le fichier
        saved_path = default_storage.save(filepath, photo)
        saved_url = default_storage.url(saved_path)
        print(f"[LOG] Photo sauvegardée: {saved_path} -> URL: {saved_url}")

        # Ajouter aux métadonnées
        photo_data = {
            'url': saved_url,
            'filename': filename,
            'size': photo.size,
            'uploaded_at': str(uuid.uuid1().time)
        }
        existing_photos.append(photo_data)
        uploaded_count += 1

    # Mettre à jour le point d'eau
    point_eau.photos = existing_photos
    point_eau.updatedat = timezone.now()
    update_fields = ['photos', 'updatedat']
    employe = getattr(request.user, 'employe', None) if request.user.is_authenticated else None
    if employe:
        point_eau.updated_by = employe
        update_fields.append('updated_by')
    point_eau.save(update_fields=update_fields)
    print(f"[OK] Point d'eau mis à jour avec {len(existing_photos)} photo(s)")

    return JsonResponse({
        'success': True,
        'nb_uploaded': uploaded_count,
        'total_photos': len(existing_photos)
    })


@csrf_exempt
@require_http_methods(["POST"])
def upload_equipement_photos(request, equipement_id):
    """
    Upload de photos pour un équipement
    """
    try:
        equipement = EquipementConstitutif.objects.get(id=equipement_id)
    except EquipementConstitutif.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Équipement introuvable'}, status=404)

    # Récupérer les photos depuis la requête
    photos = request.FILES.getlist('photos')

    if not photos:
        return JsonResponse({'success': False, 'error': 'Aucune photo fournie'}, status=400)

    # Créer le dossier si nécessaire
    upload_dir = os.path.join('photos', 'equipements', str(equipement_id))
    os.makedirs(os.path.join(settings.MEDIA_ROOT, upload_dir), exist_ok=True)

    # Récupérer les photos existantes ou initialiser
    existing_photos = equipement.photos if equipement.photos else []

    uploaded_count = 0
    for photo in photos:
        # Vérifier la taille (max 5MB)
        if photo.size > 5 * 1024 * 1024:
            continue

        # Vérifier le type
        if not photo.content_type.startswith('image/'):
            continue

        # Générer un nom unique
        ext = os.path.splitext(photo.name)[1]
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(upload_dir, filename)

        # Sauvegarder le fichier
        saved_path = default_storage.save(filepath, photo)

        # Ajouter aux métadonnées
        photo_data = {
            'url': default_storage.url(saved_path),
            'filename': filename,
            'size': photo.size,
            'uploaded_at': str(uuid.uuid1().time)
        }
        existing_photos.append(photo_data)
        uploaded_count += 1

    # Mettre à jour l'équipement
    equipement.photos = existing_photos
    equipement.save()

    return JsonResponse({
        'success': True,
        'nb_uploaded': uploaded_count,
        'total_photos': len(existing_photos)
    })
