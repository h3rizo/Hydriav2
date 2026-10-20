import os
import uuid
import mimetypes
from datetime import datetime
from django.conf import settings
import requests
import tempfile

# Configuration Supabase
SUPABASE_URL = "https://ytqvyihgztdnwkgvozqn.supabase.co"
SUPABASE_KEY = getattr(settings, 'SUPABASE_KEY', None)
BUCKET_NAME = "HydriaStock"


def generate_unique_filename(original_filename):
    """Génère un nom de fichier unique"""
    name, ext = os.path.splitext(original_filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = uuid.uuid4().hex[:8]
    return f"{timestamp}_{unique_id}_{name}{ext}"


def get_file_folder(filename):
    """Détermine le dossier selon le type de fichier"""
    mime_type, _ = mimetypes.guess_type(filename)
    
    if mime_type:
        if mime_type.startswith('image/'):
            return 'images'
        elif mime_type.startswith('video/'):
            return 'videos'
        elif mime_type.startswith('audio/'):
            return 'audio'
        elif mime_type == 'application/pdf':
            return 'documents/pdf'
        elif mime_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
            return 'documents/word'
        elif mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
            return 'documents/excel'
        elif mime_type.startswith('text/'):
            return 'documents/text'
    
    return 'autres'


def upload_to_supabase(uploaded_file):
    """
    Upload un fichier vers Supabase Storage
    Retourne le chemin du fichier dans le bucket
    """
    try:
        # Générer un nom de fichier unique
        unique_filename = generate_unique_filename(uploaded_file.name)
        
        # Déterminer le dossier
        folder = get_file_folder(uploaded_file.name)
        file_path = f"{folder}/{unique_filename}"
        
        # Pour le moment, simulation de l'upload
        # En production, vous devrez utiliser la bibliothèque Supabase Python
        # ou faire des appels API directs
        
        # Simuler l'upload avec succès
        
        return file_path
        
    except Exception as e:
        raise Exception(f"Erreur lors de l'upload vers Supabase: {str(e)}")


def delete_from_supabase(file_path):
    """
    Supprime un fichier de Supabase Storage
    """
    try:
        # Pour le moment, simulation de la suppression
        # En production, vous devrez utiliser l'API Supabase
        
        
        return True
        
    except Exception as e:
        raise Exception(f"Erreur lors de la suppression de Supabase: {str(e)}")


def get_supabase_url(file_path):
    """
    Génère l'URL publique d'un fichier dans Supabase Storage
    """
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{file_path}"


def upload_to_supabase_real(uploaded_file, supabase_key):
    """
    Upload réel vers Supabase Storage (à utiliser en production)
    """
    if not supabase_key:
        raise Exception("Clé Supabase non configurée")
    
    try:
        # Générer un nom de fichier unique
        unique_filename = generate_unique_filename(uploaded_file.name)
        folder = get_file_folder(uploaded_file.name)
        file_path = f"{folder}/{unique_filename}"
        
        # URL pour l'upload
        upload_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET_NAME}/{file_path}"
        
        # Headers pour l'authentification
        headers = {
            'Authorization': f'Bearer {supabase_key}',
            'Content-Type': uploaded_file.content_type or 'application/octet-stream'
        }
        
        # Upload du fichier
        response = requests.post(
            upload_url,
            headers=headers,
            data=uploaded_file.read()
        )
        
        if response.status_code == 200:
            return file_path
        else:
            raise Exception(f"Erreur API Supabase: {response.status_code} - {response.text}")
            
    except Exception as e:
        raise Exception(f"Erreur lors de l'upload vers Supabase: {str(e)}")


def delete_from_supabase_real(file_path, supabase_key):
    """
    Suppression réelle de Supabase Storage (à utiliser en production)
    """
    if not supabase_key:
        raise Exception("Clé Supabase non configurée")
    
    try:
        # URL pour la suppression
        delete_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET_NAME}/{file_path}"
        
        # Headers pour l'authentification
        headers = {
            'Authorization': f'Bearer {supabase_key}'
        }
        
        # Suppression du fichier
        response = requests.delete(delete_url, headers=headers)
        
        if response.status_code in [200, 204]:
            return True
        else:
            raise Exception(f"Erreur API Supabase: {response.status_code} - {response.text}")
            
    except Exception as e:
        raise Exception(f"Erreur lors de la suppression de Supabase: {str(e)}")


def validate_file_type(filename):
    """Valide le type de fichier autorisé"""
    allowed_extensions = [
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.txt', '.rtf', '.csv',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg',
        '.mp4', '.avi', '.mov', '.mkv', '.wmv',
        '.mp3', '.wav', '.ogg', '.flac',
        '.zip', '.rar', '.7z', '.tar.gz'
    ]
    
    _, ext = os.path.splitext(filename.lower())
    return ext in allowed_extensions


def get_file_icon_class(mime_type):
    """Retourne la classe CSS pour l'icône du fichier selon son type"""
    if not mime_type:
        return 'fas fa-file'
    
    if mime_type.startswith('image/'):
        return 'fas fa-file-image text-green-500'
    elif mime_type.startswith('video/'):
        return 'fas fa-file-video text-blue-500'
    elif mime_type.startswith('audio/'):
        return 'fas fa-file-audio text-purple-500'
    elif mime_type == 'application/pdf':
        return 'fas fa-file-pdf text-red-500'
    elif mime_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        return 'fas fa-file-word text-blue-600'
    elif mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
        return 'fas fa-file-excel text-green-600'
    elif mime_type.startswith('text/'):
        return 'fas fa-file-alt text-gray-500'
    elif mime_type in ['application/zip', 'application/x-rar-compressed']:
        return 'fas fa-file-archive text-yellow-600'
    else:
        return 'fas fa-file text-gray-400'