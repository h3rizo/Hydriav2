"""
Utilitaires pour la gestion des contrats employés
"""
from django.utils import timezone


def est_journalier(employe):
    """
    Vérifie si un employé est journalier (contrat actif de type 'journalier')

    Args:
        employe: Instance de Employe

    Returns:
        bool: True si journalier, False sinon
    """
    # Récupérer le contrat actif (sans date de fin ou fin dans le futur)
    contrat_actif = employe.contrats.filter(
        debut_contrat__lte=timezone.now().date()
    ).filter(
        fin_contrat__isnull=True
    ) | employe.contrats.filter(
        debut_contrat__lte=timezone.now().date(),
        fin_contrat__gte=timezone.now().date()
    )

    contrat = contrat_actif.order_by('-debut_contrat').first()

    if contrat:
        return contrat.type_contrat == 'journalier'

    return False


def est_salarie(employe):
    """
    Vérifie si un employé est salarié (non journalier)

    Inclut: temps_plein, temps_partiel, Mi-temps

    Args:
        employe: Instance de Employe

    Returns:
        bool: True si salarié, False si journalier ou sans contrat
    """
    return not est_journalier(employe)


def get_contrat_actif(employe):
    """
    Récupère le contrat actif d'un employé

    Args:
        employe: Instance de Employe

    Returns:
        Contrat ou None si aucun contrat actif
    """
    contrat_actif = employe.contrats.filter(
        debut_contrat__lte=timezone.now().date()
    ).filter(
        fin_contrat__isnull=True
    ) | employe.contrats.filter(
        debut_contrat__lte=timezone.now().date(),
        fin_contrat__gte=timezone.now().date()
    )

    return contrat_actif.order_by('-debut_contrat').first()
