"""Stockage des fichiers synchronisés sur le disque du VPS.

Règles de sécurité :
- le répertoire (``HYDRIA_STORAGE_DIR``) n'est JAMAIS servi par nginx ni par Django (hors MEDIA_ROOT
  et STATIC_ROOT) : les fichiers ne sortent que par la vue de téléchargement, après contrôle des droits ;
- tout chemin est reconstruit à partir de composants validés (identifiants, codes) et vérifié
  pour ne jamais sortir du répertoire de stockage (path traversal) ;
- le nom stocké est un identifiant généré, le nom d'origine reste en base.

Variables d'environnement (ou réglages Django du même nom) :
- ``HYDRIA_STORAGE_DIR``     répertoire racine (défaut ``/srv/hydria/storage``) ;
- ``HYDRIA_TAILLE_MAX_MO``   taille maximale par fichier en Mo (défaut 100) ;
- ``HYDRIA_QUOTA_ORGA_GO``   quota par organisation en Go (défaut 50).
"""
import hashlib
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

DEFAUT_RACINE = '/srv/hydria/storage'
DEFAUT_TAILLE_MAX_MO = 100
DEFAUT_QUOTA_ORGA_GO = 50
TAILLE_BLOC = 1024 * 1024
DOSSIER_CORBEILLE = '_corbeille'

_RE_CODE = re.compile(r'^[a-z0-9_]{1,64}$')
_RE_EXTENSION = re.compile(r'^[a-z0-9]{1,10}$')


class ErreurStockage(Exception):
    """Erreur de stockage avec un code stable (renvoyé tel quel par l'API)."""

    code = 'ERREUR_STOCKAGE'

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class CheminInvalide(ErreurStockage):
    code = 'CHEMIN_INVALIDE'


class FichierTropVolumineux(ErreurStockage):
    code = 'FICHIER_TROP_VOLUMINEUX'


class QuotaDepasse(ErreurStockage):
    code = 'QUOTA_DEPASSE'


class StockageIndisponible(ErreurStockage):
    code = 'STOCKAGE_INDISPONIBLE'


# --------------------------------------------------------------------------- configuration

def _lire_reglage(nom, defaut):
    valeur = getattr(settings, nom, None)
    if valeur in (None, ''):
        valeur = os.environ.get(nom)
    return defaut if valeur in (None, '') else valeur


def racine():
    """Répertoire racine de stockage (chemin absolu résolu)."""
    chemin = Path(str(_lire_reglage('HYDRIA_STORAGE_DIR', DEFAUT_RACINE))).expanduser().resolve()
    for interdit in (getattr(settings, 'MEDIA_ROOT', None), getattr(settings, 'STATIC_ROOT', None)):
        if not interdit:
            continue
        interdit = Path(str(interdit)).resolve()
        if chemin == interdit or interdit in chemin.parents or chemin in interdit.parents:
            raise ImproperlyConfigured(
                "HYDRIA_STORAGE_DIR ne doit pas être dans (ni contenir) MEDIA_ROOT ou STATIC_ROOT : "
                "ce répertoire ne doit jamais être servi directement."
            )
    return chemin


def taille_max_octets():
    return int(float(_lire_reglage('HYDRIA_TAILLE_MAX_MO', DEFAUT_TAILLE_MAX_MO)) * 1024 * 1024)


def quota_organisation_octets():
    return int(float(_lire_reglage('HYDRIA_QUOTA_ORGA_GO', DEFAUT_QUOTA_ORGA_GO)) * 1024 ** 3)


# --------------------------------------------------------------------------- chemins

def _code(valeur, nom):
    valeur = str(valeur or '')
    if not _RE_CODE.match(valeur):
        raise CheminInvalide(f"{nom} invalide pour un chemin de stockage.")
    return valeur


def _uuid(valeur, nom):
    try:
        return str(uuid.UUID(str(valeur)))
    except (ValueError, TypeError, AttributeError):
        raise CheminInvalide(f"{nom} invalide pour un chemin de stockage.")


def extension_de(nom_original):
    """Extension en minuscules, sans point ('' si aucune ou suspecte)."""
    extension = os.path.splitext(str(nom_original or ''))[1].lstrip('.').lower()
    return extension if _RE_EXTENSION.match(extension) else ''


def chemin_relatif_entite(entity_type, entity_id, categorie, id_fichier, extension=''):
    """entite/{EntityType}/{EntityID}/{Categorie}/{identifiant}[.ext]"""
    return _assembler(
        ['entite', _code(entity_type, 'Type d\'entité'), _uuid(entity_id, 'Identifiant d\'entité'),
         _code(categorie, 'Catégorie')],
        id_fichier, extension,
    )


def chemin_relatif_organisation(organisation_id, domaine, categorie, id_fichier, extension=''):
    """organisation/{OrganisationID}/{Domaine}/{Categorie}/{identifiant}[.ext]"""
    return _assembler(
        ['organisation', _uuid(organisation_id, 'Identifiant d\'organisation'),
         _code(domaine, 'Domaine'), _code(categorie, 'Catégorie')],
        id_fichier, extension,
    )


