"""Point de contrôle d'accès CENTRAL de la synchronisation.

Toutes les vues passent par ces fonctions : aucune règle d'accès n'est écrite ailleurs.

Principes :
- l'appartenance à l'organisation vient de ``apps.organization.scoping`` (employé -> base -> organisation,
  et gestionnaires affectés pour une organisation partenaire) ;
- la lecture d'un ouvrage / équipement / point d'eau passe par ``filter_queryset_by_permissions`` (décision Q2) ;
- un fichier n'est jamais lisible par une organisation sans lien avec lui (cloisonnement) ;
- les droits PAR DOMAINE sont configurables ci-dessous.

Domaines : opérationnel et logistique sont ouverts à tous les membres. Les domaines financier et
administratif sont VOLONTAIREMENT sans règle (question ouverte Q8) : tant qu'aucune règle n'est
renseignée, seuls les superutilisateurs y accèdent.
"""
from django.conf import settings

from . import entites
from .models import DOMAINES, PORTEE_ORGANISATION

TOUS = '*'

# domaine -> {'lecture': TOUS | liste de postes, 'ecriture': TOUS | liste de postes}
# Les postes s'écrivent normalisés (minuscules, sans accents), comme dans apps.organization.scoping.
# Une liste vide = personne (sauf superutilisateur). Surchargeable via settings.HYDRIA_SYNC_REGLES_DOMAINES.
REGLES_DOMAINES_PAR_DEFAUT = {
    'operationnel': {'lecture': TOUS, 'ecriture': TOUS},
    'logistique': {'lecture': TOUS, 'ecriture': TOUS},
    'administratif': {'lecture': [], 'ecriture': []},  # TODO Q8 : à définir
    'financier': {'lecture': [], 'ecriture': []},      # TODO Q8 : à définir
}


class AccesRefuse(Exception):
    def __init__(self, message, code='ACCES_REFUSE', statut=403):
        super().__init__(message)
        self.message = message
        self.code = code
        self.statut = statut


def regles_domaines():
    regles = {d: dict(r) for d, r in REGLES_DOMAINES_PAR_DEFAUT.items()}
    for domaine, regle in (getattr(settings, 'HYDRIA_SYNC_REGLES_DOMAINES', None) or {}).items():
        if domaine in regles:
            regles[domaine].update(regle)
    return regles


# --------------------------------------------------------------------------- utilisateur / organisation

def utilisateur_sync_autorise(user):
    """Compte actif, ni visiteur, avec une organisation (ou superutilisateur)."""
    from apps.employees.permissions import is_visiteur
    from apps.organization.scoping import get_user_organisation

    if not user or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return False
    if user.is_superuser:
        return True
    if is_visiteur(user):
        return False
    return get_user_organisation(user) is not None


def organisations_lisibles(user):
    """None = toutes (superutilisateur) ; sinon ensemble d'identifiants (str) d'organisations."""
    from apps.organization.scoping import get_user_accessible_gestionnaire_ids, get_user_organisation

    if user.is_superuser:
        return None
    ids = {str(i) for i in (get_user_accessible_gestionnaire_ids(user) or [])}
    propre = get_user_organisation(user)
    if propre is not None:
        ids.add(str(propre.id))
    return ids


def peut_acceder_organisation(user, organisation_id):
    lisibles = organisations_lisibles(user)
    return lisibles is None or str(organisation_id) in lisibles


def organisation_depot(user, demandee=None):
    """Organisation qui dépose un fichier (décision Q2) : la sienne, ou une organisation accessible."""
    from apps.organization.models import Organisation
    from apps.organization.scoping import get_user_organisation

    if demandee:
        try:
            organisation = Organisation.objects.filter(pk=demandee).first()
        except (ValueError, TypeError):
            organisation = None
        if organisation is None:
            raise AccesRefuse("Organisation introuvable.", 'ORGANISATION_INTROUVABLE', 404)
        if not peut_acceder_organisation(user, organisation.id):
            raise AccesRefuse("Vous n'appartenez pas à cette organisation.", 'ORGANISATION_INTERDITE')
        return organisation
    propre = get_user_organisation(user)
    if propre is None:
        raise AccesRefuse(
            "Aucune organisation rattachée à votre compte : précisez le paramètre 'organisation'.",
            'ORGANISATION_REQUISE', 400,
        )
    return propre


# --------------------------------------------------------------------------- domaines

def _poste_normalise(user):
    from apps.organization.scoping import _normalize_poste_name
    employe = getattr(user, 'employe', None)
    return _normalize_poste_name(getattr(getattr(employe, 'poste', None), 'nom_poste', ''))


def peut_domaine(user, domaine, mode):
    """``mode`` : 'lecture' ou 'ecriture'."""
    if domaine not in DOMAINES:
        return False
    if user.is_superuser:
        return True
    regle = regles_domaines()[domaine].get(mode, [])
    if regle == TOUS:
        return True
    autorises = {str(p) for p in regle}
    return bool(autorises) and _poste_normalise(user) in autorises


def domaines_lisibles(user):
    return {d for d in DOMAINES if peut_domaine(user, d, 'lecture')}


# --------------------------------------------------------------------------- entités

def entite_visible(user, entity_type, entity_id):
    """L'entité existe et l'utilisateur a le droit de la voir."""
    from apps.employees.permissions import filter_queryset_by_permissions

    if not entites.existe(entity_type, entity_id):
        return False
    if user.is_superuser:
        return True
    if entity_type == 'ouvrage' or entity_type == 'point_eau':
        classe = entites.modele(entity_type)
        return filter_queryset_by_permissions(classe.objects.filter(pk=entity_id), user).exists()
    if entity_type == 'equipement':
        ouvrage_id = entites.modele('equipement').objects.filter(pk=entity_id).values_list('ouvrage_id', flat=True).first()
        if ouvrage_id is None:
            return True
        ouvrages = filter_queryset_by_permissions(entites.modele('ouvrage').objects.filter(pk=ouvrage_id), user)
        return ouvrages.exists()
    return True  # référentiel (géographie, activités) : visible de tous les membres


# --------------------------------------------------------------------------- fichiers

def peut_lire_fichier(user, fichier):
    if not utilisateur_sync_autorise(user):
        return False
    if user.is_superuser:
        return True
    if fichier.portee == PORTEE_ORGANISATION:
        return peut_acceder_organisation(user, fichier.organisation_id) and peut_domaine(user, fichier.domaine, 'lecture')
    if peut_acceder_organisation(user, fichier.organisation_id):
        return True
    # Fichier déposé par une autre organisation : lisible seulement si l'utilisateur voit l'ouvrage concerné.
    return fichier.entity_type in entites.FAMILLE_OUVRAGE and entite_visible(user, fichier.entity_type, fichier.entity_id)


def peut_ecrire_fichier(user, fichier):
    if not utilisateur_sync_autorise(user):
        return False
    if user.is_superuser:
        return True
    if not peut_acceder_organisation(user, fichier.organisation_id):
        return False
    if fichier.portee == PORTEE_ORGANISATION:
        return peut_domaine(user, fichier.domaine, 'ecriture')
    return True
