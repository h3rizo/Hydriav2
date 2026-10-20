# -*- coding: utf-8 -*-
"""
Module de gestion des permissions basees sur les postes.

Ce module fournit des fonctions pour verifier si un utilisateur a acces
aux menus Administration et Comptabilite en fonction de son poste.
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from django.contrib.auth.models import Group
from unicodedata import normalize as _unicodedata_normalize
from apps.organization.scoping import get_user_accessible_gestionnaire_ids


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


def _expects_json_response(request):
    accept = request.headers.get('Accept', '')
    requested_with = request.headers.get('X-Requested-With', '')
    return (
        request.path.startswith('/api/')
        or 'application/json' in accept
        or requested_with == 'XMLHttpRequest'
    )

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

POSTES_RESTREINTS_GESTION_FACTURES_FORFAITAIRES = {
    'Agent de recouvrement',
    'Agent de recouvrement Superviseur technique',
}

POSTES_RESTREINTS_GESTION_FACTURES_FORFAITAIRES_NORMALIZED = {
    _normalize_poste_name(poste)
    for poste in POSTES_RESTREINTS_GESTION_FACTURES_FORFAITAIRES
}

POSTES_AUTORISES_COMPTA_HOME = {
    'Directeur',
    'Responsable operationnel',
    'Responsable administratif et financier',
    'Assistant(e) admin',
    'Assistant admin',
    'Assistante admin',
}

POSTES_AUTORISES_COMPTA_HOME_NORMALIZED = {
    _normalize_poste_name(poste) for poste in POSTES_AUTORISES_COMPTA_HOME
}

POSTES_AUTORISES_PAIE_HOME = {
    'Directeur',
    'Directeur adjoint',
    'Responsable administratif et financier',
    'Assistant(e) admin',
    'Assistant admin',
    'Assistante admin',
    'RAF',
    'Chef secteur',
    "Charge d'appui",
}

POSTES_AUTORISES_PAIE_HOME_NORMALIZED = {
    _normalize_poste_name(poste) for poste in POSTES_AUTORISES_PAIE_HOME
}

# Nom du groupe applique aux comptes visiteurs lecture seule
VISITEUR_GROUP_NAME = 'Visiteur'
# Nom normalise du poste visiteur
VISITEUR_POSTE_NORMALIZED = _normalize_poste_name('Visiteur')


def is_visiteur(user):
    """
    Retourne True si l'utilisateur est un visiteur.

    Regles:
    - utilisateur authentifie
    - membre du groupe "Visiteur" OU employe avec poste "Visiteur"
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if isinstance(user, Group):
        return False

    # Marque principale: groupe Visiteur
    try:
        if user.groups.filter(name=VISITEUR_GROUP_NAME).exists():
            return True
    except Exception:
        pass

    # Fallback: poste employe "Visiteur"
    try:
        employe = getattr(user, 'employe', None)
        poste = getattr(employe, 'poste', None)
        nom_poste = getattr(poste, 'nom_poste', '')
        return _normalize_poste_name(nom_poste) == VISITEUR_POSTE_NORMALIZED
    except Exception:
        return False


def has_admin_compta_access(user):
    """
    Verifie si l'utilisateur a acces aux menus Administration et Comptabilite
    en fonction du poste associe.

    Args:
        user: L'objet User Django

    Returns:
        bool: True si l'utilisateur est dans la liste des postes autorises, False sinon
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if not hasattr(user, 'employe') or not user.employe:
        return False

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


def has_compta_home_access(user):
    """
    Restreint l'accueil compta a une liste explicite de postes.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if getattr(user, 'is_superuser', False):
        return True

    poste = get_user_poste_name(user)
    if not poste:
        return False

    return _normalize_poste_name(poste) in POSTES_AUTORISES_COMPTA_HOME_NORMALIZED


def has_paie_home_access(user):
    """
    Restreint l'accueil paie aux postes autorises sur le volet RH/paie.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if getattr(user, 'is_superuser', False):
        return True

    poste = get_user_poste_name(user)
    if not poste:
        return False

    return _normalize_poste_name(poste) in POSTES_AUTORISES_PAIE_HOME_NORMALIZED


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


def can_manage_forfaitaire_factures(user):
    """
    Retourne True si l'utilisateur peut creer/modifier/supprimer
    des factures forfaitaires.

    Les postes "Agent de recouvrement" et
    "Agent de recouvrement Superviseur technique" restent en lecture seule
    sur ces actions.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if getattr(user, 'is_superuser', False):
        return True

    poste = get_user_poste_name(user)
    if not poste:
        return False

    return (
        _normalize_poste_name(poste)
        not in POSTES_RESTREINTS_GESTION_FACTURES_FORFAITAIRES_NORMALIZED
    )


def can_reschedule_forfaitaire_factures(user):
    """
    Retourne True si l'utilisateur peut deplacer la date/planning
    d'une facture forfaitaire sans modifier les montants.

    Contrairement a la gestion complete des factures, les postes
    "Agent de recouvrement" et
    "Agent de recouvrement Superviseur technique"
    sont autorises ici.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if getattr(user, 'is_superuser', False):
        return True

    poste = get_user_poste_name(user)
    if not poste:
        return False

    normalized = _normalize_poste_name(poste)
    if normalized in POSTES_RESTREINTS_GESTION_FACTURES_FORFAITAIRES_NORMALIZED:
        return True

    return can_manage_forfaitaire_factures(user)


def can_override_saisie_controls(user):
    """Directeur ou Responsable opérationnel : peut valider une saisie comptable malgré un contrôle métier."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    poste = get_user_poste_name(user)
    if not poste:
        return False
    return _normalize_poste_name(poste) in {'directeur', 'responsable operationnel'}


