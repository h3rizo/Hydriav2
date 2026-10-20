"""Rappels de pointage GPS : uniquement pour les employés qui ont déclaré le créneau (prevu_*)."""
import logging

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

from . import services_pointage as svc
from .models import Planning
from .models_pointage import PointageGPS

logger = logging.getLogger(__name__)


def envoyer_rappels_creneau(type_creneau: str) -> dict:
    """Envoie le rappel du créneau `type_creneau` (matin/aprem/nuit) aux employés concernés."""
    if type_creneau not in svc.CRENEAU_PAR_TYPE:
        raise ValueError(f"Créneau inconnu : {type_creneau}")
    _t, debut, fin, champ, label = svc.CRENEAU_PAR_TYPE[type_creneau]

    jour = timezone.now().astimezone(svc.tz_madagascar).date()
    debut_j, fin_j = svc._bornes_jour(jour)
    plannings = (
        Planning.objects.filter(date__gte=debut_j, date__lt=fin_j, **{champ: True})
        .exclude(statut='annule')
        # Pas de rappel pour un ouvrage sans pointage (TypeOuvrage.existe=False).
        .exclude(ouvrage__type_ouvrage__existe=False)
        .select_related('employe__user')
    )
    deja = set(
        PointageGPS.objects.filter(
            planning__in=plannings, type_pointage=type_creneau,
            statut_validation=PointageGPS.STATUT_VALIDE,
        ).values_list('planning_id', flat=True)
    )

    # Un seul rappel par employé même s'il a plusieurs plannings ce jour-là.
    a_rappeler = {}
    for pl in plannings:
        if pl.employe_id and pl.id not in deja:
            a_rappeler.setdefault(pl.employe_id, pl.employe)

    titre = f"Pointage {label.lower()}"
    corps = f"N'oubliez pas de pointer votre position entre {debut:%Hh%M} et {fin:%Hh%M}."
    envoyes = 0
    for employe in a_rappeler.values():
        try:
            from apps.messaging.push import send_push_to_employe
            from apps.messaging.models import DeviceToken

            a_un_appareil = DeviceToken.objects.filter(employe=employe, actif=True).exists()
            if a_un_appareil:
                send_push_to_employe(employe, titre, corps, data={'type': 'pointage', 'creneau': type_creneau})
            else:
                email = getattr(getattr(employe, 'user', None), 'email', None)
                if email:
                    send_mail(titre, corps, None, [email], fail_silently=True)
            envoyes += 1
        except Exception:  # un échec ne doit jamais bloquer les autres employés
            logger.exception("Rappel pointage échoué pour employe=%s", employe.id)
    return {'creneau': type_creneau, 'employes_rappeles': envoyes}


@shared_task(name='apps.planning.tasks.rappel_pointage_matin')
def rappel_pointage_matin():
    return envoyer_rappels_creneau(PointageGPS.TYPE_MATIN)


@shared_task(name='apps.planning.tasks.rappel_pointage_aprem')
def rappel_pointage_aprem():
    return envoyer_rappels_creneau(PointageGPS.TYPE_APREM)


@shared_task(name='apps.planning.tasks.rappel_pointage_nuit')
def rappel_pointage_nuit():
    return envoyer_rappels_creneau(PointageGPS.TYPE_NUIT)
