from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
credentials = service_account.Credentials.from_service_account_file(
    '/home/soakoja/hydria/backend/credentials/google_drive_service_account.json',
    scopes=SCOPES
)

service = build('drive', 'v3', credentials=credentials)
folder_id = '1reDoVBSODfJGGo3odpvUaGzGYz9Mw-Ru'

try:
    folder = service.files().get(
        fileId=folder_id,
        fields='id, name, mimeType'
    ).execute()

    print('[OK] Acces au dossier reussi!')
    print('ID:', folder['id'])
    print('Nom:', folder['name'])
    print('Type:', folder['mimeType'])

    results = service.files().list(
        q=f"'{folder_id}' in parents",
        pageSize=10,
        fields='files(id, name, mimeType)'
    ).execute()

    files = results.get('files', [])
    print(f'\nFichiers trouves: {len(files)}')
    for f in files[:5]:
        print(f"- {f['name']}")

except Exception as e:
    print('[ERROR]', str(e))
