"""Migre les photos d'équipements et de points d'eau existantes vers la synchronisation de fichiers (décision Q7).

    python manage.py migrer_photos                                   # simulation (par défaut)
    python manage.py migrer_photos --appliquer                       # écrit réellement
    python manage.py migrer_photos --type equipement --limite 20     # essai restreint

Principes (les mêmes que ``migrer_dossiers_techniques``) :
- NON destructif : les colonnes ``photos`` ne sont ni lues en écriture ni vidées, les pages actuelles continuent
  de fonctionner ;
- idempotent : une photo déjà copiée (même entité, même catégorie, même SHA-256) est ignorée ;
- l'organisation propriétaire est le gestionnaire actuel de l'ouvrage ; sans ouvrage ou sans gestionnaire,
  la photo est ignorée (comptée dans le bilan).

Formats de photo reconnus dans le JSON : ``{'data': <base64 ou data:image/...>}``, ``{'url': '/media/...'}``
(fichier lu dans MEDIA_ROOT) et chaîne ``data:image/...;base64,...``. Tout le reste est compté « format inconnu ».
"""
import base64
import binascii
import hashlib
import json
import os
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.sync import stockage
from apps.sync.management.commands.migrer_dossiers_techniques import gestionnaire_de
from apps.sync.models import (ORIGINE_DEPOT, PORTEE_ENTITE, STATUT_COMPLET, CategorieFichier, Fichier,
                              FichierVersion)

# type d'entité -> (catégorie de fichiers, modèle)
CIBLES = {
    'equipement': ('photos_equipement', 'infrastructure.EquipementConstitutif'),
    'point_eau': ('photos_point_eau', 'billing.PointEau'),
}

SIGNATURES = (
    (b'\xff\xd8\xff', 'jpg'), (b'\x89PNG\r\n\x1a\n', 'png'), (b'GIF8', 'gif'),
)


def extension_par_contenu(octets):
    for signature, extension in SIGNATURES:
        if octets.startswith(signature):
            return extension
    if octets[:4] == b'RIFF' and octets[8:12] == b'WEBP':
        return 'webp'
    return ''


def decoder_base64(valeur):
    """Octets d'une chaîne Base64 brute ou ``data:image/...;base64,...`` ; ``None`` si illisible."""
    if not isinstance(valeur, str) or not valeur.strip():
        return None
    texte = valeur.strip()
    if texte.startswith('data:'):
        if ';base64,' not in texte[:120]:
            return None
        texte = texte.split(';base64,', 1)[1]
    try:
        return base64.b64decode(texte, validate=False)
    except (binascii.Error, ValueError):
        return None


def lire_fichier_media(url):
    """Octets d'un fichier référencé par une URL ``/media/...`` ; ``None`` s'il est absent ou hors de MEDIA_ROOT."""
    if not isinstance(url, str) or not url:
        return None
    prefixe = settings.MEDIA_URL or '/media/'
    relatif = url.split('?', 1)[0]
    if prefixe in relatif:
        relatif = relatif.split(prefixe, 1)[1]
    racine = os.path.realpath(str(settings.MEDIA_ROOT))
    chemin = os.path.realpath(os.path.join(racine, relatif.lstrip('/\\')))
    if not chemin.startswith(racine + os.sep) or not os.path.isfile(chemin):
        return None
    with open(chemin, 'rb') as source:
        return source.read()


def extraire_photos(valeur):
    """Liste de ``(nom_original, octets | None, raison)`` pour le contenu d'une colonne ``photos``.

    ``octets`` est ``None`` quand la photo est inutilisable ; ``raison`` vaut alors ``'format'`` (structure
    inconnue) ou ``'absent'`` (fichier ou Base64 illisible).
    """
    if valeur is None:
        return []
    if isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            return []
        if texte.startswith('[') or texte.startswith('{'):
            try:
                valeur = json.loads(texte)
            except ValueError:
                return [('', None, 'format')]
        else:
            valeur = [texte]
    if isinstance(valeur, dict):
        valeur = [valeur]
    if not isinstance(valeur, list):
        return [('', None, 'format')]

    resultat = []
    for element in valeur:
        if isinstance(element, str):
            octets = decoder_base64(element)
            resultat.append(('', octets, '' if octets else 'format'))
        elif isinstance(element, dict):
            nom = str(element.get('original_name') or element.get('filename') or element.get('name') or '')
            if element.get('data'):
                octets = decoder_base64(element['data'])
                resultat.append((nom, octets, '' if octets else 'absent'))
            elif element.get('url'):
                octets = lire_fichier_media(element['url'])
                resultat.append((nom or os.path.basename(str(element['url']).split('?', 1)[0]), octets,
                                 '' if octets else 'absent'))
            else:
                resultat.append((nom, None, 'format'))
        else:
            resultat.append(('', None, 'format'))
    return resultat


