"""
Configuration Celery pour le projet Hydria
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

app = Celery('hydria')

# Configuration depuis Django settings avec le préfixe CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscover tasks dans tous les modules tasks.py des apps Django
app.autodiscover_tasks()

# Configuration du scheduler Celery Beat
app.conf.beat_schedule = {
    'recuperer-donnees-meteo-quotidien': {
        'task': 'apps.geography.tasks.recuperer_donnees_meteo',
        'schedule': crontab(hour=2, minute=0),  # Tous les jours à 2h du matin
        # Pour test : crontab(minute='*/30'),  # Toutes les 30 minutes
    },
    # Rappels de pointage GPS : 10 min avant l'ouverture de chaque créneau
    # (10h, 15h, 19h), seulement pour les créneaux déclarés prévus.
    'rappel-pointage-matin': {
        'task': 'apps.planning.tasks.rappel_pointage_matin',
        'schedule': crontab(hour=9, minute=50),
    },
    'rappel-pointage-aprem': {
        'task': 'apps.planning.tasks.rappel_pointage_aprem',
        'schedule': crontab(hour=14, minute=50),
    },
    'rappel-pointage-nuit': {
        'task': 'apps.planning.tasks.rappel_pointage_nuit',
        'schedule': crontab(hour=18, minute=50),
    },
    'envoyer-relances-situations-attention-mensuel': {
        'task': 'apps.messaging.tasks.envoyer_relances_situations_attention_mensuelles',
        'schedule': crontab(day_of_month='1', hour=6, minute=0),  # Le 1er de chaque mois à 6h
        # Remplace l'ancienne entree 'envoyer-relances-factures-non-pointees-mensuel'
        # (paiements seuls) : couvre desormais paiements + reparations echues,
        # regroupes en un seul email par destinataire. L'ancienne tache reste
        # definie dans apps/messaging/tasks.py, appelable manuellement pour
        # rattrapage isole.
        # NOTE : sans effet reel tant que django_celery_beat reste commente
        # dans INSTALLED_APPS (hydria/settings.py) - incoherence preexistante,
        # hors perimetre de cette modification.
    },
}

app.conf.timezone = 'Indian/Antananarivo'


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
