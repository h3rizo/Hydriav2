from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
credentials = service_account.Credentials.from_service_account_file(
    '/home/soakoja/hydria/backend/credentials/google_drive_service_account.json',
    scopes=SCOPES
)

service = build('drive', 'v3', credentials=credentials)

try:
    print('[INFO] Listage de tous les fichiers/dossiers accessibles par le compte de service...\n')

    results = service.files().list(
        pageSize=20,
        fields='files(id, name, mimeType, owners)'
    ).execute()

    files = results.get('files', [])

    if not files:
        print('[WARNING] Aucun fichier ou dossier trouvé!')
        print('[INFO] Le compte de service n\'a peut-être pas accès à des fichiers partagés.')
        print('[INFO] Vérifiez que le dossier est bien partagé avec: diamex@diamex-483417.iam.gserviceaccount.com')
    else:
        print(f'[OK] {len(files)} fichier(s)/dossier(s) trouvé(s):\n')
        for f in files:
            print(f"  - {f['name']} ({f['mimeType']})")
            print(f"    ID: {f['id']}")
            print()

except Exception as e:
    print(f'[ERROR] {str(e)}')
