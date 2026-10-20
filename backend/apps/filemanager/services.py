"""
Services pour la gestion des fichiers avec Supabase Storage
"""
import os
import uuid
from typing import Optional, Tuple
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from supabase import create_client, Client
import logging

logger = logging.getLogger(__name__)


class SupabaseStorageService:
    """
    Service pour gérer l'upload/download des fichiers vers Supabase Storage
    """
    
    def __init__(self):
        self.bucket_name = "HydriaStock"
        supabase_url = (getattr(settings, 'SUPABASE_URL', '') or '').strip()
        supabase_key = (getattr(settings, 'SUPABASE_SERVICE_KEY', '') or '').strip()

        if not supabase_url or not supabase_key:
            self.supabase = None
            self.supabase_available = False
            logger.info("Supabase non configure, stockage local active.")
            return

        try:
            self.supabase: Client = create_client(supabase_url, supabase_key)
            self.supabase_available = True
        except Exception as e:
            logger.error(f"Erreur d'initialisation Supabase: {e}")
            self.supabase_available = False
    
    def ensure_bucket_exists(self) -> bool:
        """
        Vérifie que le bucket existe, sinon le crée
        """
        if not self.supabase_available:
            return False
            
        try:
            # Essayer de récupérer le bucket
            self.supabase.storage.get_bucket(self.bucket_name)
            return True
        except Exception as e:
            logger.info(f"Bucket {self.bucket_name} n'existe pas, tentative de création...")
            try:
                # Créer le bucket s'il n'existe pas
                self.supabase.storage.create_bucket(
                    self.bucket_name,
                    options={"public": False}  # Bucket privé par défaut
                )
                logger.info(f"Bucket {self.bucket_name} créé avec succès")
                return True
            except Exception as create_error:
                logger.error(f"Erreur lors de la création du bucket: {create_error}")
                # Vérifier si c'est un problème de permissions
                if "row-level security policy" in str(create_error) or "Unauthorized" in str(create_error):
                    logger.error("PERMISSION DENIED: Vous utilisez probablement la clé 'anon' au lieu de 'service_role'")
                    logger.error("Solution: Remplacez SUPABASE_SERVICE_KEY par votre clé service_role dans le .env")
                return False
    
    def upload_file(self, uploaded_file: UploadedFile, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Upload un fichier vers Supabase Storage avec fallback local
        
        Args:
            uploaded_file: Le fichier Django uploadé
            file_path: Le chemin de destination dans le bucket
            
        Returns:
            Tuple[bool, Optional[str]]: (succès, message d'erreur si échec)
        """
        # Essayer d'abord Supabase
        if self.supabase_available:
            try:
                # Vérifier que le bucket existe
                if not self.ensure_bucket_exists():
                    logger.warning("Bucket Supabase inaccessible, utilisation du stockage local")
                    return self._upload_local_fallback(uploaded_file, file_path)
                
                # Lire le contenu du fichier
                file_content = uploaded_file.read()
                uploaded_file.seek(0)  # Reset file pointer
                
                # Upload vers Supabase
                response = self.supabase.storage.from_(self.bucket_name).upload(
                    path=file_path,
                    file=file_content,
                    file_options={
                        "content-type": uploaded_file.content_type or "application/octet-stream"
                    }
                )
                
                logger.info(f"Fichier uploadé avec succès vers Supabase: {file_path}")
                return True, None
                
            except Exception as e:
                logger.error(f"Erreur Supabase, fallback vers stockage local: {str(e)}")
                return self._upload_local_fallback(uploaded_file, file_path)
        else:
            logger.info("Supabase non disponible, utilisation du stockage local")
            return self._upload_local_fallback(uploaded_file, file_path)
    
    def _upload_local_fallback(self, uploaded_file: UploadedFile, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Fallback : stocker le fichier localement dans media/uploads/
        """
        try:
            # Créer le répertoire local
            local_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', os.path.dirname(file_path))
            os.makedirs(local_dir, exist_ok=True)
            
            # Chemin complet du fichier
            local_file_path = os.path.join(settings.MEDIA_ROOT, 'uploads', file_path)
            
            # Sauvegarder le fichier
            with open(local_file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            logger.info(f"Fichier sauvegardé localement: {local_file_path}")
            return True, None
            
        except Exception as e:
            error_msg = f"Erreur lors de la sauvegarde locale: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def download_file(self, file_path: str) -> Tuple[bool, Optional[bytes], Optional[str]]:
        """
        Télécharge un fichier depuis Supabase Storage avec fallback local
        
        Args:
            file_path: Le chemin du fichier dans le bucket
            
        Returns:
            Tuple[bool, Optional[bytes], Optional[str]]: (succès, contenu du fichier, message d'erreur)
        """
        # Essayer d'abord Supabase
        if self.supabase_available:
            try:
                response = self.supabase.storage.from_(self.bucket_name).download(file_path)
                return True, response, None
            except Exception as e:
                logger.warning(f"Échec téléchargement Supabase, essai local: {str(e)}")
                return self._download_local_fallback(file_path)
        else:
            return self._download_local_fallback(file_path)
    
    def _download_local_fallback(self, file_path: str) -> Tuple[bool, Optional[bytes], Optional[str]]:
        """
        Fallback : télécharger depuis le stockage local
        """
        try:
            local_file_path = os.path.join(settings.MEDIA_ROOT, 'uploads', file_path)
            
            if not os.path.exists(local_file_path):
                return False, None, "Fichier non trouvé localement"
            
            with open(local_file_path, 'rb') as f:
                content = f.read()
            
            return True, content, None
            
        except Exception as e:
            error_msg = f"Erreur lors du téléchargement local: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
    
    def delete_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Supprime un fichier de Supabase Storage
        
        Args:
            file_path: Le chemin du fichier dans le bucket
            
        Returns:
            Tuple[bool, Optional[str]]: (succès, message d'erreur si échec)
        """
        try:
            response = self.supabase.storage.from_(self.bucket_name).remove([file_path])
            logger.info(f"Fichier supprimé avec succès: {file_path}")
            return True, None
            
        except Exception as e:
            error_msg = f"Erreur lors de la suppression: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_public_url(self, file_path: str) -> Optional[str]:
        """
        Génère une URL publique pour un fichier (si le bucket est public)
        
        Args:
            file_path: Le chemin du fichier dans le bucket
            
        Returns:
            Optional[str]: L'URL publique ou None si erreur
        """
        try:
            response = self.supabase.storage.from_(self.bucket_name).get_public_url(file_path)
            return response
        except Exception as e:
            logger.error(f"Erreur lors de la génération de l'URL publique: {str(e)}")
            return None
    
    def create_signed_url(self, file_path: str, expires_in: int = 3600) -> Optional[str]:
        """
        Crée une URL signée temporaire pour un fichier privé
        
        Args:
            file_path: Le chemin du fichier dans le bucket
            expires_in: Durée de validité en secondes (défaut: 1 heure)
            
        Returns:
            Optional[str]: L'URL signée ou None si erreur
        """
        try:
            response = self.supabase.storage.from_(self.bucket_name).create_signed_url(
                file_path, expires_in
            )
            return response.get('signedURL')
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'URL signée: {str(e)}")
            return None
    
    def list_files(self, folder_path: str = "") -> Tuple[bool, list, Optional[str]]:
        """
        Liste les fichiers dans un dossier du bucket
        
        Args:
            folder_path: Le chemin du dossier (vide pour la racine)
            
        Returns:
            Tuple[bool, list, Optional[str]]: (succès, liste des fichiers, message d'erreur)
        """
        try:
            response = self.supabase.storage.from_(self.bucket_name).list(folder_path)
            return True, response, None
            
        except Exception as e:
            error_msg = f"Erreur lors de la liste des fichiers: {str(e)}"
            logger.error(error_msg)
            return False, [], error_msg


def generate_unique_filename(original_filename: str) -> str:
    """
    Génère un nom de fichier unique en conservant l'extension
    
    Args:
        original_filename: Le nom original du fichier
        
    Returns:
        str: Le nom unique généré
    """
    name, ext = os.path.splitext(original_filename)
    unique_id = str(uuid.uuid4())
    return f"{unique_id}{ext}"


def get_file_category(content_type: str) -> str:
    """
    Détermine la catégorie d'un fichier basé sur son content_type
    
    Args:
        content_type: Le type MIME du fichier
        
    Returns:
        str: La catégorie du fichier
    """
    if content_type.startswith('image/'):
        return 'images'
    elif content_type.startswith('video/'):
        return 'videos'
    elif content_type.startswith('audio/'):
        return 'audio'
    elif 'pdf' in content_type:
        return 'documents'
    elif any(doc_type in content_type for doc_type in ['word', 'excel', 'powerpoint', 'spreadsheet']):
        return 'documents'
    elif 'text' in content_type:
        return 'text'
    else:
        return 'others'


# Instance globale du service
storage_service = SupabaseStorageService()
