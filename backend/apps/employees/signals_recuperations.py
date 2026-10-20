"""
Signals pour la gestion automatique des récupérations dans le Planning
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta, datetime
import pytz

from .models_recuperations import Recuperation
from apps.planning.models import Planning, Activite


@receiver(post_save, sender=Recuperation)
def creer_planning_recuperation_validee(sender, instance, created, **kwargs):
    """
    Créer automatiquement les entrées Planning quand une récupération est validée par le directeur

    Règles:
    - Seulement quand statut = 'validee_directeur'
    - Créer un Planning par jour de récupération
    - Activité = 'Récupération'
    - validé = True (pas besoin de revalidation)
    - Marquer la récupération comme 'utilisee'
    """
    # Ne traiter que les récupérations validées par le directeur
    if instance.statut != 'validee_directeur':
        return

    # Vérifier qu'on n'a pas déjà créé les plannings
    if hasattr(instance, '_plannings_crees') and instance._plannings_crees:
        return

    # Vérifier qu'il y a bien des dates de début/fin
    if not instance.date_debut_recup or not instance.date_fin_recup:
        print(f"ERREUR: Récupération {instance.id} sans dates de début/fin")
        return

    # Récupérer l'activité "Récupération"
    try:
        activite_recup = Activite.objects.get(nom="Récupération")
    except Activite.DoesNotExist:
        print("ERREUR: Activité 'Récupération' non trouvée")
        return

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Parcourir tous les jours de récupération
    date_courante = instance.date_debut_recup
    plannings_crees = []

    while date_courante <= instance.date_fin_recup:
        # Créer datetime aware pour minuit à Madagascar
        date_planning = timezone.make_aware(
            datetime.combine(date_courante, datetime.min.time()),
            tz_madagascar
        )

        # Vérifier qu'il n'existe pas déjà un planning pour cette date
        existing = Planning.objects.filter(
            employe=instance.employe,
            date__date=date_courante
        ).first()

        if not existing:
            # Créer le planning
            planning = Planning.objects.create(
                employe=instance.employe,
                date=date_planning,
                activite=activite_recup,
                estvalide=True,  # Validé automatiquement
            )
            plannings_crees.append(planning)

        # Jour suivant
        date_courante += timedelta(days=1)

    # Marquer la récupération comme utilisée
    if plannings_crees:
        instance.statut = 'utilisee'
        instance._plannings_crees = True  # Éviter boucle infinie
        instance.save(update_fields=['statut'])

    print(f"✅ {len(plannings_crees)} planning(s) créé(s) pour la récupération de {instance.employe.nom_complet}")