def nom_de_photo(nom_original, extension, sha256):
    """Nom lisible et unique dans le dossier : ``<racine>-<6 car. du SHA>.<ext>``."""
    racine = os.path.splitext(os.path.basename(nom_original))[0].strip()[:80] or 'photo'
    return f"{racine}-{sha256[:6]}.{extension}"


class Command(BaseCommand):
    help = "Copie les photos d'équipements et de points d'eau vers la synchronisation (simulation par défaut)."

    def add_arguments(self, parser):
        parser.add_argument('--appliquer', action='store_true', help="Écrit réellement (sinon simulation).")
        parser.add_argument('--type', choices=sorted(CIBLES), help="Un seul type d'entité (défaut : les deux).")
        parser.add_argument('--limite', type=int, help="Ne traite que les N premières entités de chaque type.")

    def handle(self, *args, **options):
        from django.apps import apps

        appliquer = options['appliquer']
        types = [options['type']] if options['type'] else sorted(CIBLES)
        bilan = {'copies': 0, 'deja': 0, 'sans_organisation': 0, 'extension': 0, 'absent': 0, 'format': 0,
                 'trop_gros': 0, 'erreur': 0}
        octets_total = 0
        cache_orga = {}

        for type_entite in types:
            code_categorie, chemin_modele = CIBLES[type_entite]
            categorie = CategorieFichier.objects.filter(code=code_categorie).first()
            if categorie is None:
                raise CommandError(f"Catégorie « {code_categorie} » absente : appliquez les migrations sync.")
            modele = apps.get_model(chemin_modele)
            entites = modele.objects.exclude(photos__isnull=True).only('id', 'ouvrage_id', 'photos').order_by('id')
            if options['limite']:
                entites = entites[:options['limite']]
            self.stdout.write(f"\n== {type_entite} ==")

            for entite in entites.iterator(chunk_size=20):
                photos = extraire_photos(entite.photos)
                if not photos:
                    continue
                if entite.ouvrage_id not in cache_orga:
                    cache_orga[entite.ouvrage_id] = gestionnaire_de(entite.ouvrage_id) if entite.ouvrage_id else None
                organisation = cache_orga[entite.ouvrage_id]
                if organisation is None:
                    bilan['sans_organisation'] += len(photos)
                    continue

                for nom_original, contenu, raison in photos:
                    if contenu is None:
                        bilan[raison or 'format'] += 1
                        continue
                    extension = extension_par_contenu(contenu) or stockage.extension_de(nom_original)
                    if categorie.extensions and extension not in categorie.extensions:
                        bilan['extension'] += 1
                        continue
                    if len(contenu) > stockage.taille_max_octets():
                        bilan['trop_gros'] += 1
                        continue
                    sha256 = hashlib.sha256(contenu).hexdigest()
                    if Fichier.objects.filter(
                        portee=PORTEE_ENTITE, entity_type=type_entite, entity_id=entite.id,
                        categorie_id=code_categorie, sha256=sha256, deleted_at__isnull=True,
                    ).exists():
                        bilan['deja'] += 1
                        continue
                    if not appliquer:
                        bilan['copies'] += 1
                        octets_total += len(contenu)
                        continue

                    nom = nom_de_photo(nom_original, extension, sha256)
                    ident = uuid.uuid4()
                    chemin = stockage.chemin_relatif_entite(type_entite, entite.id, code_categorie, ident, extension)
                    try:
                        stockage.ecrire(iter([contenu]), chemin, taille_max=max(len(contenu), 1))
                        with transaction.atomic():
                            fichier = Fichier.objects.create(
                                id=ident, organisation=organisation, portee=PORTEE_ENTITE, entity_type=type_entite,
                                entity_id=entite.id, categorie_id=code_categorie, nom=nom, storage_path=chemin,
                                sha256=sha256, taille=len(contenu), version=1, statut=STATUT_COMPLET,
                            )
                            FichierVersion.objects.create(
                                fichier=fichier, numero=1, nom=nom, storage_path=chemin, sha256=sha256,
                                taille=len(contenu), origine=ORIGINE_DEPOT,
                            )
                    except Exception as exc:  # noqa: BLE001 - on continue avec les autres photos
                        stockage.supprimer_definitivement_temporaire(chemin)
                        bilan['erreur'] += 1
                        self.stderr.write(f"[ERREUR] {type_entite} {entite.id} : {exc}")
                        continue
                    bilan['copies'] += 1
                    octets_total += len(contenu)

        mode = 'APPLIQUÉ' if appliquer else 'SIMULATION (ajoutez --appliquer pour écrire)'
        self.stdout.write(f"\n[{mode}] à copier/copiées : {bilan['copies']} ({octets_total / 1024 / 1024:.1f} Mo)")
        self.stdout.write(
            f"déjà migrées : {bilan['deja']} | sans ouvrage ou gestionnaire : {bilan['sans_organisation']} | "
            f"extension refusée : {bilan['extension']} | trop volumineuses : {bilan['trop_gros']} | "
            f"illisibles : {bilan['absent']} | format inconnu : {bilan['format']} | erreurs : {bilan['erreur']}")
