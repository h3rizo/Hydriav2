from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.sessions.models import Session
from django.utils import timezone
from .models import PositionGPSEmploye, Employe


@receiver(post_save, sender=Employe)
def stamp_acces_stade_autonomie(sender, instance, created, raw=False, **kwargs):
    """
    Horodate automatiquement le passage d'un employe sur le stade pivot
    (StadeAutonomie.declenche_anciennete) ou un stade superieur, en creant une
    entree HistoriqueStadeAutonomie si aucune n'existe encore pour ce stade.

    Idempotent : ne fait rien si l'entree existe deja (donc pas de doublon sur
    les imports en masse). La date retenue est la date du jour : pour un
    historique reel anterieur, corriger la date via l'admin ou une commande de
    backfill.
    """
    if raw or not instance.stade_autonomie_actuel_id:
        return

    try:
        pivot = instance.stade_autonomie_pivot
        if pivot is None:
            return
        stade_actuel = instance.stade_autonomie_actuel
        if stade_actuel is None or stade_actuel.ordre < pivot.ordre:
            return

        from .models_autonomie import HistoriqueStadeAutonomie
        HistoriqueStadeAutonomie.objects.get_or_create(
            employe=instance,
            stade_id=instance.stade_autonomie_actuel_id,
            defaults={
                'date_effet': timezone.now().date(),
                'source': 'auto',
            },
        )
    except Exception:
        # Ne jamais bloquer l'enregistrement d'un employe pour cet effet de bord.
        pass


@receiver(user_logged_in)
def capture_gps_on_login(sender, request, user, **kwargs):
    """
    Signal qui se déclenche lors de la connexion d'un utilisateur.
    La position GPS sera capturée via JavaScript côté client et envoyée à l'API.
    Ce signal prépare simplement la session pour recevoir les données GPS.
    """
    # Marquer dans la session qu'on attend des données GPS
    if hasattr(user, 'employe') and user.employe:
        request.session['awaiting_gps'] = True
        request.session['employe_id'] = str(user.employe.id)


# Import des autres signals
from . import signals_conges  # noqa: E402, F401
from . import signals_recuperations  # noqa: E402, F401
