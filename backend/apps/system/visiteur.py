from django.contrib.auth.models import Group, User
from django.db import transaction

from apps.employees.models import Employe, Poste
from apps.employees.permissions import VISITEUR_GROUP_NAME
from apps.organization.models import Base


VISITEUR_POSTE_NAME = 'Visiteur'


def _normalize_email(email):
    return (email or '').strip().lower()


def _alias_from_email(email):
    local_part = _normalize_email(email).split('@')[0]
    alias = local_part.replace('.', ' ').replace('_', ' ').replace('-', ' ').strip()
    if not alias:
        alias = 'visiteur'
    return alias[:255]


def get_default_visiteur_base():
    """
    Retourne une base par defaut pour rattacher les comptes visiteurs.
    """
    return Base.objects.select_related('organisation').order_by('nom_base').first()


def get_or_create_visiteur_poste(base):
    if not base or not getattr(base, 'organisation', None):
        raise ValueError("Aucune base valide n'est disponible pour le profil visiteur.")
    poste, _ = Poste.objects.get_or_create(
        organisation=base.organisation,
        nom_poste=VISITEUR_POSTE_NAME,
        defaults={'prefixe': 'VIS'},
    )
    return poste


@transaction.atomic
def ensure_visiteur_profile(user, email=None):
    """
    Force le compte utilisateur en mode Visiteur:
    - appartenance au groupe "Visiteur"
    - droits Django non-admin
    - creation (ou mise a jour) d'un employe lie pour la capture GPS
    """
    if not isinstance(user, User):
        raise ValueError("Utilisateur invalide.")

    normalized_email = _normalize_email(email or user.email or user.username)
    if not normalized_email or '@' not in normalized_email:
        raise ValueError("Email visiteur invalide.")

    visiteur_group, _ = Group.objects.get_or_create(name=VISITEUR_GROUP_NAME)
    user.groups.add(visiteur_group)

    user_updates = []
    if user.email != normalized_email:
        user.email = normalized_email
        user_updates.append('email')

    if user.username != normalized_email:
        username_exists = User.objects.filter(username=normalized_email).exclude(pk=user.pk).exists()
        if not username_exists:
            user.username = normalized_email
            user_updates.append('username')

    if user.is_staff:
        user.is_staff = False
        user_updates.append('is_staff')

    if user.is_superuser:
        user.is_superuser = False
        user_updates.append('is_superuser')

    if not user.is_active:
        user.is_active = True
        user_updates.append('is_active')

    if user_updates:
        user.save(update_fields=user_updates)

    base = get_default_visiteur_base()
    if base is None:
        raise ValueError("Aucune base n'est configuree pour rattacher un visiteur.")

    poste_visiteur = get_or_create_visiteur_poste(base)
    alias = _alias_from_email(normalized_email)
    employe = Employe.objects.filter(user=user).first()

    if employe is None:
        employe = Employe.objects.create(
            user=user,
            nom_employe=normalized_email,
            nom=alias,
            prenom='Visiteur',
            surnom=alias,
            poste=poste_visiteur,
            base=base,
            salarie=False,
            mail=normalized_email,
        )
        return employe

    employe_updates = []

    if employe.poste_id != poste_visiteur.id:
        employe.poste = poste_visiteur
        employe_updates.append('poste')

    if not employe.base_id:
        employe.base = base
        employe_updates.append('base')

    if employe.mail != normalized_email:
        employe.mail = normalized_email
        employe_updates.append('mail')

    if employe.date_debauchage is not None:
        employe.date_debauchage = None
        employe_updates.append('date_debauchage')

    if not employe.nom_employe:
        employe.nom_employe = normalized_email
        employe_updates.append('nom_employe')

    if not employe.nom:
        employe.nom = alias
        employe_updates.append('nom')

    if not employe.surnom:
        employe.surnom = alias
        employe_updates.append('surnom')

    if employe.salarie:
        employe.salarie = False
        employe_updates.append('salarie')

    if employe_updates:
        employe.save(update_fields=employe_updates)

    return employe


def remove_visiteur_group(user):
    if not isinstance(user, User):
        return
    visiteur_group = Group.objects.filter(name=VISITEUR_GROUP_NAME).first()
    if visiteur_group:
        user.groups.remove(visiteur_group)
