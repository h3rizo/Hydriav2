from django.core.exceptions import ValidationError
from django.db import models
import uuid
import os
import re
import unicodedata


class Organisation(models.Model):
    """Modèle représentant les organisations."""
    TYPE_GESTIONNAIRE = 'gestionnaire'
    TYPE_PARTENAIRE = 'partenaire'
    TYPE_ORGANISATION_CHOICES = [
        (TYPE_GESTIONNAIRE, 'Gestionnaire'),
        (TYPE_PARTENAIRE, 'Partenaire'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_organisation = models.CharField(max_length=255, verbose_name="Nom de l'organisation")
    type_organisation = models.CharField(
        max_length=30,
        choices=TYPE_ORGANISATION_CHOICES,
        default=TYPE_GESTIONNAIRE,
        db_index=True,
        verbose_name="Type d'organisation"
    )
    adresse1 = models.CharField(max_length=255, null=True, blank=True, verbose_name="Adresse ligne 1")
    adresse2 = models.CharField(max_length=255, null=True, blank=True, verbose_name="Adresse ligne 2")
    code_postal = models.CharField(max_length=20, null=True, blank=True, verbose_name="Code postal")
    localite = models.CharField(max_length=255, null=True, blank=True, verbose_name="Localité")
    province = models.CharField(max_length=255, null=True, blank=True, verbose_name="Province")
    nif = models.CharField(max_length=50, null=True, blank=True, verbose_name="Numéro NIF")
    stat = models.CharField(max_length=50, null=True, blank=True, verbose_name="Numéro STAT")
    numero_cnaps = models.CharField(max_length=50, null=True, blank=True, verbose_name="Numéro CNAPS")
    tarif_carte_sociale = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Tarif carte sociale"
    )
    tarif_demande = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Tarif de demande"
    )
    tarif_minimum_bp = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Tarif minimum BP"
    )
    tarif_devis_bp = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Tarif devis BP",
        help_text="Montant du devis de branchement privé"
    )
    tarif_metre_supplementaire = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Tarif mètre supplémentaire",
        help_text="Coût par mètre supplémentaire pour les BP au-delà de la distance standard"
    )
    plafond_soins_simples = models.FloatField(
        null=True, blank=True,
        verbose_name="Plafond soins simples",
        help_text="Montant maximum pour les soins médicaux simples"
    )
    plafond_lunettes = models.FloatField(
        null=True, blank=True,
        verbose_name="Plafond lunettes",
        help_text="Montant maximum pour l'achat de lunettes"
    )
    telephone = models.CharField(max_length=20, null=True, blank=True, verbose_name="Téléphone")
    mail = models.EmailField(null=True, blank=True, verbose_name="Email")
    logo = models.ImageField(
        upload_to='logos/organisations/', null=True, blank=True,
        verbose_name="Logo de l'organisation"
    )

    class Meta:
        db_table = 'organisations'
        verbose_name = 'Organisation'
        verbose_name_plural = 'Organisations'
        ordering = ['nom_organisation']

    def __str__(self):
        return self.nom_organisation

    @property
    def is_gestionnaire(self):
        return self.type_organisation == self.TYPE_GESTIONNAIRE

    @property
    def is_partenaire(self):
        return self.type_organisation == self.TYPE_PARTENAIRE


class PartenaireGestionnaireAffectation(models.Model):
    """Affectation des organisations gestionnaires vers une organisation partenaire."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partenaire = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='affectations_gestionnaires',
        verbose_name='Organisation partenaire'
    )
    gestionnaire = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='affectations_partenaires',
        verbose_name='Organisation gestionnaire'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'partenaire_gestionnaire_affectations'
        verbose_name = 'Affectation partenaire/gestionnaire'
        verbose_name_plural = 'Affectations partenaires/gestionnaires'
        ordering = ['partenaire__nom_organisation', 'gestionnaire__nom_organisation']
        constraints = [
            models.UniqueConstraint(
                fields=['partenaire', 'gestionnaire'],
                name='unique_partenaire_gestionnaire_affectation'
            )
        ]

    def clean(self):
        if self.partenaire_id == self.gestionnaire_id:
            raise ValidationError("Une organisation ne peut pas être affectée à elle-même.")

        if self.partenaire and not self.partenaire.is_partenaire:
            raise ValidationError("L'organisation partenaire doit être de type Partenaire.")

        if self.gestionnaire and not self.gestionnaire.is_gestionnaire:
            raise ValidationError("L'organisation affectée doit être de type Gestionnaire.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.partenaire.nom_organisation} -> {self.gestionnaire.nom_organisation}"


class TypeOuvrage(models.Model):
    """Modèle représentant les types d'ouvrages (puits, forage, etc.)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_type_ouvrage = models.CharField(max_length=255, verbose_name="Nom du type d'ouvrage")
    existe = models.BooleanField(
        default=True,
        verbose_name="Existe",
        help_text="Indique si ce type d'ouvrage existe physiquement ou est juste théorique"
    )

    class Meta:
        db_table = 'type_ouvrages'
        verbose_name = "Type d'ouvrage"
        verbose_name_plural = "Types d'ouvrages"
        ordering = ['nom_type_ouvrage']

    def __str__(self):
        return self.nom_type_ouvrage


