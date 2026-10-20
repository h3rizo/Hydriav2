# -*- coding: utf-8 -*-
"""
Service pour interagir avec l'API Google Drive
Utilisé pour l'import des fichiers DiameX depuis Google Drive
"""

import os
import io
from typing import List, Dict, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from django.conf import settings

class GoogleDriveService:
    """Service pour gérer les opérations Google Drive"""

    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

    def __init__(self):
        """Initialise le service Google Drive avec les credentials du Service Account"""
        credentials_path = os.path.join(
            settings.BASE_DIR,
            'credentials',
            'google_drive_service_account.json'
        )

        if not os.path.exists(credentials_path):
            raise FileNotFoundError(f"Fichier credentials introuvable: {credentials_path}")

        # Créer les credentials depuis le fichier JSON
        self.credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=self.SCOPES
        )

        # Construire le service Drive
        self.service = build('drive', 'v3', credentials=self.credentials)

    def list_folders_in_folder(self, folder_id: str) -> List[Dict]:
        """
        Liste les dossiers dans un dossier parent

        Args:
            folder_id: ID du dossier parent Google Drive

        Returns:
            Liste de dictionnaires avec id, name pour chaque dossier
        """
        try:
            query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"

            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                orderBy='name'
            ).execute()

            folders = results.get('files', [])
            return folders

        except Exception as e:
            raise Exception(f"Erreur lors de la liste des dossiers: {str(e)}")

    def list_files_in_folder(self, folder_id: str, file_extension: Optional[str] = None) -> List[Dict]:
        """
        Liste les fichiers dans un dossier

        Args:
            folder_id: ID du dossier Google Drive
            file_extension: Extension de fichier à filtrer (ex: '.accde', '.mdb')

        Returns:
            Liste de dictionnaires avec id, name, mimeType pour chaque fichier
        """
        try:
            # Query de base : fichiers dans ce dossier, non supprimés, non dossiers
            query = f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"

            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, mimeType, size, modifiedTime)',
                orderBy='name'
            ).execute()

            files = results.get('files', [])

            # Filtrer par extension si spécifié
            if file_extension:
                extension = file_extension.lower()
                if not extension.startswith('.'):
                    extension = '.' + extension
                files = [f for f in files if f['name'].lower().endswith(extension)]

            return files

        except Exception as e:
            raise Exception(f"Erreur lors de la liste des fichiers: {str(e)}")

    def find_scan_folder(self, parent_folder_id: str) -> Optional[Dict]:
        """
        Trouve le dossier contenant le mot 'scan' dans son nom

        Args:
            parent_folder_id: ID du dossier parent (ex: dossier 03 COMPTA)

        Returns:
            Dictionnaire avec id, name du dossier scan ou None si non trouvé
        """
        try:
            folders = self.list_folders_in_folder(parent_folder_id)

            # Chercher un dossier avec 'scan' dans le nom (insensible à la casse)
            for folder in folders:
                if 'scan' in folder['name'].lower():
                    return folder

            return None

        except Exception as e:
            raise Exception(f"Erreur lors de la recherche du dossier scan: {str(e)}")

    def get_file_metadata(self, file_id: str) -> Dict:
        """
        Récupère les métadonnées d'un fichier

        Args:
            file_id: ID du fichier Google Drive

        Returns:
            Dictionnaire avec les métadonnées du fichier
        """
        try:
            file_metadata = self.service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, size, modifiedTime, webViewLink'
            ).execute()

            return file_metadata

        except Exception as e:
            raise Exception(f"Erreur lors de la récupération des métadonnées: {str(e)}")

    def download_file(self, file_id: str, destination_path: str) -> str:
        """
        Télécharge un fichier depuis Google Drive

        Args:
            file_id: ID du fichier Google Drive
            destination_path: Chemin local où enregistrer le fichier

        Returns:
            Chemin du fichier téléchargé
        """
        try:
            # Créer le répertoire de destination si nécessaire
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)

            # Télécharger le fichier
            request = self.service.files().get_media(fileId=file_id)

            with io.FileIO(destination_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

            return destination_path

        except Exception as e:
            raise Exception(f"Erreur lors du téléchargement du fichier: {str(e)}")

    def get_folder_structure(self, base_folder_id: str) -> Dict:
        """
        Récupère la structure complète d'un dossier de base (pour une Base)
        Ex: SKJ VAVATENINA -> 03 COMPTA -> fichier .accde + dossier scan

        Args:
            base_folder_id: ID du dossier de base (ex: SKJ VAVATENINA)

        Returns:
            Dictionnaire avec la structure du dossier:
            {
                'base_folder': {...},
                'compta_folder': {...},
                'accde_file': {...},
                'scan_folder': {...}
            }
        """
        try:
            structure = {
                'base_folder': None,
                'compta_folder': None,
                'accde_file': None,
                'scan_folder': None
            }

            # Récupérer les métadonnées du dossier de base
            structure['base_folder'] = self.get_file_metadata(base_folder_id)

            # Chercher le dossier 03 COMPTA
            folders = self.list_folders_in_folder(base_folder_id)
            compta_folder = next((f for f in folders if '03 COMPTA' in f['name']), None)

            if not compta_folder:
                raise Exception("Dossier '03 COMPTA' introuvable")

            structure['compta_folder'] = compta_folder

            # Chercher le fichier .accde dans 03 COMPTA
            accde_files = self.list_files_in_folder(compta_folder['id'], '.accde')
            if accde_files:
                structure['accde_file'] = accde_files[0]  # Prendre le premier

            # Chercher le dossier scan
            structure['scan_folder'] = self.find_scan_folder(compta_folder['id'])

            return structure

        except Exception as e:
            raise Exception(f"Erreur lors de la récupération de la structure: {str(e)}")