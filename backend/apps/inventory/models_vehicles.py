"""


Modles pour la gestion du parc automobile


"""


import uuid


from decimal import Decimal


from django.db import models


from django.core.validators import MinValueValidator, MaxValueValidator


from django.conf import settings


from apps.employees.models import Employe


from apps.planning.models import Designation








class Vehicule(models.Model):


    """Modle pour grer les vhicules du parc automobile"""


    TYPE_VEHICULE_CHOICES = [


        ('voiture', 'Voiture'),


        ('moto', 'Moto'),


    ]





    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


    type_vehicule = models.CharField(max_length=20, choices=TYPE_VEHICULE_CHOICES, verbose_name="Type de vhicule")


    immatriculation = models.CharField(max_length=20, unique=True, verbose_name="Immatriculation")


    marque = models.CharField(max_length=100, verbose_name="Marque")


    modele = models.CharField(max_length=100, verbose_name="Modle")


    date_mise_circulation = models.DateField(verbose_name="Date de mise en circulation")





    # Informations complmentaires


    numero_chassis = models.CharField(max_length=50, blank=True, null=True, verbose_name="Numro de chssis")


    couleur = models.CharField(max_length=50, blank=True, null=True, verbose_name="Couleur")


    annee_fabrication = models.IntegerField(blank=True, null=True, verbose_name="Anne de fabrication")


    carte_grise = models.FileField(


        upload_to='vehicules/cartes_grises/',


        blank=True,


        null=True,


        verbose_name="Carte grise / carte rose"


    )

    photo = models.ImageField(
        upload_to='vehicules/photos/',
        blank=True,
        null=True,
        verbose_name="Photo du véhicule"
    )



    # Statut


    actif = models.BooleanField(default=True, verbose_name="Actif")


    date_retrait = models.DateField(blank=True, null=True, verbose_name="Date de retrait du parc")


    motif_retrait = models.TextField(blank=True, null=True, verbose_name="Motif de retrait")





    # Compteur kilomtrique


    index_compteur_actuel = models.DecimalField(


        max_digits=10,


        decimal_places=2,


        default=0,


        validators=[MinValueValidator(Decimal('0'))],


        verbose_name="Index compteur actuel (km)"


    )


    compteur_fonctionnel = models.BooleanField(default=True, verbose_name="Compteur fonctionnel")





    # Mtadonnes


    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de cration")


    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")


    notes = models.TextField(blank=True, null=True, verbose_name="Notes")





    class Meta:


        db_table = 'vehicules'


        verbose_name = 'Vhicule'


        verbose_name_plural = 'Vhicules'


        ordering = ['-actif', 'immatriculation']


        indexes = [


            models.Index(fields=['immatriculation']),


            models.Index(fields=['actif']),


            models.Index(fields=['type_vehicule']),


        ]





    def __str__(self):


        return f"{self.immatriculation} - {self.marque} {self.modele}"





    @property


    def nom_complet(self):


        """Nom complet du vhicule"""


        return f"{self.marque} {self.modele} ({self.immatriculation})"





    @property


    def employe_actuel(self):


        """Retourne l'employ actuellement affect au vhicule"""


        affectation = self.affectations.filter(date_fin__isnull=True).first()


        return affectation.employe if affectation else None





    @property


    def affectation_actuelle(self):


        """Retourne l'affectation actuellement active du vhicule"""


        return self.affectations.filter(date_fin__isnull=True).first()