class Ouvrage(models.Model):
    """Modèle représentant les ouvrages d'approvisionnement en eau"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_ouvrage = models.CharField(max_length=255, verbose_name="Nom de l'ouvrage")
    type_ouvrage = models.ForeignKey(
        TypeOuvrage,
        on_delete=models.PROTECT,
        related_name='ouvrages',
        db_column='type_ouvrage_id'
    )
    ouvrage_source = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ouvrages_extensions',
        verbose_name="Ouvrage AEPG source",
        help_text="Ouvrage AEPG dont la source est partagee avec cet ouvrage extension."
    )
    annee_realisation = models.IntegerField(
        null=True, blank=True,
        verbose_name="Année de réalisation"
    )
    annee_realisation_avant = models.IntegerField(
        null=True, blank=True,
        verbose_name="Année de réalisation antérieure"
    )
    intervenant = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name="Intervenant/Constructeur"
    )
    observation = models.TextField(null=True, blank=True, verbose_name="Observations")
    idxlsx = models.IntegerField(null=True, blank=True, verbose_name="IDxls")
    saisonnier = models.BooleanField(default=False, verbose_name="Ouvrage saisonnier")
    photo = models.TextField(null=True, blank=True, verbose_name="Photos (JSON)")
    marque_non_fonctionnel = models.BooleanField(
        default=False,
        verbose_name="Marqué non fonctionnel (manuel)",
        help_text=(
            "Case à cocher manuelle : l'ouvrage est déclaré non fonctionnel. "
            "Ignorée/non modifiable si un chantier actif existe pour cet ouvrage "
            "(le chantier fait alors foi)."
        ),
    )

    class Meta:
        db_table = 'ouvrages'
        verbose_name = 'Ouvrage'
        verbose_name_plural = 'Ouvrages'
        ordering = ['nom_ouvrage']

    def __str__(self):
        return self.nom_ouvrage

    @property
    def ouvrage_source_effectif(self):
        type_nom = str(getattr(self.type_ouvrage, 'nom_type_ouvrage', '') or '').strip().lower()
        if type_nom == 'aepg extension' and self.ouvrage_source_id:
            return self.ouvrage_source
        return self


def normaliser_alias_ouvrage(value):
    """Clé stable de comparaison : casse Unicode et espaces ignorés."""
    value = unicodedata.normalize('NFKC', str(value or ''))
    return re.sub(r'\s+', '', value).casefold()


class OuvrageAlias(models.Model):
    """Faute ou variante connue permettant de retrouver un ouvrage officiel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey(
        Ouvrage,
        on_delete=models.CASCADE,
        related_name='aliases_extraction',
    )
    alias = models.CharField(max_length=255, verbose_name="Erreur ou variante")
    alias_normalise = models.CharField(
        max_length=255,
        unique=True,
        editable=False,
        verbose_name="Clé normalisée",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ouvrage_aliases'
        ordering = ['ouvrage__nom_ouvrage', 'alias']
        verbose_name = "Alias d'ouvrage"
        verbose_name_plural = "Alias d'ouvrages"

    def clean(self):
        super().clean()
        self.alias = str(self.alias or '').strip()
        self.alias_normalise = normaliser_alias_ouvrage(self.alias)
        if not self.alias_normalise:
            raise ValidationError({'alias': "L'alias ne peut pas être vide."})

        duplicate = OuvrageAlias.objects.filter(
            alias_normalise=self.alias_normalise
        ).exclude(pk=self.pk).select_related('ouvrage').first()
        if duplicate:
            raise ValidationError({
                'alias': (
                    f'Cette erreur est déjà attribuée à l\'ouvrage '
                    f'"{duplicate.ouvrage.nom_ouvrage}".'
                )
            })

        for ouvrage in Ouvrage.objects.only('id', 'nom_ouvrage'):
            if normaliser_alias_ouvrage(ouvrage.nom_ouvrage) != self.alias_normalise:
                continue
            if ouvrage.id == self.ouvrage_id:
                raise ValidationError({
                    'alias': "Cette variante correspond déjà au nom officiel de l'ouvrage."
                })
            raise ValidationError({
                'alias': (
                    f'Cette variante correspond au nom officiel de l\'ouvrage '
                    f'"{ouvrage.nom_ouvrage}" et ne peut pas être attribuée ailleurs.'
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.alias} → {self.ouvrage.nom_ouvrage}'


def ouvrage_dossier_technique_upload_to(instance, filename):
    """Chemin de stockage, limité à 100 caractères (max_length par défaut du FileField).

    Seul le nom stocké est raccourci ; le nom complet reste dans `nom_affichage`.
    """
    prefixe = f"ouvrages/dossiers_techniques/{instance.ouvrage_id}/"
    racine, extension = os.path.splitext(os.path.basename(filename))
    # marge : Django ajoute « _xxxxxxx » (8 caractères) quand le nom existe déjà
    place = max(100 - len(prefixe) - len(extension) - 8, 10)
    return f"{prefixe}{racine[:place]}{extension}"


class OuvrageDossierTechnique(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey(
        Ouvrage,
        on_delete=models.CASCADE,
        related_name='dossiers_techniques',
        db_column='ouvrage_id',
        verbose_name='Ouvrage',
    )
    fichier = models.FileField(
        upload_to=ouvrage_dossier_technique_upload_to,
        verbose_name='Fichier',
    )
    nom_affichage = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Nom d affichage',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ouvrage_dossiers_techniques'
        verbose_name = 'Dossier technique ouvrage'
        verbose_name_plural = 'Dossiers techniques ouvrages'
        ordering = ['-created_at', 'nom_affichage']

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.nom_affichage:
            return self.nom_affichage
        return os.path.basename(self.fichier.name) if self.fichier else 'Fichier'

    @property
    def preview_kind(self):
        extension = os.path.splitext(self.display_name or '')[1].lower()
        if extension in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}:
            return 'image'
        if extension == '.pdf':
            return 'pdf'
        if extension in {'.docx', '.xlsx', '.csv', '.txt'}:
            return 'document'
        return ''

    @property
    def can_preview(self):
        return bool(self.preview_kind)


class OuvrageDossierTechniqueChecklist(models.Model):
    """Documents couverts par le dossier technique d'un ouvrage AEPG."""
    ouvrage = models.OneToOneField(
        Ouvrage,
        on_delete=models.CASCADE,
        related_name='dossier_technique_checklist',
        db_column='ouvrage_id',
        primary_key=True,
        verbose_name='Ouvrage',
    )
    plan_reseau = models.BooleanField(default=False, verbose_name='Plan de réseau')
    fiche_technique = models.BooleanField(default=False, verbose_name="Fiche technique de l'ouvrage")
    profils = models.BooleanField(default=False, verbose_name='Profils entre les équipements et points d’eau')
    dimensionnement_citernes = models.BooleanField(default=False, verbose_name='Dimensionnement des citernes')
    devis_materiaux = models.BooleanField(default=False, verbose_name='Devis des matériaux')
    devis_main_oeuvre = models.BooleanField(default=False, verbose_name='Devis de main-d’œuvre')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ouvrage_dossier_technique_checklists'
        verbose_name = 'État du dossier technique AEPG'
        verbose_name_plural = 'États des dossiers techniques AEPG'

    def __str__(self):
        return f'Dossier technique - {self.ouvrage}'


class OuvrageGradingAnnuel(models.Model):
    """Stockage du grading des ouvrages par annee."""
    GRADE_CHOICES = [
        ('A', 'A'),
        ('B', 'B'),
        ('B_PANNE', 'B PANNE'),
        ('C', 'C'),
        ('D', 'D'),
        ('D_PANNE', 'D PANNE'),
    ]

    SOURCE_CHOICES = [
        ('manuel', 'Manuel'),
        ('import_excel', 'Import Excel'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey(
        Ouvrage,
        on_delete=models.CASCADE,
        related_name='gradings_annuels',
        db_column='ouvrage_id'
    )
    annee = models.PositiveIntegerField(verbose_name='Annee')
    grade = models.CharField(max_length=20, choices=GRADE_CHOICES, verbose_name='Grade')
    observation = models.TextField(null=True, blank=True, verbose_name='Observation')
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='manuel',
        verbose_name='Source'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ouvrage_gradings_annuels'
        verbose_name = 'Grading annuel ouvrage'
        verbose_name_plural = 'Gradings annuels ouvrages'
        ordering = ['-annee', 'ouvrage__nom_ouvrage']
        constraints = [
            models.UniqueConstraint(
                fields=['ouvrage', 'annee'],
                name='unique_ouvrage_grading_annuel'
            )
        ]

    def __str__(self):
        return f"{self.ouvrage.nom_ouvrage} - {self.annee} - {self.grade}"


class Base(models.Model):
    """Modèle représentant les bases opérationnelles des organisations"""
    @property
    def lieu_depart(self):
        """(longitude, latitude, libellé) du lieu de départ des déplacements, ou None.

        La position GPS saisie prime ; sinon on prend les coordonnées du village de départ.
        """
        if self.latitude_depart is not None and self.longitude_depart is not None:
            libelle = self.village_depart.nom_village if self.village_depart_id else self.nom_base
            return float(self.longitude_depart), float(self.latitude_depart), libelle
        village = self.village_depart if self.village_depart_id else None
        if village is not None and village.latitude is not None and village.longitude is not None:
            return float(village.longitude), float(village.latitude), village.nom_village
        return None

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_base = models.CharField(max_length=255, verbose_name="Nom de la base")
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='bases',
        db_column='organisation_id'
    )
    ouvrage = models.ForeignKey(
        Ouvrage,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases',
        db_column='ouvrage_id'
    )
    ouvrage_correspondant = models.ForeignKey(
        Ouvrage,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases_correspondant',
        verbose_name="Ouvrage correspondant",
        help_text="Ouvrage lié à cette base"
    )
    volet = models.CharField(max_length=100, null=True, blank=True, verbose_name="Volet d'activité")
    telephone = models.CharField(max_length=20, null=True, blank=True, verbose_name="Numéro de téléphone")
    prog_diamex = models.CharField(max_length=255, null=True, blank=True, verbose_name="Programme Diamex")

    # Lieu de départ des déplacements des agents de cette base (calcul des trajets, durées, contrôle des frais).
    # Un village n'existe pas toujours (base en ville) : la position GPS prime quand elle est renseignée.
    village_depart = models.ForeignKey(
        'geography.Village',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases_depart',
        verbose_name="Village de départ",
        help_text="Village d'où partent les agents de cette base (facultatif si la position GPS est renseignée)"
    )
    latitude_depart = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        verbose_name="Latitude du lieu de départ", help_text="Ex. -18.9332847"
    )
    longitude_depart = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        verbose_name="Longitude du lieu de départ", help_text="Ex. 47.5360256"
    )

    # Configuration Google Drive pour import DiameX
    google_drive_folder_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="ID Dossier Google Drive",
        help_text="ID du dossier Google Drive pour accéder aux fichiers DiameX (ex: 03 COMPTA)"
    )
    google_drive_folder_path = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Chemin Dossier Google Drive",
        help_text="Chemin complet du dossier (ex: SKJ VAVATENINA/03 COMPTA)"
    )
    google_drive_actif = models.BooleanField(
        default=False,
        verbose_name="Google Drive Actif",
        help_text="Activer l'import depuis Google Drive pour cette base"
    )

    # Relations avec Journal et Comptes
    journal_retour = models.ForeignKey(
        'Journal',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases_retour',
        verbose_name="Journal de retour",
        db_column='journal_retour_id'
    )
    compte_avance = models.ForeignKey(
        'Compte',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases_avance',
        verbose_name="Compte avance"
    )
    compte_indemnites = models.ForeignKey(
        'Compte',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases_indemnites',
        verbose_name="Compte indemnités"
    )
    compte_frais_deplacement = models.ForeignKey(
        'Compte',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases_frais_deplacement',
        verbose_name="Compte frais déplacement"
    )
    compte_demande_bp = models.ForeignKey(
        'Compte',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases_demande_bp',
        verbose_name="Compte demande BP"
    )
    compte_facture_volumetrique = models.ForeignKey(
        'Compte',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases_facture_volumetrique',
        verbose_name="Compte facture volumétrique"
    )
    compte_conso_carte_sociale = models.ForeignKey(
        'Compte',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bases_conso_carte_sociale',
        verbose_name="Compte consommation carte sociale"
    )

    class Meta:
        db_table = 'bases'
        verbose_name = 'Base'
        verbose_name_plural = 'Bases'
        ordering = ['organisation__nom_organisation', 'nom_base']

    def __str__(self):
        return f"{self.nom_base} ({self.organisation.nom_organisation})"


