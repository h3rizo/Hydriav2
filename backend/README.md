# Hydria Backend - Django API

## Configuration
API Django avec connexion Supabase PostgreSQL pour la gestion des activités d'approvisionnement en eau à Madagascar.

## Commandes

### Activer l'environnement virtuel
```powershell
# PowerShell (recommandé)
.\venv\Scripts\Activate.ps1

# Command Prompt
venv\Scripts\activate.bat

# Git Bash
source venv/Scripts/activate
```

### Installation et lancement
```bash
# Installer dépendances
pip install -r requirements.txt

# Migrations
python manage.py migrate

# Lancer le serveur
python manage.py runserver
```

## Structure
- `hydria/` - Configuration Django principale
- `apps/` - Applications Django modulaires
- `static/` - Fichiers statiques
- `templates/` - Templates Django
- `media/` - Fichiers media uploadés