class AffectationVehicule(models.Model):


    """Modle pour grer les affectations des vhicules aux employs"""


    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


    vehicule = models.ForeignKey(


        Vehicule,


        on_delete=models.CASCADE,


        related_name='affectations',


        verbose_name="Vhicule"


    )


    employe = models.ForeignKey(


        Employe,


        on_delete=models.CASCADE,


        related_name='affectations_vehicules',


        verbose_name="Employ"


    )


    date_debut = models.DateField(verbose_name="Date de dbut")


    date_fin = models.DateField(blank=True, null=True, verbose_name="Date de fin")





    # Mtadonnes


    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de cration")


    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")


    notes = models.TextField(blank=True, null=True, verbose_name="Notes")





    class Meta:


        db_table = 'affectations_vehicules'


        verbose_name = 'Affectation de vhicule'


        verbose_name_plural = 'Affectations de vhicules'


        ordering = ['-date_debut']


        indexes = [


            models.Index(fields=['vehicule', 'date_debut']),


            models.Index(fields=['employe', 'date_debut']),


            models.Index(fields=['date_fin']),


        ]





    def __str__(self):


        return f"{self.vehicule.immatriculation}  {self.employe.nom_complet} ({self.date_debut})"





    @property


    def est_active(self):


        """Vrifie si l'affectation est active"""


        return self.date_fin is None








class RelevéCompteur(models.Model):


    """Modle pour grer les relevs de compteur kilomtrique"""


    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


    vehicule = models.ForeignKey(


        Vehicule,


        on_delete=models.CASCADE,


        related_name='releves_compteur',


        verbose_name="Vhicule"


    )


    employe = models.ForeignKey(


        Employe,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='releves_compteur',


        verbose_name="Employ"


    )





    # Date et index


    date_releve = models.DateField(verbose_name="Date du relev")


    index_compteur = models.DecimalField(


        max_digits=10,


        decimal_places=2,


        blank=True,


        null=True,


        validators=[MinValueValidator(Decimal('0'))],


        verbose_name="Index compteur (km)",


        help_text="Laisser vide si compteur en panne"


    )

    photo_compteur = models.ImageField(
        upload_to='vehicules/releves_compteur/',
        blank=True,
        null=True,
        verbose_name="Photo compteur"
    )





    # Trajet


    lieu_depart = models.CharField(max_length=200, blank=True, null=True, verbose_name="Lieu de dpart")


    lieu_arrivee = models.CharField(max_length=200, blank=True, null=True, verbose_name="Lieu d'arrive")


    distance_parcourue = models.DecimalField(


        max_digits=10,


        decimal_places=2,


        validators=[MinValueValidator(Decimal('0'))],


        verbose_name="Distance parcourue (km)"


    )





    # Compteur en panne


    saisie_manuelle = models.BooleanField(


        default=False,


        verbose_name="Saisie manuelle",


        help_text="Cocher si le compteur est en panne"


    )





    # Mtadonnes


    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de cration")


    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")


    notes = models.TextField(blank=True, null=True, verbose_name="Notes")





    class Meta:


        db_table = 'releves_compteur_vehicules'


        verbose_name = 'Releve de compteur'


        verbose_name_plural = 'Releves de compteur'


        ordering = ['-date_releve', '-created_at']


        indexes = [


            models.Index(fields=['vehicule', 'date_releve']),


            models.Index(fields=['employe', 'date_releve']),


            models.Index(fields=['-date_releve']),


        ]





    def __str__(self):


        return f"{self.vehicule.immatriculation} - {self.date_releve} ({self.distance_parcourue} km)"





    def save(self, *args, **kwargs):


        """Mettre  jour l'index actuel du vhicule si index renseign"""


        super().save(*args, **kwargs)


        if self.index_compteur and not self.saisie_manuelle:


            if self.index_compteur > self.vehicule.index_compteur_actuel:


                self.vehicule.index_compteur_actuel = self.index_compteur


                self.vehicule.save(update_fields=['index_compteur_actuel'])








