"""Migre les dossiers techniques d'ouvrage existants vers la synchronisation de fichiers (décision Q6).

    python manage.py migrer_dossiers_techniques                      # simulation (par défaut)
    python manage.py migrer_dossiers_techniques --appliquer          # copie réellement
    python manage.py migrer_dossiers_techniques --appliquer --organisation-defaut <uuid>

Principes :
- NON destructif : les lignes ``OuvrageDossierTechnique`` et les fichiers de ``media/`` ne sont ni
  modifiés ni supprimés (les pages actuelles continuent de fonctionner jusqu'à leur bascule) ;
- idempotent : un dossier déjà copié (même ouvrage, même nom, même SHA-256) est ignoré ;
- l'organisation propriétaire est le gestionnaire actuel de l'ouvrage, à défaut le plus récent ;
  sans gestionnaire, le dossier est ignoré sauf si ``--organisation-defaut`` est fourni.
"""
import hashlib
import os
import uuid
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.sync import stockage
from apps.sync.models import (ORIGINE_DEPOT, PORTEE_ENTITE, STATUT_COMPLET, CategorieFichier, Fichier,
                              FichierVersion)

CATEGORIE = 'dossier_technique'


def gestionnaire_de(ouvrage_id):
    """Organisation gestionnaire : modalité active aujourd'hui, sinon la plus récente."""
    from apps.billing.models import ModaliteGestion

    modalites = ModaliteGestion.objects.filter(ouvrage_id=ouvrage_id, gestionnaire__isnull=False)
    aujourdhui = date.today()
    courante = modalites.filter(statut='actif', date_debut__lte=aujourdhui).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=aujourdhui)).order_by('-date_debut').first()
    modalite = courante or modalites.order_by('-date_debut').first()
    return modalite.gestionnaire if modalite else None


def blocs_de(champ_fichier):
    with champ_fichier.open('rb') as source:
        yield from iter(lambda: source.read(stockage.TAILLE_BLOC), b'')


class Command(BaseCommand):
    help = "Copie les dossiers techniques d'ouvrage vers la synchronisation de fichiers (simulation par défaut)."

    def add_arguments(self, parser):
        parser.add_argument('--appliquer', action='store_true', help="Écrit réellement (sinon simulation).")
        parser.add_argument('--organisation-defaut', help="UUID de l'organisation pour les ouvrages sans gestionnaire.")
        parser.add_argument('--limite', type=int, help="Ne traite que les N premiers dossiers (essai).")

    def handle(self, *args, **options):
        from apps.organization.models import Organisation, OuvrageDossierTechnique

        categorie = CategorieFichier.objects.filter(code=CATEGORIE).first()
        if categorie is None:
            raise CommandError("Catégorie « dossier_technique » absente : appliquez les migrations sync.")
        defaut = None
        if options['organisation_defaut']:
            defaut = Organisation.objects.filter(pk=options['organisation_defaut']).first()
            if defaut is None:
                raise CommandError("Organisation par défaut introuvable.")
        appliquer = options['appliquer']

        bilan = {'copies': 0, 'deja': 0, 'sans_organisation': 0, 'extension': 0, 'absent': 0, 'erreur': 0}
        octets = 0
        dossiers = OuvrageDossierTechnique.objects.select_related('ouvrage').order_by('created_at', 'id')
        if options['limite']:
            dossiers = dossiers[:options['limite']]

        for dossier in dossiers:
            nom = (dossier.nom_affichage or os.path.basename(dossier.fichier.name or '')).strip()[:255] or 'dossier'
            extension = stockage.extension_de(nom) or stockage.extension_de(dossier.fichier.name)
            if categorie.extensions and extension not in categorie.extensions:
                bilan['extension'] += 1
                self.stdout.write(f"[IGNORE extension .{extension or '?'}] {nom}")
                continue
            organisation = gestionnaire_de(dossier.ouvrage_id) or defaut
            if organisation is None:
                bilan['sans_organisation'] += 1
                continue
            try:
                empreinte = hashlib.sha256()
                taille = 0
                for bloc in blocs_de(dossier.fichier):
                    empreinte.update(bloc)
                    taille += len(bloc)
            except (FileNotFoundError, ValueError, OSError):
                bilan['absent'] += 1
                self.stdout.write(f"[ABSENT du disque] {dossier.fichier.name}")
                continue
            sha256 = empreinte.hexdigest()
            if Fichier.objects.filter(
                portee=PORTEE_ENTITE, entity_type='ouvrage', entity_id=dossier.ouvrage_id,
                categorie_id=CATEGORIE, sha256=sha256, nom=nom, deleted_at__isnull=True,
            ).exists():
                bilan['deja'] += 1
                continue
            if not appliquer:
                bilan['copies'] += 1
                octets += taille
                continue

            ident = uuid.uuid4()
            chemin = stockage.chemin_relatif_entite('ouvrage', dossier.ouvrage_id, CATEGORIE, ident, extension)
            try:
                stockage.ecrire(blocs_de(dossier.fichier), chemin, taille_max=max(taille, 1))
                with transaction.atomic():
                    fichier = Fichier.objects.create(
                        id=ident, organisation=organisation, portee=PORTEE_ENTITE, entity_type='ouvrage',
                        entity_id=dossier.ouvrage_id, categorie_id=CATEGORIE, nom=nom, storage_path=chemin,
                        sha256=sha256, taille=taille, version=1, statut=STATUT_COMPLET,
                    )
                    FichierVersion.objects.create(
                        fichier=fichier, numero=1, nom=nom, storage_path=chemin, sha256=sha256, taille=taille,
                        origine=ORIGINE_DEPOT,
                    )
            except Exception as exc:  # noqa: BLE001 - on continue avec les autres dossiers
                stockage.supprimer_definitivement_temporaire(chemin)
                bilan['erreur'] += 1
                self.stderr.write(f"[ERREUR] {nom} : {exc}")
                continue
            bilan['copies'] += 1
            octets += taille

        mode = 'APPLIQUÉ' if appliquer else 'SIMULATION (ajoutez --appliquer pour écrire)'
        self.stdout.write(f"\n[{mode}] à copier/copiés : {bilan['copies']} ({octets / 1024 / 1024:.1f} Mo)")
        self.stdout.write(
            f"déjà migrés : {bilan['deja']} | sans gestionnaire (ignorés) : {bilan['sans_organisation']} | "
            f"extension refusée : {bilan['extension']} | absents du disque : {bilan['absent']} | erreurs : {bilan['erreur']}")
        if bilan['sans_organisation']:
            self.stdout.write("Astuce : --organisation-defaut <uuid> pour rattacher les ouvrages sans gestionnaire.")
