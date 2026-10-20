"""
Backend de base de données personnalisé pour Supabase REST API
Contourne les problèmes de connectivité PostgreSQL
"""
import os
from supabase import create_client, Client
from django.db.backends.postgresql import base
from django.conf import settings

class SupabaseRestClient:
    """Client REST pour Supabase qui remplace la connexion PostgreSQL"""
    
    def __init__(self):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_SERVICE_KEY')
        
        if not url or not key:
            raise Exception("SUPABASE_URL et SUPABASE_SERVICE_KEY requis dans .env")
            
        self.client: Client = create_client(url, key)
        
    def test_connection(self):
        """Test de la connexion Supabase"""
        try:
            # Simple test - récupère les tables publiques
            result = self.client.rpc('get_schema', {}).execute()
            return True
        except Exception as e:
            print(f"Erreur connexion Supabase: {e}")
            return False

# Instance globale du client
supabase_client = None

def get_supabase_client():
    """Récupère l'instance du client Supabase"""
    global supabase_client
    if supabase_client is None:
        supabase_client = SupabaseRestClient()
    return supabase_client