class ReparationVehicule(models.Model):


    """Modle pour grer les rparations des vhicules"""


    TYPE_REPARATION_CHOICES = [


        ('entretien', 'Entretien'),


        ('reparation', 'Rparation'),


        ('revision', 'Rvision'),


        ('depannage', 'Dpannage'),


        ('autre', 'Autre'),


    ]


    STATUT_CHOICES = [


        ('planifiee', 'Planifi?e'),


        ('commande', 'Commande initi?e'),


        ('commande_recue', 'Commande re?ue'),


        ('terminee', 'Réparation terminée'),


        ('annulee', 'Annul?e'),


    ]





    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


    vehicule = models.ForeignKey(


        Vehicule,


        on_delete=models.CASCADE,


        related_name='reparations',


        verbose_name="Vhicule"


    )





    # Informations rparation


    date_prevue = models.DateField(blank=True, null=True, verbose_name="Date Prévue de r?paration")


    date_reparation = models.DateField(blank=True, null=True, verbose_name="Date de r?paration")


    type_reparation = models.CharField(


        max_length=20,


        choices=TYPE_REPARATION_CHOICES,


        default='reparation',


        verbose_name="Type"


    )


    libelle = models.CharField(max_length=255, verbose_name="Libell de la rparation")


    description = models.TextField(blank=True, null=True, verbose_name="Description dtaille")


    statut = models.CharField(


        max_length=20,


        choices=STATUT_CHOICES,


        default='terminee',


        verbose_name="Statut"


    )


    purchase = models.ForeignKey(


        'inventory.Purchase',


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='reparations_vehicules',


        verbose_name="Commande li?e"


    )





    # Mcanicien


    nom_mecanicien = models.CharField(max_length=200, blank=True, null=True, verbose_name="Nom du mcanicien")


    garage = models.CharField(max_length=200, blank=True, null=True, verbose_name="Garage")





    # Pices utilises


    pieces_utilisees = models.TextField(blank=True, null=True, verbose_name="Pices utilises")


    cout_pieces = models.DecimalField(


        max_digits=12,


        decimal_places=2,


        default=0,


        validators=[MinValueValidator(Decimal('0'))],


        verbose_name="Cot des pices (Ar)"


    )


    cout_main_oeuvre = models.DecimalField(


        max_digits=12,


        decimal_places=2,


        default=0,


        validators=[MinValueValidator(Decimal('0'))],


        verbose_name="Cot main d'uvre (Ar)"


    )





    # Index compteur au moment de la rparation


    index_compteur = models.DecimalField(


        max_digits=10,


        decimal_places=2,


        blank=True,


        null=True,


        validators=[MinValueValidator(Decimal('0'))],


        verbose_name="Index compteur (km)"


    )





    # Mtadonnes


    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de cration")


    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")


    notes = models.TextField(blank=True, null=True, verbose_name="Notes")





    class Meta:


        db_table = 'reparations_vehicules'


        verbose_name = 'Rparation de vhicule'


        verbose_name_plural = 'Rparations de vhicules'


        ordering = ['-date_reparation']


        indexes = [


            models.Index(fields=['vehicule', '-date_reparation']),


            models.Index(fields=['-date_reparation']),


            models.Index(fields=['type_reparation']),


        ]





    def __str__(self):


        return f"{self.vehicule.immatriculation} - {self.libelle} ({self.date_reparation})"





    @property


    def cout_total(self):


        """Cot total de la rparation"""


        return self.cout_pieces + self.cout_main_oeuvre





