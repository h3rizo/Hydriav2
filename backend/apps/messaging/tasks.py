"""
Taches Celery de l'app messaging.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='apps.messaging.tasks.envoyer_relances_factures_non_pointees_mensuelles')
def envoyer_relances_factures_non_pointees_mensuelles():
    """
    Tache mensuelle (paiements seuls, conservee pour rattrapage/diagnostic
    isole) : envoie le recapitulatif des factures non pointees a chaque
    responsable d'ouvrage actif (EmployeOuvrages.recevoir_alertes=True),
    pour le mois qui vient de se terminer.

    N'est plus la tache appelee automatiquement par le beat_schedule (voir
    hydria/celery.py) - remplacee par
    envoyer_relances_situations_attention_mensuelles ci-dessous. Reste
    appelable manuellement (Celery task shell) en cas de besoin de
    rattrapage cible paiements-only.
    """
    from .monthly_billing_mailer import envoyer_toutes_les_relances

    logger.info("Debut envoi relances mensuelles factures non pointees")
    resultat = envoyer_toutes_les_relances()

    logger.info(
        "Fin envoi relances mensuelles (%s/%s) : %s responsables, %s envoyes, "
        "%s echecs, %s email manquant, %s facture(s) sans responsable",
        resultat['mois'], resultat['annee'], resultat['nb_responsables'],
        resultat['nb_envoyes'], resultat['nb_echecs'], resultat['nb_email_manquant'],
        resultat['factures_sans_responsable'],
    )
    return {
        'annee': resultat['annee'],
        'mois': resultat['mois'],
        'nb_responsables': resultat['nb_responsables'],
        'nb_envoyes': resultat['nb_envoyes'],
        'nb_echecs': resultat['nb_echecs'],
        'nb_email_manquant': resultat['nb_email_manquant'],
        'factures_sans_responsable': resultat['factures_sans_responsable'],
    }


@shared_task(name='apps.messaging.tasks.envoyer_relances_situations_attention_mensuelles')
def envoyer_relances_situations_attention_mensuelles():
    """
    Tache mensuelle combinee : envoie le recapitulatif des paiements non
    pointes ET des reparations echues a chaque destinataire concerne
    (responsable direct d'ouvrage ou superieur hierarchique), regroupe par
    ouvrage, un seul email par destinataire. Declenchee le 1er de chaque
    mois (voir hydria/celery.py, entree
    'envoyer-relances-situations-attention-mensuel').
    """
    from .relance_mailer_combine import envoyer_toutes_les_relances_combinees

    logger.info("Debut envoi relances mensuelles situations a traiter (combinees)")
    resultat = envoyer_toutes_les_relances_combinees()

    logger.info(
        "Fin envoi relances mensuelles combinees (%s/%s) : %s destinataires, %s envoyes, "
        "%s echecs, %s email manquant, %s reparation(s) echue(s), %s facture(s) sans responsable",
        resultat['mois'], resultat['annee'], resultat['nb_destinataires'],
        resultat['nb_envoyes'], resultat['nb_echecs'], resultat['nb_email_manquant'],
        resultat['nb_reparations_echues'], resultat['factures_sans_responsable'],
    )
    return {
        'annee': resultat['annee'],
        'mois': resultat['mois'],
        'nb_destinataires': resultat['nb_destinataires'],
        'nb_envoyes': resultat['nb_envoyes'],
        'nb_echecs': resultat['nb_echecs'],
        'nb_email_manquant': resultat['nb_email_manquant'],
        'nb_reparations_echues': resultat['nb_reparations_echues'],
        'factures_sans_responsable': resultat['factures_sans_responsable'],
    }
