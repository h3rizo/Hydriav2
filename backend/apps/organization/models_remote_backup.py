from django.db import models
import uuid


class Organisation(models.Model):
    """Modèle représentant les organisations gestionnaires des ouvrages"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_organisation = models.CharField(max_length=255, verbose_name="Nom de l'organisation")
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

    class Meta:
        db_table = 'ouvrages'
        verbose_name = 'Ouvrage'
        verbose_name_plural = 'Ouvrages'
        ordering = ['nom_ouvrage']

    def __str__(self):
        return self.nom_ouvrage


class Base(models.Model):
    """Modèle représentant les bases opérationnelles des organisations"""
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
    prog_diamex = models.CharField(max_length=255, null=True, blank=True, verbose_name="Programme Diamex")

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