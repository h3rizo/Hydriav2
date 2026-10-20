# Guide d'utilisation du Workflow Météo

## 📋 Vue d'ensemble

Ce workflow permet de récupérer automatiquement les données météorologiques (pluviométrie, température, humidité) pour les villages du projet Hydria et de les afficher en parallèle avec l'analyse de consommation d'eau.

## 🏗️ Architecture

### Composants créés

1. **Modèle DonneeMeteo** (`apps/geography/models.py`)
   - Stocke les données météo par village et par date
   - Champs : precipitation, temperature_min, temperature_max, humidite
   - Source API : Open-Meteo (gratuit, sans authentification)

2. **Tâches Celery** (`apps/geography/tasks.py`)
   - `recuperer_donnees_meteo()` : Tâche planifiée quotidienne (2h du matin)
   - `recuperer_donnees_meteo_village()` : Tâche pour un village spécifique

3. **API de consultation** (`apps/planning/views_analyse_consommation.py`)
   - `api_donnees_meteo_filtrees()` : Retourne les données filtrées pour l'année en cours
   - Respecte les mêmes filtres géographiques que l'analyse de consommation

4. **Interface utilisateur** (`templates/planning/analyse_consommation.html`)
   - Graphique Chart.js avec barres (précipitations) et courbes (températures)
   - Mise à jour automatique lors du changement de filtres

## 🚀 Installation et démarrage

### 1. Installer Redis (broker Celery)

**Windows - Option 1 : Memurai (recommandé)**
```bash
# Télécharger depuis https://www.memurai.com/get-memurai
# Ou utiliser Chocolatey :
choco install memurai-developer
```

**Windows - Option 2 : Redis via WSL**
```bash
wsl --install
wsl
sudo apt update
sudo apt install redis-server
sudo service redis-server start
```

**Linux/Mac**
```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# macOS (Homebrew)
brew install redis
brew services start redis
```

### 2. Configurer l'environnement (.env)

Ajouter ces variables dans votre fichier `.env` :

```env
# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 3. Démarrer Celery Worker

**Terminal 1 - Worker (exécute les tâches)**
```bash
cd backend
.venv\Scripts\activate  # Windows
# ou: source .venv/bin/activate  # Linux/Mac

celery -A hydria worker -l info
```

### 4. Démarrer Celery Beat (planificateur)

**Terminal 2 - Beat Scheduler (planifie les tâches)**
```bash
cd backend
.venv\Scripts\activate  # Windows

celery -A hydria beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### 5. Démarrer le serveur Django

**Terminal 3 - Django**
```bash
cd backend
.venv\Scripts\activate
python manage.py runserver
```

## 📊 Utilisation

### Accéder à l'interface

