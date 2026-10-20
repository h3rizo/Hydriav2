import os
from supabase import create_client, Client
from decouple import config

# Récupération des variables d'environnement via python-decouple
# Assurez-vous que votre fichier .env contient SUPABASE_URL et SUPABASE_SERVICE_KEY
SUPABASE_URL = config('SUPABASE_URL', default=None)
SUPABASE_KEY = config('SUPABASE_SERVICE_KEY', default=None)

supabase_client: Client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Test simple pour vérifier la connexion en listant les buckets
        supabase_client.storage.list_buckets()
        print("✅ Connexion à Supabase Storage réussie.")
    except Exception as e:
        print(f"⚠️ Erreur lors de la connexion à Supabase: {e}")
        supabase_client = None
else:
    print("⚠️ Avertissement: SUPABASE_URL et SUPABASE_SERVICE_KEY ne sont pas configurés. L'intégration avec Supabase Storage est désactivée.")