def is_directeur_poste(user):
    """Retourne True si l'utilisateur occupe un poste 'Directeur' (normalisé)."""
    poste = get_user_poste_name(user)
    return _normalize_poste_name(poste) == 'directeur'


def get_user_poste(user):
    """Alias utilisé par certains context processors ou vues."""
    return get_user_poste_name(user)


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
            if _expects_json_response(request):
                return JsonResponse({
                    'success': False,
                    'error': 'Authentification requise'
                }, status=401)
            messages.warning(request, "Vous devez etre connecte pour acceder a cette page.")
            return redirect('login')

        # Verifier si l'utilisateur a un employe lie
        if not hasattr(request.user, 'employe') or not request.user.employe:
            if _expects_json_response(request):
                return JsonResponse({
                    'success': False,
                    'error': "Acces refuse. Votre compte utilisateur n'est pas lie a un employe."
                }, status=403)
            messages.error(
                request,
                "Acces refuse. Votre compte utilisateur n'est pas lie a un employe."
            )
            return redirect('core:home')

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

    # Les visiteurs sont en lecture seule globale (sans restriction organisation)
    # Le blocage ecriture est gere par ReadOnlyVisitorMiddleware.
    if is_visiteur(user):
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

    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return queryset
    if not gestionnaire_ids:
        return queryset.none()

    # Determiner le nom du modele pour appliquer le bon filtre
    model_name = queryset.model.__name__

    from apps.organization.scoping import current_modalite_q

    # Filtrer selon le type de modele. Une modalite future ne donne aucun
    # acces avant sa date de debut, meme lorsque sa date de fin est vide.
    if model_name == 'Ouvrage':
        # Filtrer les ouvrages par organisation via la base
        current = current_modalite_q('modalites_gestion')
        organisation = (
            Q(modalites_gestion__gestionnaire_id__in=gestionnaire_ids) |
            Q(modalites_gestion__gestionnaire__isnull=True)
        )
        return queryset.filter(current & organisation).distinct()

    elif model_name == 'PointEau':
        # Filtrer les points d'eau par organisation via l'ouvrage
        current = current_modalite_q('ouvrage__modalites_gestion')
        organisation = (
            Q(ouvrage__modalites_gestion__gestionnaire_id__in=gestionnaire_ids) |
            Q(ouvrage__modalites_gestion__gestionnaire__isnull=True)
        )
        return queryset.filter(current & organisation).distinct()

    elif model_name == 'Parcelle':
        # Filtrer les parcelles par organisation via les points d'eau
        current = current_modalite_q('pointeau__ouvrage__modalites_gestion')
        organisation = (
            Q(pointeau__ouvrage__modalites_gestion__gestionnaire_id__in=gestionnaire_ids) |
            Q(pointeau__ouvrage__modalites_gestion__gestionnaire__isnull=True)
        )
        return queryset.filter(current & organisation).distinct()

    else:
        # Pour les autres modeles, retourner le queryset sans filtre
        # (peut etre etendu au besoin)
        return queryset


def est_responsable_actif_ouvrage(employe, ouvrage_id, date_reference=None):
    """
    Verifie qu'un Employe est responsable ACTIF et DIRECT (pas de notion de
    subordonnes, contrairement a get_user_responsable_ouvrage_ids) d'un
    ouvrage donne, a une date de reference donnee. Requete directe sur
    EmployeOuvrages.

    Reimplementation explicite (pas d'utilisation de la property est_actif
    d'EmployeOuvrages, qui utilise date.today() naif et ne verifie pas
    date_debut) - meme principe que dans monthly_billing_reminder.py.
    """
    from datetime import date as date_cls

    from apps.employees.models import EmployeOuvrages

    if employe is None or ouvrage_id is None:
        return False

    date_reference = date_reference or date_cls.today()
    return EmployeOuvrages.objects.filter(
        employe=employe, ouvrage_id=ouvrage_id, date_debut__lte=date_reference,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=date_reference)
    ).exists()


def est_agent_recouvrement(employe) -> bool:
    """
    True si le poste de l'employe contient 'recouvrement' (icontains,
    insensible a la casse) - meme motif que celui deja utilise ailleurs
    dans le projet pour identifier ce role (ex:
    apps/planning/views_planning_auto.py, filtre
    nom_poste__icontains='recouvrement').

    Volontairement PLUS ETROIT que Employe.is_agent_recouvrement
    (apps/employees/models.py) qui matche aussi tout poste contenant le mot
    'agent' seul (heuristique trop large, capturerait des postes de terrain
    sans rapport avec le recouvrement de creances). Reservee a l'exclusion
    specifique des destinataires de relances reparations - ne pas
    reutiliser Employe.is_agent_recouvrement pour ce besoin.
    """
    if employe is None or employe.poste_id is None:
        return False
    return 'recouvrement' in (employe.poste.nom_poste or '').lower()
