"""
Fonctions helper pour la gestion des différents types d'utilisateurs
"""

def get_user_type(user):
    """
    Retourne le type d'utilisateur : 'client', 'employe', 'candidat', ou 'admin'

    Args:
        user: Instance de django.contrib.auth.models.User

    Returns:
        str: 'client', 'employe', 'candidat', ou 'admin'
    """
    if hasattr(user, 'client') and user.client:
        return 'client'
    elif hasattr(user, 'employe') and user.employe:
        return 'employe'
    elif hasattr(user, 'candidat') and user.candidat:
        return 'candidat'
    elif user.is_staff or user.is_superuser:
        return 'admin'
    return None


def is_client(user):
    """Vérifie si l'utilisateur est un client"""
    return get_user_type(user) == 'client'


def is_employe(user):
    """Vérifie si l'utilisateur est un employé"""
    return get_user_type(user) == 'employe'


def is_admin(user):
    """Vérifie si l'utilisateur est un administrateur"""
    return get_user_type(user) == 'admin'


def is_candidat(user):
    """Verifie si l'utilisateur est un candidat"""
    return get_user_type(user) == 'candidat'


def get_user_profile(user):
    """
    Retourne le profil associé à l'utilisateur (Client ou Employe)

    Returns:
        ClientUser ou Employe ou None
    """
    if hasattr(user, 'client') and user.client:
        return user.client
    elif hasattr(user, 'employe') and user.employe:
        return user.employe
    elif hasattr(user, 'candidat') and user.candidat:
        return user.candidat
    return None