class Magasin(models.Model):
    """Modèle représentant les magasins de stockage rattachés aux bases"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_magasin = models.CharField(max_length=255, verbose_name="Nom du magasin")
    base = models.ForeignKey(
        Base,
        on_delete=models.CASCADE,
        related_name='magasins',
        db_column='base_id'
    )

    class Meta:
        db_table = 'magasins'
        verbose_name = 'Magasin'
        verbose_name_plural = 'Magasins'
        ordering = ['base__nom_base', 'nom_magasin']

    def __str__(self):
        return f"{self.nom_magasin} ({self.base.nom_base})"


class Journal(models.Model):
    """Modèle représentant les journaux comptables rattachés aux bases"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_journal = models.CharField(max_length=255, verbose_name="Nom du journal")
    compte = models.CharField(max_length=100, null=True, blank=True, verbose_name="Compte associé")
    code = models.CharField(max_length=50, null=True, blank=True, verbose_name="Code du journal")
    base = models.ForeignKey(
        Base,
        on_delete=models.CASCADE,
        related_name='journaux',
        db_column='base_id'
    )

    class Meta:
        db_table = 'journaux'
        verbose_name = 'Journal'
        verbose_name_plural = 'Journaux'
        ordering = ['base__nom_base', 'nom_journal']

    def __str__(self):
        return f"{self.nom_journal} ({self.base.nom_base})"


