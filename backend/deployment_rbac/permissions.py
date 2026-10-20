# -*- coding: utf-8 -*-
"""
Module de gestion des permissions basees sur les postes.

Ce module fournit des fonctions pour verifier si un utilisateur a acces
aux menus Administration et Comptabilite en fonction de son poste.
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.db.models import Q
from unicodedata import normalize as _unicodedata_normalize


def _normalize_poste_name(name: str) -> str:
    """Normalise le nom du poste pour comparer sans accent ni casse."""
    if not name:
        return ''
    normalized = str(name).replace('\u2019', "'").replace('`', "'")
    normalized = _unicodedata_normalize('NFKD', normalized)
    ascii_only = normalized.encode('ascii', errors='ignore').decode('ascii')
    return ' '.join(ascii_only.lower().strip().split())


# Postes autorises a voir les menus Administration et Comptabilite
POSTES_AUTORISES_ADMIN_COMPTA = {
    'Directeur',
    'Directeur adjoint',
    'Assistant(e) admin',
    'Assistant admin',
    'Assistante admin',
    'RAF',
    'Responsable administratif et financier',
    'Chef secteur',
    "Charge d'appui",
}

POSTES_AUTORISES_NORMALIZED = {
    _normalize_poste_name(poste) for poste in POSTES_AUTORISES_ADMIN_COMPTA
}

POSTE_KEYWORDS_ADMIN_COMPTA = (
    'directeur',
    'directeur adjoint',
    'assistant admin',
    'assistante admin',
    'raf',
    'responsable administratif et financier',
    'chef secteur',
    "charge d'appui",
)

POSTES_AUTORISES_ADMIN_COMPTA_MESSAGE = ", ".join([
    'Directeur',
    'Directeur adjoint',
    'Assistant(e) admin',
    'Assistant admin',
    'Assistante admin',
    'RAF',
    'Responsable administratif et financier',
    'Chef secteur',
    "Charge d'appui",
])


def has_admin_compta_access(user):
    """
    Verifie si l'utilisateur a acces aux menus Administration et Comptabilite.

    Args:
        user: L'objet User Django

    Returns:
        bool: True si l'utilisateur a acces, False sinon

    Regles:
        - Les superusers ont toujours acces
        - L'utilisateur doit avoir un employe lie (user.employe)
        - L'employe doit avoir un poste
        - Le nom du poste doit correspondre a un des postes autorises
        - La verification est insensible a la casse
        - Normalise le nom du poste (correspondance accent/casse insensible)
    """
    # Les superusers ont toujours acces
    if user.is_superuser:
        return True

    # Verifier si l'utilisateur a un employe lie
    if not hasattr(user, 'employe') or not user.employe:
        return False

    # Verifier si l'employe a un poste
    if not user.employe.poste:
        return False

    nom_poste = user.employe.poste.nom_poste
    nom_poste_normalized = _normalize_poste_name(nom_poste)
    if nom_poste_normalized in POSTES_AUTORISES_NORMALIZED:
        return True
    return any(keyword in nom_poste_normalized for keyword in POSTE_KEYWORDS_ADMIN_COMPTA)


def has_admin_access(user):
    """
    Verifie si l'utilisateur a acces au menu Administration.

    Args:
        user: L'objet User Django

    Returns:
        bool: True si l'utilisateur a acces, False sinon

    Note:
        Actuellement utilise la meme logique que has_admin_compta_access.
        Cette fonction est separee pour permettre une granularite future.
    """
    return has_admin_compta_access(user)


def has_compta_access(user):
    """
    Verifie si l'utilisateur a acces au menu Comptabilite.

    Args:
        user: L'objet User Django

    Returns:
        bool: True si l'utilisateur a acces, False sinon

    Note:
        Actuellement utilise la meme logique que has_admin_compta_access.
        Cette fonction est separee pour permettre une granularite future.
    """
    return has_admin_compta_access(user)


def get_user_poste_name(user):
    """
    Retourne le nom du poste de l'utilisateur.

    Args:
        user: L'objet User Django

    Returns:
        str ou None: Le nom du poste ou None si non disponible
    """
    if hasattr(user, 'employe') and user.employe and user.employe.poste:
        return user.employe.poste.nom_poste
    return None


def get_user_poste(user):
    """Alias pour compatibilite."""
    return get_user_poste_name(user)


def is_directeur_poste(user):
    """Retourne True si l'utilisateur occupe le poste Directeur."""
    poste = get_user_poste_name(user)
    return _normalize_poste_name(poste) == 'directeur'


