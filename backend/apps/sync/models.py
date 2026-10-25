"""Modèles de la synchronisation de fichiers (type Dropbox).

Quatre tables :
- ``categories_fichiers`` : référentiel des catégories (pré-rempli par la migration 0002) ;
- ``fichiers`` : métadonnées des fichiers (le contenu est sur le disque du VPS) ;
- ``sync_changes`` : journal ordonné des changements, alimenté par des triggers PostgreSQL ;
- ``sync_devices`` : curseur de synchronisation de chaque ordinateur.

Convention : colonnes en snake_case comme le reste du projet
(``Fichiers.OrganisationID`` du cahier des charges = ``fichiers.organisation_id``).
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

PORTEE_ENTITE = 'entite'
PORTEE_ORGANISATION = 'organisation'
PORTEE_CHOICES = [
    (PORTEE_ENTITE, 'Entité'),
    (PORTEE_ORGANISATION, 'Organisation'),
]

DOMAINE_OPERATIONNEL = 'operationnel'
DOMAINE_ADMINISTRATIF = 'administratif'
DOMAINE_FINANCIER = 'financier'
DOMAINE_LOGISTIQUE = 'logistique'
DOMAINE_CHOICES = [
    (DOMAINE_OPERATIONNEL, 'Opérationnel'),
    (DOMAINE_ADMINISTRATIF, 'Administratif'),
    (DOMAINE_FINANCIER, 'Financier'),
    (DOMAINE_LOGISTIQUE, 'Logistique'),
]
DOMAINES = [code for code, _ in DOMAINE_CHOICES]

STATUT_EN_ATTENTE = 'en_attente'
STATUT_COMPLET = 'complet'
STATUT_CHOICES = [
    (STATUT_EN_ATTENTE, 'En attente'),
    (STATUT_COMPLET, 'Complet'),
]

ACTION_CHOICES = [
    ('insert', 'Création'),
    ('update', 'Modification'),
    ('delete', 'Suppression'),
]

# Types d'entités auxquelles un fichier peut être rattaché / qui apparaissent dans le journal.
ENTITY_TYPES = [
    'region', 'district', 'commune', 'fokontany', 'village',
    'ouvrage', 'equipement', 'point_eau', 'activite',
]


class CategorieFichier(models.Model):
    code = models.CharField(max_length=64, primary_key=True)
    libelle = models.CharField(max_length=255)
    portee = models.CharField(max_length=20, choices=PORTEE_CHOICES)
    domaine = models.CharField(
        max_length=20, choices=DOMAINE_CHOICES, null=True, blank=True,
        help_text="Renseigné si portée = organisation, vide sinon.",
    )
    # Extensions au cahier des charges : permettent de refuser un fichier incohérent avec la catégorie.
    entity_types = models.JSONField(
        default=list, blank=True,
        help_text="Types d'entités acceptés (portée entité). Liste vide = tous.",
    )
    extensions = models.JSONField(
        default=list, blank=True,
        help_text="Extensions de fichier acceptées, sans point. Liste vide = toutes.",
    )
    actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'categories_fichiers'
        ordering = ['portee', 'domaine', 'code']
        constraints = [
            models.CheckConstraint(
                name='categories_fichiers_portee_domaine',
                check=(
                    (Q(portee=PORTEE_ENTITE) & Q(domaine__isnull=True))
                    | (Q(portee=PORTEE_ORGANISATION) & Q(domaine__in=DOMAINES))
                ),
            ),
        ]

    def __str__(self):
        return self.libelle


class Fichier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        'organization.Organisation', on_delete=models.PROTECT,
        related_name='fichiers_sync',
        help_text="Organisation qui dépose le fichier.",
    )
    portee = models.CharField(max_length=20, choices=PORTEE_CHOICES)
    entity_type = models.CharField(max_length=30, null=True, blank=True)
    entity_id = models.UUIDField(null=True, blank=True)
    domaine = models.CharField(max_length=20, choices=DOMAINE_CHOICES, null=True, blank=True)
    categorie = models.ForeignKey(
        CategorieFichier, on_delete=models.PROTECT, db_column='categorie',
        related_name='fichiers',
    )
    nom = models.CharField(max_length=255, help_text="Nom d'origine du fichier.")
    storage_path = models.CharField(
        max_length=500, unique=True,
        help_text="Chemin relatif au répertoire de stockage (HYDRIA_STORAGE_DIR).",
    )
    sha256 = models.CharField(max_length=64)
    taille = models.BigIntegerField(help_text="Octets.")
    version = models.PositiveIntegerField(default=1)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STATUT_COMPLET)
    depose_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fichiers_sync',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'fichiers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organisation', 'entity_type', 'entity_id'], name='fichiers_entite_idx'),
            models.Index(fields=['organisation', 'domaine'], name='fichiers_domaine_idx'),
        ]
        constraints = [
            # Cohérence portée / entité / domaine. La cohérence avec la catégorie (autre table)
            # est imposée par le trigger sync_verifier_fichier (migration 0002).
            models.CheckConstraint(
                name='fichiers_coherence_portee',
                check=(
                    (
                        Q(portee=PORTEE_ENTITE)
                        & Q(entity_type__isnull=False) & Q(entity_id__isnull=False)
                        & Q(domaine__isnull=True)
                    )
                    | (
                        Q(portee=PORTEE_ORGANISATION)
                        & Q(entity_type__isnull=True) & Q(entity_id__isnull=True)
                        & Q(domaine__in=DOMAINES)
                    )
                ),
            ),
            models.CheckConstraint(name='fichiers_taille_positive', check=Q(taille__gte=0)),
            models.CheckConstraint(name='fichiers_version_positive', check=Q(version__gte=1)),
            models.CheckConstraint(
                name='fichiers_statut_valide',
                check=Q(statut__in=[STATUT_EN_ATTENTE, STATUT_COMPLET]),
            ),
        ]

    def __str__(self):
        return self.nom


ORIGINE_DEPOT = 'depot'
ORIGINE_REMPLACEMENT = 'remplacement'
ORIGINE_RESTAURATION = 'restauration'
ORIGINE_CHOICES = [
    (ORIGINE_DEPOT, 'Dépôt initial'),
    (ORIGINE_REMPLACEMENT, 'Remplacement du contenu'),
    (ORIGINE_RESTAURATION, "Restauration d'une version"),
]


class FichierVersion(models.Model):
    """Historique du CONTENU d'un fichier (décision Q12 : historique consultable).

    ``numero`` ne compte que les changements de contenu ; ``Fichier.version`` (l'ETag de If-Match)
    compte aussi les renommages. La version courante est celle de plus grand ``numero`` ; elle est
    recopiée dans ``Fichier`` (nom, sha256, taille, storage_path).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fichier = models.ForeignKey(Fichier, on_delete=models.CASCADE, related_name='versions')
    numero = models.PositiveIntegerField()
    nom = models.CharField(max_length=255, help_text="Nom du fichier à cette version.")
    storage_path = models.CharField(max_length=500, unique=True)
    sha256 = models.CharField(max_length=64)
    taille = models.BigIntegerField()
    origine = models.CharField(max_length=20, choices=ORIGINE_CHOICES, default=ORIGINE_DEPOT)
    restaure_de = models.PositiveIntegerField(
        null=True, blank=True, help_text="Numéro de la version recopiée (origine = restauration).")
    depose_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='versions_fichiers_sync',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fichiers_versions'
        ordering = ['-numero']
        constraints = [
            models.UniqueConstraint(fields=['fichier', 'numero'], name='fichiers_versions_numero_uniq'),
            models.CheckConstraint(name='fichiers_versions_numero_positif', check=Q(numero__gte=1)),
            models.CheckConstraint(name='fichiers_versions_taille_positive', check=Q(taille__gte=0)),
        ]

    def __str__(self):
        return f'{self.nom} v{self.numero}'


class SyncChange(models.Model):
    seq = models.BigAutoField(primary_key=True)
    # NULL = référentiel diffusé à tous les utilisateurs authentifiés (décision Q1).
    organisation = models.ForeignKey(
        'organization.Organisation', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+',
    )
    portee = models.CharField(max_length=20, choices=PORTEE_CHOICES)
    entity_type = models.CharField(max_length=30, null=True, blank=True)
    entity_id = models.UUIDField(null=True, blank=True)
    domaine = models.CharField(max_length=20, null=True, blank=True)
    fichier = models.ForeignKey(
        Fichier, on_delete=models.SET_NULL, null=True, blank=True, related_name='changements',
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sync_changes'
        ordering = ['seq']
        indexes = [
            models.Index(fields=['organisation', 'seq'], name='sync_changes_org_seq_idx'),
        ]


class SyncDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sync_devices',
    )
    organisation = models.ForeignKey(
        'organization.Organisation', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+',
    )
    device_nom = models.CharField(max_length=120)
    last_seq = models.BigIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sync_devices'
        constraints = [
            models.UniqueConstraint(fields=['user', 'device_nom'], name='sync_devices_user_nom_uniq'),
        ]
