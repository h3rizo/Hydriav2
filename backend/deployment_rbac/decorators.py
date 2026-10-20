# -*- coding: utf-8 -*-
"""
Decorateurs de securite pour les vues bases sur les permissions de poste.

Ces decorateurs permettent de proteger les vues en verifiant que l'utilisateur
a les permissions appropriees basees sur son poste.
"""
from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib import messages
from .permissions import (
    POSTES_AUTORISES_ADMIN_COMPTA_MESSAGE,
    has_admin_access,
    has_compta_access,
    has_admin_compta_access,
)


def admin_required(view_func):
    """
    Decorateur pour restreindre l'acces aux vues d'administration.

    Verifie que l'utilisateur a les permissions d'administration via has_admin_access().
    Si l'utilisateur n'a pas les permissions, retourne une erreur 403 Forbidden.

    Usage:
        @admin_required
        def ma_vue_admin(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not has_admin_access(request.user):
            messages.error(
                request,
                "Acces refuse. Cette fonctionnalite est reservee aux postes d'administration."
            )
            return HttpResponseForbidden(
                "<h1>Acces interdit</h1>"
                "<p>Vous n'avez pas les permissions necessaires pour acceder a cette page.</p>"
                "<p>Cette fonctionnalite est reservee aux postes : "
                f"{POSTES_AUTORISES_ADMIN_COMPTA_MESSAGE}.</p>"
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def compta_required(view_func):
    """
    Decorateur pour restreindre l'acces aux vues de comptabilite.

    Verifie que l'utilisateur a les permissions de comptabilite via has_compta_access().
    Si l'utilisateur n'a pas les permissions, retourne une erreur 403 Forbidden.

    Usage:
        @compta_required
        def ma_vue_compta(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not has_compta_access(request.user):
            messages.error(
                request,
                "Acces refuse. Cette fonctionnalite est reservee aux postes de comptabilite."
            )
            return HttpResponseForbidden(
                "<h1>Acces interdit</h1>"
                "<p>Vous n'avez pas les permissions necessaires pour acceder a cette page.</p>"
                "<p>Cette fonctionnalite est reservee aux postes : "
                f"{POSTES_AUTORISES_ADMIN_COMPTA_MESSAGE}.</p>"
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_compta_required(view_func):
    """
    Decorateur pour restreindre l'acces aux vues necessitant a la fois
    les permissions d'administration ET de comptabilite.

    Verifie que l'utilisateur a les permissions via has_admin_compta_access().
    Si l'utilisateur n'a pas les permissions, retourne une erreur 403 Forbidden.

    Usage:
        @admin_compta_required
        def ma_vue_admin_compta(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not has_admin_compta_access(request.user):
            messages.error(
                request,
                "Acces refuse. Cette fonctionnalite est reservee aux postes d'administration et comptabilite."
            )
            return HttpResponseForbidden(
                "<h1>Acces interdit</h1>"
                "<p>Vous n'avez pas les permissions necessaires pour acceder a cette page.</p>"
                "<p>Cette fonctionnalite est reservee aux postes : "
                f"{POSTES_AUTORISES_ADMIN_COMPTA_MESSAGE}.</p>"
            )
        return view_func(request, *args, **kwargs)
    return wrapper