class UtilisationPieceVehicule(models.Model):


    """Usage of vehicle parts (pieces) that impacts stock."""


    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


    vehicule = models.ForeignKey(


        Vehicule,


        on_delete=models.CASCADE,


        related_name='utilisations_pieces',


        verbose_name="Vhicule"


    )


    designation = models.ForeignKey(


        Designation,


        on_delete=models.PROTECT,


        related_name='utilisations_pieces_vehicules',


        verbose_name="Pice"


    )


    reparation = models.ForeignKey(


        'ReparationVehicule',


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='pieces_utilisees_rows',


        verbose_name="Rparation"


    )


    purchase_item = models.ForeignKey(


        'inventory.PurchaseItem',


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_pieces_vehicules',


        verbose_name="Achat associ"


    )


    magasin = models.ForeignKey(


        'organization.Magasin',


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_pieces_vehicules',


        verbose_name="Magasin"


    )


    employe = models.ForeignKey(


        Employe,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_pieces_vehicules',


        verbose_name="Employ"


    )


    quantite = models.DecimalField(


        max_digits=10,


        decimal_places=2,


        validators=[MinValueValidator(Decimal('0.01'))],


        verbose_name="Quantit utilise"


    )


    date_utilisation = models.DateField(verbose_name="Date d'utilisation")


    motif = models.TextField(blank=True, null=True, verbose_name="Motif / description")


    notes = models.TextField(blank=True, null=True, verbose_name="Notes")


    created_by = models.ForeignKey(


        settings.AUTH_USER_MODEL,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_pieces_vehicules',


        verbose_name="Cr par"


    )


    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de cration")


    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")





    class Meta:


        db_table = 'utilisations_pieces_vehicules'


        verbose_name = 'Utilisation de pices vhicule'


        verbose_name_plural = 'Utilisations de pices vhicules'


        ordering = ['-date_utilisation', '-created_at']


        indexes = [


            models.Index(fields=['vehicule', '-date_utilisation']),


            models.Index(fields=['-date_utilisation']),


        ]





    def __str__(self):


        return f"{self.vehicule.immatriculation} - {self.designation.nom} ({self.quantite})"








class UtilisationCarburantVehicule(models.Model):


    """Fuel usage linked to supplier purchases or stock movements."""


    SOURCE_CHOICES = [


        ('achat', 'Achat fournisseur'),


        ('stock', 'Stock magasin'),


    ]





    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


    vehicule = models.ForeignKey(


        Vehicule,


        on_delete=models.CASCADE,


        related_name='utilisations_carburant',


        verbose_name="Vhicule"


    )


    employe = models.ForeignKey(


        Employe,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_carburant_vehicules',


        verbose_name="Employ"


    )


    date_utilisation = models.DateField(verbose_name="Date d'utilisation")


    quantite = models.DecimalField(


        max_digits=10,


        decimal_places=2,


        validators=[MinValueValidator(Decimal('0.01'))],


        verbose_name="Quantit"


    )


    montant = models.DecimalField(


        max_digits=12,


        decimal_places=2,


        null=True,


        blank=True,


        verbose_name="Montant"


    )


    source_type = models.CharField(


        max_length=20,


        choices=SOURCE_CHOICES,


        verbose_name="Source"


    )


    purchase_item = models.ForeignKey(


        'inventory.PurchaseItem',


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_carburant_vehicules',


        verbose_name="Achat associ"


    )


    base_diamex_entry = models.ForeignKey(


        'accounting.BaseDiameX',


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_carburant_vehicules',


        verbose_name="Ligne comptable associee"


    )


    stock_movement = models.ForeignKey(


        'inventory.StockMovement',


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_carburant_vehicules',


        verbose_name="Mouvement de stock"


    )


    magasin = models.ForeignKey(


        'organization.Magasin',


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_carburant_vehicules',


        verbose_name="Magasin"


    )


    releve = models.ForeignKey(


        'inventory.RelevéCompteur',


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='carburants',


        verbose_name="Relev"


    )


    is_personnel = models.BooleanField(default=False, verbose_name="Usage personnel")


    notes = models.TextField(blank=True, null=True, verbose_name="Notes")


    created_by = models.ForeignKey(


        settings.AUTH_USER_MODEL,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_carburant_vehicules',


        verbose_name="Cr par"


    )


    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de cration")


    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")





    class Meta:


        db_table = 'utilisations_carburant_vehicules'


        verbose_name = 'Utilisation carburant vhicule'


        verbose_name_plural = 'Utilisations carburant vhicules'


        ordering = ['-date_utilisation', '-created_at']


        indexes = [


            models.Index(fields=['vehicule', '-date_utilisation']),


            models.Index(fields=['-date_utilisation']),


        ]





    def __str__(self):


        return f"{self.vehicule.immatriculation} - {self.quantite}"