def _assembler(dossiers, id_fichier, extension):
    nom = _uuid(id_fichier, 'Identifiant de fichier')
    if extension:
        if not _RE_EXTENSION.match(extension):
            raise CheminInvalide("Extension invalide pour un chemin de stockage.")
        nom = f'{nom}.{extension}'
    return '/'.join(dossiers + [nom])


def resoudre(chemin_relatif):
    """Chemin absolu sûr d'un chemin relatif ; lève CheminInvalide si on sort de la racine."""
    texte = str(chemin_relatif or '')
    if (not texte or '\x00' in texte or '\\' in texte or texte.startswith('/')
            or re.match(r'^[A-Za-z]:', texte)):
        raise CheminInvalide("Chemin de stockage invalide.")
    if any(partie in ('', '.', '..') for partie in texte.split('/')):
        raise CheminInvalide("Chemin de stockage invalide.")
    base = racine()
    cible = (base / texte).resolve()
    if base != cible and base not in cible.parents:
        raise CheminInvalide("Chemin de stockage hors du répertoire autorisé.")
    return cible


# --------------------------------------------------------------------------- écriture / lecture

def ecrire(flux, chemin_relatif, *, taille_max=None, quota_restant=None):
    """Écrit ``flux`` (itérable de blocs d'octets) de façon atomique.

    Fichier temporaire dans le même dossier, SHA-256 et taille calculés à la réception, puis
    renommage. Les limites sont contrôlées pendant la lecture (jamais sur la foi de Content-Length).
    Retourne ``(sha256, taille)``.
    """
    cible = resoudre(chemin_relatif)
    taille_max = taille_max_octets() if taille_max is None else taille_max
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StockageIndisponible(f"Répertoire de stockage inaccessible : {exc.strerror or exc}")

    temporaire = cible.parent / f'.tmp-{uuid.uuid4().hex}'
    empreinte = hashlib.sha256()
    taille = 0
    try:
        with open(temporaire, 'xb') as sortie:
            for bloc in flux:
                taille += len(bloc)
                if taille > taille_max:
                    raise FichierTropVolumineux(
                        f"Fichier trop volumineux : maximum {taille_max // (1024 * 1024)} Mo par fichier."
                    )
                if quota_restant is not None and taille > quota_restant:
                    raise QuotaDepasse("Quota de stockage de l'organisation dépassé.")
                empreinte.update(bloc)
                sortie.write(bloc)
            sortie.flush()
            os.fsync(sortie.fileno())
        os.replace(temporaire, cible)
    except BaseException:
        try:
            temporaire.unlink()
        except OSError:
            pass
        raise
    return empreinte.hexdigest(), taille


def blocs(fichier_televerse):
    """Itère sur un fichier téléversé Django par blocs de 1 Mo."""
    return fichier_televerse.chunks(TAILLE_BLOC)


def copier(source_relative, destination_relative, *, taille_max=None, quota_restant=None):
    """Copie atomique d'un fichier stocké vers un nouveau chemin (restauration d'une version).

    Retourne ``(sha256, taille)`` recalculés sur la copie."""
    with ouvrir(source_relative) as source:
        return ecrire(iter(lambda: source.read(TAILLE_BLOC), b''), destination_relative,
                      taille_max=taille_max, quota_restant=quota_restant)


def ouvrir(chemin_relatif):
    """Ouvre un fichier stocké en lecture binaire (FileNotFoundError s'il n'existe pas)."""
    return open(resoudre(chemin_relatif), 'rb')


def existe(chemin_relatif):
    try:
        return resoudre(chemin_relatif).is_file()
    except CheminInvalide:
        return False


def mettre_a_la_corbeille(chemin_relatif):
    """Suppression logique : déplace le fichier sous ``_corbeille/{AAAAMMJJ-HHMMSS}/{chemin}``.

    Retourne le nouveau chemin relatif, ou None si le fichier n'existait pas.
    """
    source = resoudre(chemin_relatif)
    if not source.is_file():
        return None
    horodatage = datetime.now().strftime('%Y%m%d-%H%M%S')
    relatif_corbeille = f'{DOSSIER_CORBEILLE}/{horodatage}/{chemin_relatif}'
    destination = resoudre(relatif_corbeille)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    return relatif_corbeille


def supprimer_definitivement_temporaire(chemin_relatif):
    """Nettoyage d'un fichier qu'on vient d'écrire mais dont l'enregistrement a échoué."""
    try:
        resoudre(chemin_relatif).unlink()
    except (OSError, CheminInvalide):
        pass


def espace_disque():
    """(total, utilisé, libre) en octets pour le disque du stockage."""
    base = racine()
    cible = base if base.exists() else base.parent
    usage = shutil.disk_usage(cible)
    return usage.total, usage.used, usage.free


DEFAUT_VERSIONS_MAX = 20


def versions_max():
    """Nombre maximal de versions de contenu conservées par fichier (HYDRIA_VERSIONS_MAX, défaut 20)."""
    return max(1, int(float(_lire_reglage('HYDRIA_VERSIONS_MAX', DEFAUT_VERSIONS_MAX))))
