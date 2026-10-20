import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.organization.models import Base

print('[INFO] Vérification de la configuration Google Drive...\n')

bases = Base.objects.filter(google_drive_folder_id__isnull=False)
print(f'[INFO] {bases.count()} base(s) avec Google Drive configuré\n')

for base in bases:
    print(f'[BASE] {base.nom}')
    print(f'  Folder ID: {base.google_drive_folder_id}')
    print(f'  Chemin: {base.chemin_base_diamex}')
    print()

# Vérifier si le fichier credentials existe
credentials_path = '/home/soakoja/hydria/backend/credentials/google_drive_service_account.json'
if os.path.exists(credentials_path):
    print(f'[OK] Fichier credentials trouvé: {credentials_path}')
    print(f'  Taille: {os.path.getsize(credentials_path)} octets')
else:
    print(f'[ERROR] Fichier credentials introuvable: {credentials_path}')