class UtilisationPersoVehicule(models.Model):


    """Personal usage workflow for vehicles."""


    STATUT_CHOICES = [


        ('demande', 'Demande'),


        ('refusee', 'Refuse'),


        ('approuvee', 'Approuve'),


        ('en_cours', 'En cours'),


        ('retour_soumis', 'Retour soumis'),


        ('retour_valide', 'Retour valid'),


    ]





    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


    vehicule = models.ForeignKey(


        Vehicule,


        on_delete=models.CASCADE,


        related_name='utilisations_perso',


        verbose_name="Vhicule"


    )


    employe = models.ForeignKey(


        Employe,


        on_delete=models.CASCADE,


        related_name='utilisations_perso_vehicules',


        verbose_name="Employ demandeur"


    )


    date_debut = models.DateField(verbose_name="Date dbut")


    date_fin = models.DateField(verbose_name="Date fin")


    motif = models.TextField(blank=True, null=True, verbose_name="Motif")


    statut = models.CharField(


        max_length=30,


        choices=STATUT_CHOICES,


        default='demande',


        verbose_name="Statut"


    )


    regles_acceptees = models.BooleanField(default=False, verbose_name="Rgles acceptes")


    casque_obligatoire = models.BooleanField(default=False, verbose_name="Casque obligatoire")





    directeur = models.ForeignKey(


        Employe,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_perso_validees_directeur',


        verbose_name="Directeur"


    )


    directeur_avis = models.BooleanField(null=True, blank=True, verbose_name="Avis directeur")


    directeur_commentaire = models.TextField(blank=True, null=True, verbose_name="Commentaire directeur")


    date_avis_directeur = models.DateTimeField(blank=True, null=True, verbose_name="Date avis directeur")





    chef = models.ForeignKey(


        Employe,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_perso_validees_chef',


        verbose_name="Chef validateur"


    )


    chef_commentaire = models.TextField(blank=True, null=True, verbose_name="Commentaire chef")


    date_validation_chef = models.DateTimeField(blank=True, null=True, verbose_name="Date validation chef")





    carburant_avant = models.ForeignKey(


        UtilisationCarburantVehicule,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_perso_avant',


        verbose_name="Carburant avant"


    )


    carburant_apres = models.ForeignKey(


        UtilisationCarburantVehicule,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_perso_apres',


        verbose_name="Carburant aprs"


    )





    created_by = models.ForeignKey(


        settings.AUTH_USER_MODEL,


        on_delete=models.SET_NULL,


        null=True,


        blank=True,


        related_name='utilisations_perso_vehicules',


        verbose_name="Cr par"


    )


    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de cration")


    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")





    class Meta:


        db_table = 'utilisations_perso_vehicules'


        verbose_name = 'Utilisation personnelle vhicule'


        verbose_name_plural = 'Utilisations personnelles vhicules'


        ordering = ['-created_at']


        indexes = [


            models.Index(fields=['vehicule', '-created_at']),


            models.Index(fields=['employe', '-created_at']),


            models.Index(fields=['statut']),


        ]





    def __str__(self):


        return f"{self.vehicule.immatriculation} - {self.employe.nom_complet} ({self.statut})"


class ClotureCarburantMois(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mois = models.IntegerField()
    annee = models.IntegerField()
    override_directeur = models.BooleanField(default=False)
    commentaire = models.TextField(blank=True, null=True)
    cloture_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clotures_carburant_mensuelles'
    )
    date_cloture = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'clotures_carburant_mensuelles'
        unique_together = [('mois', 'annee')]
        ordering = ['-annee', '-mois']

    def __str__(self):
        return f"{self.mois:02d}/{self.annee}"







