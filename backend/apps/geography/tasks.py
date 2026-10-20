"""
Tâches Celery pour récupérer les données météorologiques via Open-Meteo API
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal
import requests
import logging

from .models import Village, DonneeMeteo

logger = logging.getLogger(__name__)


@shared_task(name='apps.geography.tasks.recuperer_donnees_meteo')
def recuperer_donnees_meteo():
    """
    Tâche Celery pour récupérer les données météo de tous les villages avec coordonnées GPS
    Utilise l'API Open-Meteo (gratuite, pas de clé API requise)
    """
    logger.info("🌤️  Début de la récupération des données météo")

    # Récupérer tous les villages avec coordonnées GPS
    villages = Village.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).exclude(latitude=0, longitude=0)

    if not villages.exists():
        logger.warning("Aucun village avec coordonnées GPS trouvé")
        return {
            'success': False,
            'message': 'Aucun village avec coordonnées GPS'
        }

    # Dates à récupérer : hier et aujourd'hui (Open-Meteo a un délai de 1 jour pour les données historiques)
    aujourd_hui = date.today()
    hier = aujourd_hui - timedelta(days=1)

    villages_traites = 0
    donnees_creees = 0
    erreurs = 0

    for village in villages:
        try:
            # Appel à l'API Open-Meteo
            # Documentation: https://open-meteo.com/en/docs
            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {
                'latitude': float(village.latitude),
                'longitude': float(village.longitude),
                'start_date': hier.strftime('%Y-%m-%d'),
                'end_date': hier.strftime('%Y-%m-%d'),  # Seulement hier (données validées)
                'daily': 'precipitation_sum,temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean',
                'timezone': 'Indian/Antananarivo'
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Parser les données
            if 'daily' in data and data['daily']:
                daily = data['daily']
                dates = daily.get('time', [])

                for i, date_str in enumerate(dates):
                    date_obj = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()

                    # Créer ou mettre à jour la donnée météo
                    donnee, created = DonneeMeteo.objects.update_or_create(
                        village=village,
                        date=date_obj,
                        defaults={
                            'precipitation': Decimal(str(daily.get('precipitation_sum', [])[i])) if daily.get('precipitation_sum') and len(daily.get('precipitation_sum')) > i and daily.get('precipitation_sum')[i] is not None else None,
                            'temperature_max': Decimal(str(daily.get('temperature_2m_max', [])[i])) if daily.get('temperature_2m_max') and len(daily.get('temperature_2m_max')) > i and daily.get('temperature_2m_max')[i] is not None else None,
                            'temperature_min': Decimal(str(daily.get('temperature_2m_min', [])[i])) if daily.get('temperature_2m_min') and len(daily.get('temperature_2m_min')) > i and daily.get('temperature_2m_min')[i] is not None else None,
                            'humidite': Decimal(str(daily.get('relative_humidity_2m_mean', [])[i])) if daily.get('relative_humidity_2m_mean') and len(daily.get('relative_humidity_2m_mean')) > i and daily.get('relative_humidity_2m_mean')[i] is not None else None,
                            'source_api': 'open-meteo'
                        }
                    )

                    if created:
                        donnees_creees += 1

            villages_traites += 1
            logger.info(f"✅ Village {village.nom_village} traité ({villages_traites}/{villages.count()})")

        except requests.RequestException as e:
            logger.error(f"❌ Erreur API pour {village.nom_village}: {e}")
            erreurs += 1
        except Exception as e:
            logger.error(f"❌ Erreur inattendue pour {village.nom_village}: {e}")
            erreurs += 1

    logger.info(f"🏁 Récupération terminée: {villages_traites} villages, {donnees_creees} données créées, {erreurs} erreurs")

    return {
        'success': True,
        'villages_traites': villages_traites,
        'donnees_creees': donnees_creees,
        'erreurs': erreurs
    }


@shared_task(name='apps.geography.tasks.recuperer_donnees_meteo_village')
def recuperer_donnees_meteo_village(village_id, start_date=None, end_date=None):
    """
    Tâche pour récupérer les données météo d'un village spécifique sur une période

    Args:
        village_id: UUID du village
        start_date: Date de début (format YYYY-MM-DD), par défaut: il y a 30 jours
        end_date: Date de fin (format YYYY-MM-DD), par défaut: hier
    """
    try:
        village = Village.objects.get(id=village_id)

        if not village.latitude or not village.longitude:
            return {
                'success': False,
                'message': f'Village {village.nom_village} sans coordonnées GPS'
            }

        # Dates par défaut
        if not end_date:
            end_date = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        if not start_date:
            start_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')

        # Appel API Open-Meteo
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            'latitude': float(village.latitude),
            'longitude': float(village.longitude),
            'start_date': start_date,
            'end_date': end_date,
            'daily': 'precipitation_sum,temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean',
            'timezone': 'Indian/Antananarivo'
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        donnees_creees = 0

        if 'daily' in data and data['daily']:
            daily = data['daily']
            dates = daily.get('time', [])

            for i, date_str in enumerate(dates):
                date_obj = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()

                donnee, created = DonneeMeteo.objects.update_or_create(
                    village=village,
                    date=date_obj,
                    defaults={
                        'precipitation': Decimal(str(daily.get('precipitation_sum', [])[i])) if daily.get('precipitation_sum') and len(daily.get('precipitation_sum')) > i and daily.get('precipitation_sum')[i] is not None else None,
                        'temperature_max': Decimal(str(daily.get('temperature_2m_max', [])[i])) if daily.get('temperature_2m_max') and len(daily.get('temperature_2m_max')) > i and daily.get('temperature_2m_max')[i] is not None else None,
                        'temperature_min': Decimal(str(daily.get('temperature_2m_min', [])[i])) if daily.get('temperature_2m_min') and len(daily.get('temperature_2m_min')) > i and daily.get('temperature_2m_min')[i] is not None else None,
                        'humidite': Decimal(str(daily.get('relative_humidity_2m_mean', [])[i])) if daily.get('relative_humidity_2m_mean') and len(daily.get('relative_humidity_2m_mean')) > i and daily.get('relative_humidity_2m_mean')[i] is not None else None,
                        'source_api': 'open-meteo'
                    }
                )

                if created:
                    donnees_creees += 1

        logger.info(f"✅ Village {village.nom_village}: {donnees_creees} données météo récupérées")

        return {
            'success': True,
            'village': village.nom_village,
            'donnees_creees': donnees_creees
        }

    except Village.DoesNotExist:
        return {
            'success': False,
            'message': f'Village {village_id} introuvable'
        }
    except Exception as e:
        logger.error(f"❌ Erreur récupération météo village {village_id}: {e}")
        return {
            'success': False,
            'message': str(e)
        }
