#!/usr/bin/env python
import os
import sys

# Ajouter le chemin du projet
sys.path.insert(0, '/home/soakoja/hydria/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

import django
django.setup()

from apps.organization.models import Base

# Le Folder ID du dossier "03 COMPTA"
FOLDER_ID = '1reDoVBSODfJGGo3odpvUaGzGYz9Mw-Ru'

print('[INFO] Mise à jour de la configuration Google Drive...\n')

# Chercher toutes les bases
bases = Base.objects.all()
print(f'[INFO] {bases.count()} base(s) trouvée(s)\n')

# Afficher les bases disponibles
for i, base in enumerate(bases, 1):
    print(f'{i}. {base.nom_base}')
    if base.google_drive_folder_id:
        print(f'   Folder ID actuel: {base.google_drive_folder_id}')
    else:
        print(f'   Pas de Folder ID configuré')

# Mettre à jour toutes les bases qui n'ont pas encore le Folder ID
print(f'\n[UPDATE] Mise à jour des bases...')

updated_count = 0
for base in bases:
    if base.google_drive_folder_id != FOLDER_ID:
        base.google_drive_folder_id = FOLDER_ID
        base.save()
        print(f'  - {base.nom_base}: Folder ID défini à {FOLDER_ID}')
        updated_count += 1
    else:
        print(f'  - {base.nom_base}: Déjà configuré')

print(f'\n[OK] {updated_count} base(s) mise(s) à jour!')