class CarnetBordMensuelScan(models.Model):
    """Scan mensuel du carnet de bord par vehicule."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicule = models.ForeignKey(
        Vehicule,
        on_delete=models.CASCADE,
        related_name='carnets_bord_scans',
        verbose_name="Vehicule",
    )
    mois = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name="Mois",
    )
    annee = models.PositiveIntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
        verbose_name="Annee",
    )
    fichier_scan = models.FileField(
        upload_to='vehicules/carnets_bord/',
        verbose_name="Scan carnet",
    )
    commentaire = models.TextField(blank=True, null=True, verbose_name="Commentaire")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='carnets_bord_vehicules_uploades',
        verbose_name="Charge par",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de creation")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'vehicules_carnets_bord_scans'
        verbose_name = 'Scan carnet de bord vehicule'
        verbose_name_plural = 'Scans carnets de bord vehicules'
        ordering = ['-annee', '-mois', 'vehicule__immatriculation', '-updated_at']
        unique_together = [('vehicule', 'annee', 'mois')]
        indexes = [
            models.Index(fields=['annee', 'mois']),
            models.Index(fields=['vehicule', 'annee', 'mois']),
            models.Index(fields=['-updated_at']),
        ]

    def __str__(self):
        return f"{self.vehicule.immatriculation} - {self.mois:02d}/{self.annee}"


class RapportConsommationCarburantScan(models.Model):
    """Scan du rapport mensuel de consommation carburant par base."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base = models.ForeignKey(
        'organization.Base',
        on_delete=models.CASCADE,
        related_name='rapports_consommation_carburant_scans',
        verbose_name="Base",
    )
    mois = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name="Mois",
    )
    annee = models.PositiveIntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
        verbose_name="Annee",
    )
    fichier_scan = models.FileField(
        upload_to='vehicules/rapports_consommation_carburant/',
        verbose_name="Scan rapport signe",
    )
    commentaire = models.TextField(blank=True, null=True, verbose_name="Commentaire")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rapports_consommation_carburant_uploades',
        verbose_name="Charge par",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de creation")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'vehicules_rapports_consommation_carburant_scans'
        verbose_name = 'Scan rapport consommation carburant'
        verbose_name_plural = 'Scans rapports consommation carburant'
        ordering = ['-annee', '-mois', 'base__nom_base', '-updated_at']
        unique_together = [('base', 'annee', 'mois')]
        indexes = [
            models.Index(fields=['base', 'annee', 'mois']),
            models.Index(fields=['annee', 'mois']),
            models.Index(fields=['-updated_at']),
        ]

    def __str__(self):
        return f"{self.base.nom_base} - {self.mois:02d}/{self.annee}"


class RapportConsommationCarburantRemarque(models.Model):
    """Remarque mensuelle par vehicule pour le rapport consommation carburant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base = models.ForeignKey(
        'organization.Base',
        on_delete=models.CASCADE,
        related_name='rapports_consommation_carburant_remarques',
        verbose_name="Base",
    )
    vehicule = models.ForeignKey(
        Vehicule,
        on_delete=models.CASCADE,
        related_name='rapports_consommation_carburant_remarques',
        verbose_name="Vehicule",
    )
    mois = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name="Mois",
    )
    annee = models.PositiveIntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
        verbose_name="Annee",
    )
    remarque = models.TextField(blank=True, null=True, verbose_name="Remarque")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rapports_consommation_carburant_remarques_modifiees',
        verbose_name="Modifie par",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'vehicules_rapports_consommation_carburant_remarques'
        verbose_name = 'Remarque rapport consommation carburant'
        verbose_name_plural = 'Remarques rapport consommation carburant'
        ordering = ['base__nom_base', 'vehicule__immatriculation', '-annee', '-mois']
        unique_together = [('base', 'vehicule', 'annee', 'mois')]
        indexes = [
            models.Index(fields=['base', 'annee', 'mois']),
            models.Index(fields=['vehicule', 'annee', 'mois']),
        ]

    def __str__(self):
        return f"{self.base.nom_base} - {self.vehicule.immatriculation} ({self.mois:02d}/{self.annee})"
