from .settings import *

# Base de données locale pour développement
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_local.sqlite3',
    }
}

# Pas besoin de Supabase en local
SUPABASE_URL = ''
SUPABASE_SERVICE_KEY = ''

print("Utilisation de la base SQLite locale pour developpement")