class Compte(models.Model):
    """Modèle représentant les comptes comptables des organisations"""
    FINANCEMENT_CHOICES = [
        ('', 'Aucun contrôle'),
        ('RL Activités', 'RL Activités'),
        ('FAN', 'FAN'),
        ('MEB', 'MEB'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_compte = models.CharField(max_length=255, verbose_name="Nom du compte")
    compte = models.CharField(max_length=100, null=True, blank=True, verbose_name="Numéro de compte")
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='comptes',
        db_column='organisation_id'
    )
    detail = models.TextField(null=True, blank=True, verbose_name="Détails du compte")
    financement = models.CharField(
        max_length=50,
        choices=FINANCEMENT_CHOICES,
        blank=True,
        default='',
        verbose_name="Financement attendu",
        help_text="Valeur attendue dans la colonne Fin des saisies DiameX pour ce compte"
    )
    a_recouper_hydria_diamex = models.BooleanField(
        default=False,
        verbose_name="À recouper Hydria/Diamex"
    )
    achat = models.BooleanField(default=False, verbose_name="Compte d'achat")
    fournisseur_obligatoire = models.BooleanField(
        default=False,
        verbose_name="Fournisseur obligatoire",
        help_text="Si coché, un fournisseur doit être spécifié pour ce compte"
    )
    employe_obligatoire = models.BooleanField(
        default=False,
        verbose_name="Compte employé",
        help_text="Si coché, ce compte est réservé aux paiements employés (salaires, charges sociales, etc.)"
    )
    compte_vehicule = models.BooleanField(
        default=False,
        verbose_name="Compte véhicule",
        help_text="Si coché, ce compte porte des dépenses de véhicule (carburant, entretien) réparties sur les ouvrages via le conducteur"
    )
    compte_ouvrage_analyse = models.BooleanField(
        default=False,
        verbose_name="Compte à répartir sur un ouvrage (analyse des coûts)",
        help_text=(
            "Si coché, la dépense est affectée à l'ouvrage identifié dans le libellé "
            "UNIQUEMENT pour l'analyse des coûts par ouvrage. Sans effet sur le contrôle DiameX "
            "(contrairement à « Nécessite ouvrage »)."
        )
    )

    # Charte de vérification pour les descriptions DiameX
    CHARTE_CHOICES = [
        ('', 'Aucune vérification'),
        ('allocation_familiale', 'Allocation familiale employés (648200)'),
        ('baf', 'BAF - Budget Activités Fonctionnement (748100)'),
        ('installation_bp', 'Installation Branchement Privé (748201)'),
        ('taxe_communale', 'Taxe communale (635201)'),
        ('cartes_sociales', 'Cartes sociales (748415)'),
        ('paiement_volume', 'Paiement au volume (707401)'),
        ('paiement_forfaitaire', 'Paiement forfaitaire (748411)'),
        ('indemnite_rbf_savon', 'Indemnité RBF/Savon (621102)'),
        ('indemnite_hors_zone', 'Indemnité Hors zone (625107)'),
        ('indemnite_terrain', 'Indemnité Terrain (625107)'),
    ]
    charte_verification = models.CharField(
        max_length=50,
        choices=CHARTE_CHOICES,
        blank=True,
        default='',
        verbose_name="Charte de vérification",
        help_text="Format de description attendu pour ce compte"
    )

    # Nature de déclaration pour la déclaration de communication aux impôts
    nature_declaration = models.ForeignKey(
        'accounting.ConfigDeclarationCommunication',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comptes',
        verbose_name="Nature de déclaration",
        help_text="Nature pour la déclaration de communication aux impôts (Fournitures, Matériaux, etc.)"
    )

    # Indique si ce compte nécessite qu'un ouvrage soit extrait de la description
    necessite_ouvrage = models.BooleanField(
        default=False,
        verbose_name="Nécessite ouvrage",
        help_text="Si coché, ce compte nécessite qu'un ouvrage soit identifié dans la description (ex: paiements volumétriques, cartes sociales, etc.)"
    )

    class Meta:
        db_table = 'comptes'
        verbose_name = 'Compte'
        verbose_name_plural = 'Comptes'
        ordering = ['organisation__nom_organisation', 'nom_compte']

    def __str__(self):
        return f"{self.nom_compte} ({self.organisation.nom_organisation})"


class CompteTable(models.Model):
    """
    Modèle représentant les tables où un compte peut apparaître.
    Permet de définir pour chaque compte les tables dans lesquelles il peut être utilisé.
    """
    TABLES_CHOICES = [
        ('plannings_details', 'Planning Details'),
        ('releves', 'Relevés'),
        ('salaires', 'Salaires'),
        ('indemnites', 'Indemnités'),
        ('frais_medicaux', 'Frais Médicaux'),
        ('frais_scolarite', 'Frais de Scolarité'),
        ('achats', 'Achats'),
        ('points_eau', 'Points d\'eau'),
        ('conso_carte_sociale', 'Consommations Carte Sociale'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compte = models.ForeignKey(
        Compte,
        on_delete=models.CASCADE,
        related_name='tables_autorisees',
        verbose_name="Compte"
    )
    nom_table = models.CharField(
        max_length=100,
        choices=TABLES_CHOICES,
        verbose_name="Nom de la table"
    )
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Indique si cette relation est active"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'comptes_tables'
        verbose_name = 'Table autorisée pour compte'
        verbose_name_plural = 'Tables autorisées pour comptes'
        unique_together = ('compte', 'nom_table')
        ordering = ['compte__nom_compte', 'nom_table']

    def __str__(self):
        return f"{self.compte.nom_compte} → {self.get_nom_table_display()}"


class GPSDataQualityReview(models.Model):
    """Décision humaine conservée pour une anomalie GPS détectée automatiquement."""

    ENTITY_CHOICES = (('point_eau', "Point d'eau"), ('equipement', 'Équipement'))
    STATUS_CHOICES = (
        ('confirmed', 'Position correcte et expliquée'),
        ('to_correct', 'Correction nécessaire'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity_type = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    entity_id = models.UUIDField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    explanation = models.TextField(blank=True, default='')
    latitude_snapshot = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    longitude_snapshot = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    distance_km_snapshot = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    reference_village = models.ForeignKey(
        'geography.Village', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gps_quality_reviews',
    )
    reviewed_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gps_quality_reviews',
    )
    reviewed_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gps_data_quality_reviews'
        unique_together = ('entity_type', 'entity_id')
        indexes = [
            models.Index(fields=['entity_type', 'status'], name='gps_quality_entity_status_idx'),
            models.Index(fields=['entity_id'], name='gps_quality_entity_id_idx'),
        ]

    def __str__(self):
        return f'{self.get_entity_type_display()} {self.entity_id} - {self.get_status_display()}'
