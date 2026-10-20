#!/usr/bin/env python
import os
import sys

# Ajouter le chemin du projet
sys.path.insert(0, '/home/soakoja/hydria/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

import django
django.setup()

from apps.accounting.google_drive_service import GoogleDriveService
from apps.organization.models import Base

print('[TEST] Début du test Google Drive API...\n')

# Récupérer une base avec folder_id
base = Base.objects.filter(google_drive_folder_id__isnull=False).first()

if not base:
    print('[ERROR] Aucune base avec google_drive_folder_id trouvée')
    sys.exit(1)

print(f'[INFO] Base: {base.nom_base}')
print(f'[INFO] Folder ID: {base.google_drive_folder_id}')

# Tester l'initialisation du service
try:
    print('\n[TEST] Initialisation du GoogleDriveService...')
    service = GoogleDriveService()
    print('[OK] GoogleDriveService initialisé avec succès')
except Exception as e:
    print(f'[ERROR] Échec initialisation: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Tester l'accès au dossier
try:
    print(f'\n[TEST] Récupération de la structure du dossier {base.google_drive_folder_id}...')
    structure = service.get_folder_structure(base.google_drive_folder_id)

    files_count = len(structure.get('files', []))
    folders_count = len(structure.get('folders', []))

    print(f'[OK] Structure récupérée avec succès!')
    print(f'[INFO] Fichiers trouvés: {files_count}')
    print(f'[INFO] Dossiers trouvés: {folders_count}')

    # Afficher quelques fichiers
    if structure.get('files'):
        print('\n[INFO] Premiers fichiers:')
        for file in structure['files'][:5]:
            print(f'  - {file.get("name")}')

    if structure.get('folders'):
        print('\n[INFO] Premiers dossiers:')
        for folder in structure['folders'][:5]:
            print(f'  - {folder.get("name")}')

except Exception as e:
    print(f'[ERROR] Échec récupération structure: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

print('\n[OK] Test terminé avec succès!')
