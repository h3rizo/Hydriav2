# -*- coding: utf-8 -*-
"""
Vues API pour l'intégration Google Drive avec DiameX
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
import json
import logging

from apps.organization.models import Base
from .google_drive_service import GoogleDriveService

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def api_list_google_drive_bases(request):
    """
    Liste les bases avec Google Drive configuré et actif

    Returns:
        JSON avec la liste des bases Google Drive
    """
    try:
        # Filtrer les bases avec Google Drive actif
        bases = Base.objects.filter(
            google_drive_actif=True,
            google_drive_folder_id__isnull=False
        ).exclude(
            google_drive_folder_id=''
        ).values(
            'id',
            'nom',
            'organisation__nom',
            'google_drive_folder_id',
            'google_drive_folder_path'
        )

        bases_list = []
        for base in bases:
            bases_list.append({
                'id': str(base['id']),
                'nom': base['nom'],
                'organisation': base['organisation__nom'],
                'folder_id': base['google_drive_folder_id'],
                'folder_path': base['google_drive_folder_path']
            })

        return JsonResponse({
            'success': True,
            'bases': bases_list,
            'count': len(bases_list)
        })

    except Exception as e:
        logger.error(f"Erreur lors de la liste des bases Google Drive: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_browse_google_drive_folder(request):
    """
    Parcourt un dossier Google Drive

    Paramètres GET:
        - folder_id: ID du dossier Google Drive

    Returns:
        JSON avec la liste des fichiers et dossiers
    """
    try:
        folder_id = request.GET.get('folder_id')

        if not folder_id:
            return JsonResponse({
                'success': False,
                'error': 'ID du dossier requis'
            }, status=400)

        # Initialiser le service Google Drive
        drive_service = GoogleDriveService()

        # Lister les dossiers
        folders = drive_service.list_folders_in_folder(folder_id)

        # Lister les fichiers (filtrer les .accde et .mdb)
        accde_files = drive_service.list_files_in_folder(folder_id, '.accde')
        mdb_files = drive_service.list_files_in_folder(folder_id, '.mdb')

        all_files = accde_files + mdb_files

        return JsonResponse({
            'success': True,
            'folders': folders,
            'files': all_files,
            'folder_id': folder_id
        })

    except Exception as e:
        logger.error(f"Erreur lors du parcours du dossier Google Drive: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_get_base_structure(request):
    """
    Récupère la structure complète d'une base Google Drive
    (dossier 03 COMPTA, fichier .accde, dossier scan)

    Paramètres GET:
        - base_id: ID de la base

    Returns:
        JSON avec la structure du dossier
    """
    try:
        base_id = request.GET.get('base_id')

        if not base_id:
            return JsonResponse({
                'success': False,
                'error': 'ID de la base requis'
            }, status=400)

        # Récupérer la base
        try:
            base = Base.objects.get(id=base_id, google_drive_actif=True)
        except Base.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Base introuvable ou Google Drive non actif'
            }, status=404)

        if not base.google_drive_folder_id:
            return JsonResponse({
                'success': False,
                'error': 'Dossier Google Drive non configuré pour cette base'
            }, status=400)

        # Initialiser le service Google Drive
        drive_service = GoogleDriveService()

        # Récupérer la structure
        structure = drive_service.get_folder_structure(base.google_drive_folder_id)

        return JsonResponse({
            'success': True,
            'base': {
                'id': str(base.id),
                'nom': base.nom,
                'organisation': base.organisation.nom if base.organisation else None
            },
            'structure': structure
        })

    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la structure: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_import_from_google_drive(request):
    """
    Importe un fichier DiameX depuis Google Drive

    Paramètres POST (JSON):
        - file_id: ID du fichier Google Drive
        - base_id: ID de la base
        - import_type: Type d'import (DATA, SoldesReels, etc.)

    Returns:
        JSON avec le résultat de l'import
    """
    try:
        data = json.loads(request.body)

        file_id = data.get('file_id')
        base_id = data.get('base_id')
        import_type = data.get('import_type', 'DATA')

        if not file_id or not base_id:
            return JsonResponse({
                'success': False,
                'error': 'ID du fichier et de la base requis'
            }, status=400)

        # Récupérer la base
        try:
            base = Base.objects.get(id=base_id)
        except Base.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Base introuvable'
            }, status=404)

        # Initialiser le service Google Drive
        drive_service = GoogleDriveService()

        # Récupérer les métadonnées du fichier
        file_metadata = drive_service.get_file_metadata(file_id)

        # Créer un répertoire temporaire pour le téléchargement
        import tempfile
        import os

        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, file_metadata['name'])

        try:
            # Télécharger le fichier
            drive_service.download_file(file_id, temp_file_path)

            # Importer le fichier (réutiliser la logique existante d'import)
            # Cette partie sera à adapter selon la structure existante

            return JsonResponse({
                'success': True,
                'message': f"Fichier '{file_metadata['name']}' téléchargé avec succès",
                'file_name': file_metadata['name'],
                'file_size': file_metadata.get('size'),
                'temp_path': temp_file_path
            })

        except Exception as e:
            # Nettoyer le fichier temporaire en cas d'erreur
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise e

    except Exception as e:
        logger.error(f"Erreur lors de l'import depuis Google Drive: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)