def employe_required(view_func):
    """
    Decorateur pour restreindre l'acces aux vues aux utilisateurs employes uniquement.

    Ce decorateur verifie que l'utilisateur est authentifie et a un employe lie.
    Si c'est le cas, il attache l'employe a la requete (request.employe) pour
    un acces facile dans la vue.

    Args:
        view_func: La fonction de vue a proteger

    Returns:
        function: La fonction enveloppee avec verification d'employe

    Comportement:
        - Si utilisateur non authentifie: redirige vers login
        - Si utilisateur sans employe lie: affiche message d'erreur et redirige vers home
        - Si utilisateur a un employe: attache request.employe et execute la vue
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Verifier si l'utilisateur est authentifie
        if not request.user.is_authenticated:
            messages.warning(request, "Vous devez etre connecte pour acceder a cette page.")
            return redirect('login')

        # Verifier si l'utilisateur a un employe lie
        if not hasattr(request.user, 'employe') or not request.user.employe:
            messages.error(
                request,
                "Acces refuse. Votre compte utilisateur n'est pas lie a un employe."
            )
            return redirect('home')

        # Attacher l'employe a la requete pour acces facile dans la vue
        request.employe = request.user.employe

        # Executer la vue
        return view_func(request, *args, **kwargs)

    return wrapper


def filter_queryset_by_permissions(queryset, user):
    """
    Filtre un queryset en fonction des permissions de l'utilisateur.

    Cette fonction applique des filtres basés sur l'organisation et les permissions
    de l'utilisateur pour restreindre les donnees visibles.

    Args:
        queryset: Le queryset Django a filtrer
        user: L'objet User Django

    Returns:
        QuerySet: Le queryset filtre selon les permissions de l'utilisateur

    Regles de filtrage:
        - Les superusers voient tout (pas de filtre)
        - Les utilisateurs sans employe ne voient rien
        - Les utilisateurs avec employe voient les donnees de leur organisation
        - Supporte le filtrage sur: Ouvrage, PointEau, Parcelle

    Exemple d'utilisation:
        ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
        points_eau = filter_queryset_by_permissions(PointEau.objects.all(), request.user)
    """
    # Les superusers ont acces a tout
    if user.is_superuser:
        return queryset

    # Verifier si l'utilisateur a un employe lie
    if not hasattr(user, 'employe') or not user.employe:
        # Retourner un queryset vide si pas d'employe
        return queryset.none()

    employe = user.employe

    # Verifier si l'employe a une base (organisation)
    if not employe.base:
        # Pas de base = pas de filtre possible, retourner tout
        return queryset

    organisation = employe.base.organisation

    # Determiner le nom du modele pour appliquer le bon filtre
    model_name = queryset.model.__name__

    # Filtrer selon le type de modele
    if model_name == 'Ouvrage':
        # Filtrer les ouvrages par organisation via la base
        return queryset.filter(
            Q(modalites_gestion__gestionnaire=organisation) |
            Q(modalites_gestion__gestionnaire__isnull=True)
        ).distinct()

    elif model_name == 'PointEau':
        # Filtrer les points d'eau par organisation via l'ouvrage
        return queryset.filter(
            Q(ouvrage__modalites_gestion__gestionnaire=organisation) |
            Q(ouvrage__modalites_gestion__gestionnaire__isnull=True)
        ).distinct()

    elif model_name == 'Parcelle':
        # Filtrer les parcelles par organisation via les points d'eau
        return queryset.filter(
            Q(pointeau__ouvrage__modalites_gestion__gestionnaire=organisation) |
            Q(pointeau__ouvrage__modalites_gestion__gestionnaire__isnull=True)
        ).distinct()

    else:
        # Pour les autres modeles, retourner le queryset sans filtre
        # (peut etre etendu au besoin)
        return queryset