1. Naviguer vers : `http://localhost:8000/plannings/volumetrique/analyse-consommation/`
2. Utiliser les filtres (communes, ouvrages, types de points d'eau)
3. Le graphique météo se met à jour automatiquement avec les filtres

### Récupération automatique des données

- **Planification** : Tous les jours à 2h du matin (Madagascar time)
- **Villages concernés** : Tous les villages avec coordonnées GPS (latitude/longitude)
- **Données récupérées** : Veille (J-1) - données les plus récentes validées
- **Source API** : Open-Meteo Archive API (https://archive-api.open-meteo.com)

### Récupération manuelle

**Via Django Shell :**
```python
python manage.py shell

# Récupérer les données de tous les villages
from apps.geography.tasks import recuperer_donnees_meteo
result = recuperer_donnees_meteo()
print(result)

# Récupérer les données d'un village spécifique (30 derniers jours)
from apps.geography.tasks import recuperer_donnees_meteo_village
from apps.geography.models import Village
village = Village.objects.filter(latitude__isnull=False).first()
result = recuperer_donnees_meteo_village(str(village.id))
print(result)
```

**Via Celery (tâche asynchrone) :**
```python
from apps.geography.tasks import recuperer_donnees_meteo
task = recuperer_donnees_meteo.delay()
print(f"Tâche lancée : {task.id}")

# Vérifier le statut
from celery.result import AsyncResult
result = AsyncResult(task.id)
print(result.status)  # PENDING, SUCCESS, FAILURE
print(result.result)  # Résultat quand SUCCESS
```

## 🔧 Configuration avancée

### Modifier la fréquence de récupération

Éditer `backend/hydria/celery.py` :

```python
app.conf.beat_schedule = {
    'recuperer-donnees-meteo-quotidien': {
        'task': 'apps.geography.tasks.recuperer_donnees_meteo',
        'schedule': crontab(hour=2, minute=0),  # Tous les jours à 2h
        # Alternatives :
        # 'schedule': crontab(minute='*/30'),  # Toutes les 30 minutes (test)
        # 'schedule': crontab(hour=2, minute=0, day_of_week='monday'),  # Tous les lundis à 2h
    },
}
```

Redémarrer Celery Beat après modification.

### Ajouter des coordonnées GPS aux villages

```python
python manage.py shell

from apps.geography.models import Village

# Mettre à jour un village
village = Village.objects.get(nom_village="Ambanja")
village.latitude = -13.6833
village.longitude = 48.4500
village.save()
```

### Vérifier les données météo stockées

```python
python manage.py shell

from apps.geography.models import DonneeMeteo, Village
from datetime import date, timedelta

# Compter les données disponibles
print(f"Total mesures : {DonneeMeteo.objects.count()}")

# Données récentes (7 derniers jours)
depuis = date.today() - timedelta(days=7)
recentes = DonneeMeteo.objects.filter(date__gte=depuis).count()
print(f"Mesures récentes (7j) : {recentes}")

# Villages avec données
villages_ids = DonneeMeteo.objects.values_list('village_id', flat=True).distinct()
villages = Village.objects.filter(id__in=villages_ids)
print(f"Villages avec données : {villages.count()}")
for v in villages:
    nb = DonneeMeteo.objects.filter(village=v).count()
    print(f"  - {v.nom_village} : {nb} mesures")

# Dernière mesure
derniere = DonneeMeteo.objects.order_by('-date').first()
if derniere:
    print(f"\nDernière mesure : {derniere.village.nom_village} - {derniere.date}")
    print(f"  Précipitations : {derniere.precipitation} mm")
    print(f"  Température : {derniere.temperature_min}°C - {derniere.temperature_max}°C")
```

## 🐛 Dépannage

### Redis ne démarre pas

**Windows (Memurai) :**
```bash
# Vérifier le service
Get-Service Memurai

# Démarrer le service
Start-Service Memurai
```

**Linux/Mac :**
```bash
# Vérifier si Redis tourne
redis-cli ping  # Doit retourner "PONG"

# Démarrer Redis
sudo systemctl start redis  # Linux
brew services start redis    # macOS
```

### Celery ne se connecte pas à Redis

Vérifier le fichier `.env` :
```bash
# Doit contenir :
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

Tester la connexion Redis :
```bash
redis-cli
> ping
PONG
> exit
```

### Les données météo ne s'affichent pas

1. **Vérifier qu'il y a des données en base :**
```python
python manage.py shell
from apps.geography.models import DonneeMeteo
print(DonneeMeteo.objects.count())  # Doit être > 0
```

2. **Vérifier les villages avec GPS :**
```python
from apps.geography.models import Village
villages_gps = Village.objects.filter(latitude__isnull=False, longitude__isnull=False).exclude(latitude=0)
print(f"Villages avec GPS : {villages_gps.count()}")
```

3. **Tester l'API manuellement :**
```bash
# Dans le navigateur ou via curl :
http://localhost:8000/plannings/volumetrique/api/donnees-meteo/?annee=2025
```

### Les tâches Celery échouent

Consulter les logs :
```bash
# Worker logs (Terminal 1)
celery -A hydria worker -l debug

# Beat logs (Terminal 2)
celery -A hydria beat -l debug
```

Vérifier les tâches dans l'admin Django :
```
http://localhost:8000/admin/django_celery_beat/periodictask/
```

## 📈 Améliorations futures possibles

1. **Backfill historique** : Script pour récupérer les données des années précédentes
2. **Alertes météo** : Notifications quand précipitations > seuil
3. **Corrélation automatique** : Analyse statistique consommation vs pluviométrie
4. **Prévisions météo** : Intégrer l'API de prévisions Open-Meteo
5. **Export Excel** : Inclure les données météo dans les exports
6. **Cache Redis** : Mettre en cache les données météo pour améliorer les performances

## 📚 Ressources

- **Open-Meteo API** : https://open-meteo.com/en/docs/archive-api
- **Celery Documentation** : https://docs.celeryproject.org/
- **Django Celery Beat** : https://django-celery-beat.readthedocs.io/
- **Chart.js** : https://www.chartjs.org/docs/

## ✅ Checklist de mise en production

- [ ] Redis installé et configuré en service
- [ ] Variables d'environnement configurées
- [ ] Celery Worker configuré en service (systemd/supervisord)
- [ ] Celery Beat configuré en service
- [ ] Coordonnées GPS renseignées pour tous les villages
- [ ] Backfill des données historiques effectué
- [ ] Monitoring des tâches Celery en place
- [ ] Logs configurés et rotation en place
- [ ] Alertes configurées pour échecs de tâches

---

**Créé le :** 9 novembre 2025
**Dernière mise à jour :** 9 novembre 2025
**Auteur :** Claude Code (continuation session précédente)