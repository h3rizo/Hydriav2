import unicodedata
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from apps.organization.models import Base, Compte, Ouvrage
from apps.employees.models import Employe, Poste


ABSENCE_PLANNING_TACHE_LABELS = {
    'conge',
    'jour ferie',
    'recuperation',
    'repos',
    'repos medical',
}


def _normalize_planning_guard_label(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    ascii_value = normalized.encode('ascii', 'ignore').decode('ascii')
    return ' '.join(ascii_value.lower().strip().split())


class GroupeTypeActivite(models.Model):
    """Groupe de regroupement des types d'activités (gérable depuis l'interface)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, unique=True, verbose_name="Nom du groupe")
    icone = models.CharField(max_length=50, blank=True, default='fa-layer-group', verbose_name="Icône Font Awesome")
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")
    createdat = models.DateTimeField(auto_now_add=True)
    updatedat = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'groupes_types_activites'
        ordering = ['ordre', 'nom']
        verbose_name = "Groupe de types d'activités"
        verbose_name_plural = "Groupes de types d'activités"

    def __str__(self):
        return self.nom


class TypeActivite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nomtype = models.CharField(max_length=255, verbose_name="Nom du type")
    groupe = models.ForeignKey(
        GroupeTypeActivite, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='types', verbose_name="Groupe",
    )
    createdat = models.DateTimeField(auto_now_add=True)
    updatedat = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'typesactivites'
        verbose_name = "Type d'Activit?"
        verbose_name_plural = "Types d'Activit?s"

    def __str__(self):
        return self.nomtype


class Activite(models.Model):
    """Mod?le pour les activit?s rattach?es aux types d'activit?s"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom de l'activit?")
    description = models.TextField(null=True, blank=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    est_corrective = models.BooleanField(default=False, verbose_name="Corrective")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    type_activite = models.ForeignKey(
        TypeActivite,
        on_delete=models.CASCADE,
        related_name='activites'
    )

    class Meta:
        db_table = 'activites'
        verbose_name = 'Activit?'
        verbose_name_plural = 'Activit?s'
        ordering = ['type_activite__nomtype', 'nom']

    def __str__(self):
        return f"{self.nom} ({self.type_activite.nomtype})"


class ActivitePoste(models.Model):
    FREQUENCE_CHOICES = [
        (1, 'Tous les mois'),
        (2, 'Tous les 2 mois'),
        (6, 'Tous les 6 mois'),
        (12, 'Tous les ans'),
    ]
    MODE_FREQUENCE_CHOICES = [
        ('par_employe', 'Par employ?'),
        ('par_employe_ouvrage', 'Par employ? et ouvrage'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom de l'activit? de poste")
    description = models.TextField(null=True, blank=True, verbose_name="Description")
    activite = models.ForeignKey(Activite, on_delete=models.CASCADE, related_name='activites_postes')
    poste = models.ForeignKey('employees.Poste', on_delete=models.CASCADE, related_name='activites_postes', null=True, blank=True)
    fiche_poste = models.ForeignKey(
        'employees.FichePoste',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activites_postes',
        verbose_name='Fiche de poste',
        help_text="Fiche de poste associ?e ? cette activit?"
    )
    frequence_mois = models.IntegerField(
        choices=FREQUENCE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Frequence (mois)",
        help_text="Laisser vide si aucune frequence ne s'applique."
    )
    mode_frequence = models.CharField(
        max_length=30,
        choices=MODE_FREQUENCE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Mode de frequence",
        help_text="Laisser vide si aucune frequence ne s'applique."
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'activitespostes'
        verbose_name = 'Activit? de Poste'
        verbose_name_plural = 'Activit?s de Postes'
        ordering = ['activite__nom', 'nom']

    def __str__(self):
        return f"{self.nom} ({self.activite.nom})"


class TypeDesignation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom du type de d?signation")
    description = models.TextField(null=True, blank=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'typedesignations'
        verbose_name = 'Type de D?signation'
        verbose_name_plural = 'Types de D?signations'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Planning(models.Model):
    STATUS_CHOICES = [
        ('en_cours', 'En cours'),
        ('termine', 'Termine'),
        ('annule', 'Annule'),
        ('reporte', 'Reporte'),
    ]
    PRIORITE_SUIVI_CHOICES = [
        ('basse', 'Basse'),
        ('normale', 'Normale'),
        ('haute', 'Haute'),
        ('critique', 'Critique'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Champs principaux
    date = models.DateTimeField()
    remarque = models.TextField(null=True, blank=True)
    datesignalementactivite = models.DateTimeField(null=True, blank=True)
    estvalide = models.BooleanField(null=True, blank=True)
    debitmesure = models.FloatField(null=True, blank=True)
    bilan = models.TextField(null=True, blank=True)
    suiteadonner = models.TextField(null=True, blank=True)
    priorite_suivi = models.CharField(max_length=20, choices=PRIORITE_SUIVI_CHOICES, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    statut = models.CharField(max_length=50, choices=STATUS_CHOICES, null=True, blank=True)

    # Créneaux de pointage GPS que l'employé déclare à l'avance (rappels + suivi)
    prevu_matinee = models.BooleanField(default=False, verbose_name="Prévu matinée")
    prevu_apres_midi = models.BooleanField(default=False, verbose_name="Prévu après-midi")
    prevu_nuitee = models.BooleanField(default=False, verbose_name="Prévu nuitée")

    # Nouveaux champs pour verification
    verification = models.CharField(max_length=100, null=True, blank=True, verbose_name="R?sultat v?rification")
    commentaire_verification = models.TextField(null=True, blank=True, verbose_name="Commentaire v?rification")

    # Photos du planning (stock?es en JSON)
    photo = models.TextField(null=True, blank=True, verbose_name="Photos (JSON)")

    # Relations ForeignKey correctes vers les mod?les UUID (nouvelles colonnes)
    employe = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='plannings', db_column='employe_uuid_id')
    type_activite = models.ForeignKey(TypeActivite, on_delete=models.SET_NULL, null=True, blank=True, related_name='plannings', db_column='type_activite_uuid_id')
    fiche_poste = models.ForeignKey('employees.FichePoste', on_delete=models.SET_NULL, null=True, blank=True, related_name='plannings', db_column='fiche_poste_id', verbose_name="Fiche de poste")
    ouvrage = models.ForeignKey(Ouvrage, on_delete=models.SET_NULL, null=True, blank=True, related_name='plannings', db_column='ouvrage_uuid_id')

    # Cible d'une réparation : un équipement OU un point d'eau (jamais les deux)
    # et le ou les composants concernés (catalogue du type de la cible).
    cible_equipement = models.ForeignKey(
        'infrastructure.EquipementConstitutif', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='plannings_cibles', verbose_name="Équipement ciblé",
    )
    cible_point_eau = models.ForeignKey(
        'billing.PointEau', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='plannings_cibles', verbose_name="Point d'eau ciblé",
    )
    composants_equipement = models.ManyToManyField(
        'inspections.ComposantTypeEquipement', blank=True,
        related_name='plannings', verbose_name="Composants d'équipement concernés",
    )
    composants_point_eau = models.ManyToManyField(
        'inspections.ComposantTypePointEau', blank=True,
        related_name='plannings', verbose_name="Composants de point d'eau concernés",
    )

    class Meta:
        db_table = 'plannings'
        verbose_name = 'Planning'
        verbose_name_plural = 'Plannings'
        constraints = []

    def __str__(self):
        date_str = self.date.strftime('%Y-%m-%d') if self.date else 'Sans date'
        employe_str = self.employe.nom_affichage if self.employe else 'Sans employ?'
        return f"Planning {date_str} - {employe_str}"

    @property
    def planning_date(self):
        """Retourne la date du planning"""
        return self.date.date() if self.date else None

    @property
    def employe_nom(self):
        """Retourne le nom de l'employ? (surnom si disponible)"""
        return self.employe.nom_affichage if self.employe else "Sans employ?"

    @property
    def employe_surnom(self):
        """Retourne le surnom de l'employ? ou son pr?nom si pas de surnom"""
        if self.employe:
            return self.employe.surnom or self.employe.prenom
        return "N/A"

    @property
    def type_activite_nom(self):
        """Retourne le nom du type d'activit?"""
        return self.type_activite.nomtype if self.type_activite else "Type d'activit? non d?fini"

    @property
    def activite(self):
        """Compat: remplace l'ancienne FK Activite par la fiche de poste."""
        return self.fiche_poste

    @activite.setter
    def activite(self, value):
        self.fiche_poste = value

    @property
    def activite_id(self):
        """Compat: expose l'id de fiche_poste sous l'ancien nom."""
        return self.fiche_poste_id

    @activite_id.setter
    def activite_id(self, value):
        self.fiche_poste_id = value

    @property
    def activite_display(self):
        """Retourne l'activit? ? afficher"""
        if self.fiche_poste:
            return self.fiche_poste.tache
        elif self.type_activite:
            return self.type_activite.nomtype
        else:
            return "Activit? non d?finie"

    @property
    def fiche_poste_display(self):
        """Retourne la fiche de poste associ?e au planning."""
        if hasattr(self, "_fiche_poste_display"):
            return self._fiche_poste_display

        if self.fiche_poste:
            return self.fiche_poste.tache

        if not self.employe or not self.employe.poste_id:
            return ""

        return ""

    @property
    def ouvrage_nom(self):
        """Retourne le nom de l'ouvrage"""
        if self.ouvrage:
            # organization.Ouvrage n'a que `nom_ouvrage` (infra_name/nom n'existent pas :
            # l'ancien code levait AttributeError -> 500 sur /api/mobile/v1/pointage/aujourdhui).
            return self.ouvrage.nom_ouvrage or ''
        return "Aucun ouvrage"

    @property
    def validation(self):
        """Retourne le statut de validation"""
        return self.estvalide or False

    @property
    def statut_display(self):
        """Retourne le statut d'affichage format?"""
        if self.statut:
            statut_mapping = {
                'en_cours': 'En cours',
                'termine': 'Termine',
                'annule': 'Annule',
                'reporte': 'Reporte'
            }
            return statut_mapping.get(self.statut, self.statut.title())
        elif self.estvalide:
            return 'Valid?'
        else:
            return 'En attente'

    @validation.setter
    def validation(self, value):
        """D?finit le statut de validation"""
        self.estvalide = value

    @property
    def remarques(self):
        """Retourne les remarques"""
        return self.remarque or ""

    @remarques.setter
    def remarques(self, value):
        """D?finit les remarques"""
        self.remarque = value
class PlanningEmploye(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    planning = models.ForeignKey(Planning, on_delete=models.CASCADE, related_name='planning_employees')
    employee = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='planning_participations')
    
    is_present = models.BooleanField(default=True)
    notes = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'planning_employees'
        verbose_name = 'Participation Planning'
        verbose_name_plural = 'Participations Planning'
        unique_together = ['planning', 'employee']

    def __str__(self):
        return f"{self.employee.full_name} - {self.planning.date}"


class Indemnite(models.Model):
    INDEMNITE_TYPE_CHOICES = [
        ('transport', 'Transport'),
        ('repas', 'Repas'),
        ('heures_sup', 'Heures supplémentaires'),
        ('mission', 'Mission'),
        ('prime', 'Prime'),
    ]
    
    STATUS_CHOICES = [
        ('en_attente', 'En attente'),
        ('valide', 'Validé'),
        ('paye', 'Payé'),
        ('rejete', 'Rejeté'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    indemnite_type = models.CharField(max_length=50, choices=INDEMNITE_TYPE_CHOICES)
    indemnite_amount = models.DecimalField(max_digits=10, decimal_places=2)
    indemnite_date = models.DateField()
    indemnite_description = models.TextField(null=True, blank=True)
    indemnite_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='en_attente')
    
    employee = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='indemnites')
    planning = models.ForeignKey(Planning, on_delete=models.SET_NULL, null=True, blank=True, related_name='indemnites')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'indemnites'
        verbose_name = 'Indemnité'
        verbose_name_plural = 'Indemnités'

    def __str__(self):
        return f"{self.employee.full_name} - {self.indemnite_type} - {self.indemnite_amount} Ar"


class IndemniteJournaliere(models.Model):
    """
    Modèle pour les indemnités journalières calculées automatiquement depuis le planning.
    Une indemnité est générée pour chaque jour passé sur le terrain (ouvrage non Bureau
    ou Bureau mais pas affecté à la base de l'employé).
    """
    STATUT_CHOICES = [
        ('calculee', 'Calculée'),
        ('avancee', 'Avancée'),
        ('confirmee', 'Confirmée'),
        ('imprimee', 'Imprimée'),
        ('exportee', 'Exportée vers DiameX'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relations principales
    employe = models.ForeignKey(
        Employe,
        on_delete=models.CASCADE,
        related_name='indemnites_journalieres',
        verbose_name="Employé"
    )
    date = models.DateField(verbose_name="Date")

    # Ouvrages visités ce jour (peut être plusieurs, stockés en texte concaténé)
    ouvrages_visites = models.TextField(
        verbose_name="Ouvrages visités",
        help_text="Liste des ouvrages visités ce jour (concaténés)"
    )
    ouvrages_ids = models.TextField(
        null=True, blank=True,
        verbose_name="IDs des ouvrages",
        help_text="IDs des ouvrages séparés par virgule"
    )

    # Activités du jour (concaténées)
    activites = models.TextField(
        null=True, blank=True,
        verbose_name="Activités",
        help_text="Liste des activités du jour"
    )

    # Montant de l'indemnité (basé sur tarif_indemnite du poste)
    montant = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Montant indemnité"
    )

    # Statut du workflow
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='calculee',
        verbose_name="Statut"
    )

    # DiameX
    numero_diamex = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX"
    )
    base_diamex = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Base DiameX"
    )

    # Dates de workflow
    date_avance = models.DateTimeField(null=True, blank=True, verbose_name="Date d'avance")
    date_confirmation = models.DateTimeField(null=True, blank=True, verbose_name="Date de confirmation")
    date_impression = models.DateTimeField(null=True, blank=True, verbose_name="Date d'impression")
    date_export = models.DateTimeField(null=True, blank=True, verbose_name="Date d'export DiameX")

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'indemnites_journalieres'
        verbose_name = 'Indemnité Journalière'
        verbose_name_plural = 'Indemnités Journalières'
        unique_together = ['employe', 'date']  # Une seule indemnité par employé par jour
        ordering = ['-date', 'employe__nom']
        indexes = [
            models.Index(fields=['employe', 'date']),
            models.Index(fields=['statut']),
            models.Index(fields=['-date']),
        ]

    def __str__(self):
        return f"{self.employe.nom_affichage} - {self.date} - {self.montant} Ar"

    @property
    def est_terrain(self):
        """Indique si c'est bien une journée terrain (toujours True pour ce modèle)"""
        return True


class Designation(models.Model):
    """Modèle pour les désignations utilisées dans les détails de planning"""
    NATURE_STOCK_CHOICES = [
        ('consommable', 'Consommable'),
        ('non_consommable', 'Non consommable'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom de la désignation")
    description = models.TextField(null=True, blank=True, verbose_name="Description")
    type_designation = models.ForeignKey(TypeDesignation, on_delete=models.CASCADE, related_name='designations')
    prix_unitaire = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Prix unitaire par défaut"
    )
    unite = models.CharField(max_length=50, null=True, blank=True, verbose_name="Unité de mesure")
    concerne_livraison = models.BooleanField(default=False, verbose_name="Concerne livraison")
    concerne_avance = models.BooleanField(default=False, verbose_name="Concerne avance")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    # Photo de la désignation (URL Unsplash ou autre)
    photo = models.URLField(
        max_length=500, null=True, blank=True,
        verbose_name="URL de la photo",
        help_text="URL de la photo illustrative (ex: Unsplash)"
    )
    photo_file = models.ImageField(
        upload_to='designations/', null=True, blank=True,
        verbose_name="Fichier photo",
        help_text="Upload d'une photo depuis l'ordinateur ou appareil photo"
    )

    # Nouveaux champs ajoutés
    poids_unitaire = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        verbose_name="Poids unitaire", help_text="Poids unitaire en kg"
    )
    seuil_minimum = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Seuil minimum", help_text="Seuil minimum de stock"
    )
    nature_stock = models.CharField(
        max_length=20,
        choices=NATURE_STOCK_CHOICES,
        default='consommable',
        verbose_name="Nature du stock",
        help_text="Les consommables diminuent avec l'usage. Les non consommables restent au stock et se contrôlent surtout par inventaire."
    )
    TYPE_AVANCE_CHOICES = [
        ('bon_livraison', 'Bon de livraison'),
        ('avance', 'Avance'),
        ('facture', 'Facture/Dépense'),
        ('recette', 'Recette'),
    ]
    type_avance_caissiere = models.CharField(
        max_length=20, choices=TYPE_AVANCE_CHOICES, null=True, blank=True,
        verbose_name="Type avance caissière"
    )
    code_materiel = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name="Code matériel", help_text="Code de référence du matériel"
    )
    prestation = models.BooleanField(default=False, verbose_name="Prestation")
    date_prix = models.DateField(
        null=True, blank=True,
        verbose_name="Date du prix", help_text="Date de référence du prix"
    )
    poste_acheteur = models.ForeignKey(
        Poste, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designations_achat', verbose_name="Poste acheteur"
    )

    # Photo spécimen pour la désignation
    photo_specimen = models.ForeignKey(
        'filemanager.FileUpload',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='designations_specimen',
        verbose_name="Photo spécimen",
        help_text="Photo de référence du matériel/prestation"
    )

    # Type de désignation pour les chantiers
    TYPE_DESIGNATION_CHANTIER_CHOICES = [
        ('accessoires', 'Accessoires'),
        ('materiaux_locaux', 'Matériaux locaux'),
        ('materiaux_construction', 'Matériaux de construction'),
        ('tuyau', 'Tuyau'),
    ]
    type_designation_chantier = models.CharField(
        max_length=30,
        choices=TYPE_DESIGNATION_CHANTIER_CHOICES,
        null=True,
        blank=True,
        verbose_name="Type désignation chantier",
        help_text="Catégorie pour les matériaux de chantier"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'designations'
        verbose_name = 'Désignation'
        verbose_name_plural = 'Désignations'
        ordering = ['type_designation__nom', 'nom']

    def __str__(self):
        return f"{self.nom} ({self.type_designation.nom})"

    @property
    def photo_url(self):
        """Retourne l'URL de la photo (fichier local prioritaire, sinon URL Unsplash)"""
        if self.photo_file:
            return self.photo_file.url
        return self.photo or ''


class DesignationCompte(models.Model):
    """Modèle de liaison entre Designation et Compte"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    designation = models.ForeignKey(Designation, on_delete=models.CASCADE, related_name='comptes')
    compte = models.ForeignKey(Compte, on_delete=models.CASCADE, related_name='designations')
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    notes = models.TextField(null=True, blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'designationcomptes'
        verbose_name = 'Liaison Désignation-Compte'
        verbose_name_plural = 'Liaisons Désignation-Comptes'
        unique_together = ('designation', 'compte')

    def __str__(self):
        return f"{self.designation.nom} - {self.compte.nom_compte}"


class PlanningDetail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # ForeignKey UUID vers Planning
    planning = models.ForeignKey(
        Planning,
        on_delete=models.CASCADE,
        related_name='details',
        db_column='planning_id',
        null=True,
        blank=True
    )
    designation = models.ForeignKey(
        Designation,
        on_delete=models.PROTECT,
        related_name='planning_details',
        db_column='designationid'
    )
    quantity = models.FloatField()
    pu = models.DecimalField(max_digits=15, decimal_places=2)
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    acheteur = models.CharField(max_length=100, null=True, blank=True)

    # Nouveaux champs ajoutés
    compte = models.ForeignKey(
        'organization.Compte',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planning_details',
        verbose_name="Compte comptable"
    )
    livraison = models.BooleanField(default=False, verbose_name="Livraison effectuée")
    date_livraison = models.DateField(null=True, blank=True, verbose_name="Date de livraison")
    retour = models.BooleanField(default=False, verbose_name="Retour effectué")
    date_retour = models.DateField(null=True, blank=True, verbose_name="Date de retour")
    numeroDiameXAvance = models.IntegerField(null=True, blank=True, verbose_name="Numéro DiameX Avance")
    BaseDiameXAvance = models.CharField(max_length=100, null=True, blank=True, verbose_name="Base DiameX Avance")
    numeroDiameX = models.IntegerField(null=True, blank=True, verbose_name="Numéro DiameX")
    BaseDiameX = models.CharField(max_length=100, null=True, blank=True, verbose_name="Base DiameX")

    # Nouveaux champs ajoutés pour l'import/export Excel
    equipement_constitutif = models.ForeignKey(
        'infrastructure.EquipementConstitutif',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planning_details',
        verbose_name="Équipement constitutif"
    )
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planning_details',
        verbose_name="Point d'eau"
    )
    # Champs pour le workflow terrain (agent)
    utilise = models.BooleanField(default=False, verbose_name="Utilisé sur le terrain")
    photo_justificatif = models.ForeignKey(
        'filemanager.FileUpload',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planning_details_justificatif',
        verbose_name="Photo justificatif",
        help_text="Photo prise par l'agent après utilisation"
    )
    fournisseur = models.ForeignKey(
        'billing.Fournisseur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planning_details',
        verbose_name="Fournisseur"
    )
    facture_imprimee = models.BooleanField(default=False, verbose_name="Facture imprimée")
    date_utilisation = models.DateTimeField(null=True, blank=True, verbose_name="Date d'utilisation")

    # Numéros de bons
    numero_bon_livraison = models.CharField(max_length=50, null=True, blank=True, verbose_name="N° Bon de livraison", help_text="Ex: BL-2025-001")
    numero_bon_avance = models.CharField(max_length=50, null=True, blank=True, verbose_name="N° Bon d'avance", help_text="Ex: BA-2025-001")
    numero_facture = models.CharField(max_length=50, null=True, blank=True, verbose_name="N° Facture", help_text="Ex: F-2025-001")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'planningdetails'
        verbose_name = 'Détail du Planning'
        verbose_name_plural = 'Détails du Planning'

    def __str__(self):
        return f"Détail pour Planning {self.planning.id if self.planning else 'N/A'}: {self.designation}"

    def save(self, *args, **kwargs):
        from decimal import Decimal
        # Convertir quantity en Decimal pour éviter l'erreur float * Decimal
        if self.quantity is not None and self.pu is not None:
            self.montant = Decimal(str(self.quantity)) * self.pu
        super().save(*args, **kwargs)


    def clean(self):
        super().clean()

        if not self.point_eau_id:
            return

        planning = self.planning
        point_eau = self.point_eau

        planning_tache = ''
        if planning and getattr(planning, 'fiche_poste_id', None) and getattr(planning, 'fiche_poste', None):
            planning_tache = getattr(planning.fiche_poste, 'tache', '') or ''

        normalized_tache = _normalize_planning_guard_label(planning_tache)
        if normalized_tache in ABSENCE_PLANNING_TACHE_LABELS:
            raise ValidationError({
                'point_eau': (
                    "Un planning d'absence ne doit pas avoir de point d'eau "
                    f"associe ({planning_tache or 'sans tache'})."
                )
            })

        point_eau_ouvrage_id = getattr(point_eau, 'ouvrage_id', None)
        if not point_eau_ouvrage_id:
            raise ValidationError({
                'point_eau': "Le point d'eau selectionne n'est rattache a aucun ouvrage."
            })

        if not planning:
            return

        planning_ouvrage_id = getattr(planning, 'ouvrage_id', None)
        if not planning_ouvrage_id:
            raise ValidationError({
                'point_eau': (
                    "Le planning doit etre rattache a un ouvrage avant d'associer un point d'eau."
                )
            })

        if str(planning_ouvrage_id) != str(point_eau_ouvrage_id):
            planning_ouvrage_nom = getattr(getattr(planning, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'
            point_eau_ouvrage_nom = getattr(getattr(point_eau, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'
            raise ValidationError({
                'point_eau': (
                    "Incoherence detail planning: le point d'eau appartient a "
                    f"'{point_eau_ouvrage_nom}' alors que le planning vise '{planning_ouvrage_nom}'."
                )
            })

    @property
    def deplacement_detail(self):
        return getattr(self, 'deplacement', None)

    @property
    def trajet(self):
        return getattr(self.deplacement_detail, 'trajet', None)

    @property
    def point_a(self):
        return getattr(self.deplacement_detail, 'point_a', None)

    @property
    def point_b(self):
        return getattr(self.deplacement_detail, 'point_b', None)

    @property
    def point_a_id(self):
        return getattr(self.deplacement_detail, 'point_a_id', None)

    @property
    def point_b_id(self):
        return getattr(self.deplacement_detail, 'point_b_id', None)

    @property
    def moyen_transport(self):
        return getattr(self.deplacement_detail, 'moyen_transport', None)

    def get_trajet_display(self):
        deplacement = self.deplacement_detail
        if not deplacement or not deplacement.trajet:
            return ''
        return deplacement.get_trajet_display()

    def get_moyen_transport_display(self):
        deplacement = self.deplacement_detail
        if not deplacement or not deplacement.moyen_transport:
            return ''
        return deplacement.get_moyen_transport_display()

    def save(self, *args, **kwargs):
        # Convertir quantity en Decimal pour eviter l'erreur float * Decimal
        if self.quantity is not None and self.pu is not None:
            self.montant = Decimal(str(self.quantity)) * self.pu
        self.clean()
        super().save(*args, **kwargs)


class PlanningPiece(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    planning = models.ForeignKey(
        Planning,
        on_delete=models.CASCADE,
        related_name='pieces'
    )
    fichier = models.ForeignKey(
        'filemanager.FileUpload',
        on_delete=models.CASCADE,
        related_name='planning_pieces'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'planning_pieces'
        verbose_name = 'Pièce justificative'
        verbose_name_plural = 'Pièces justificatives'


class BonLivraison(models.Model):
    """
    Table dédiée aux bons de livraison (séparée de PlanningDetail)
    Contient uniquement les informations nécessaires pour les livraisons de matériel/équipement
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation avec le planning
    planning = models.ForeignKey(
        Planning,
        on_delete=models.CASCADE,
        related_name='bons_livraison',
        verbose_name="Planning"
    )

    # Point d'eau concerné (optionnel)
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bons_livraison',
        verbose_name="Point d'eau"
    )

    # Équipement livré (optionnel)
    equipement = models.ForeignKey(
        'infrastructure.EquipementConstitutif',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bons_livraison',
        verbose_name="Équipement constitutif"
    )

    # Désignation (type de matériel/équipement)
    designation = models.ForeignKey(
        Designation,
        on_delete=models.PROTECT,
        related_name='bons_livraison',
        verbose_name="Désignation"
    )

    # Quantité livrée
    quantite = models.FloatField(verbose_name="Quantité")

    # Magasin d'origine
    magasin = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Magasin"
    )

    # Workflow terrain
    utilise = models.BooleanField(
        default=False,
        verbose_name="Livraison effectuée"
    )
    date_utilisation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de livraison terrain"
    )

    # Workflow caissière (retour)
    retour = models.BooleanField(
        default=False,
        verbose_name="Bon retourné à la caissière"
    )
    date_retour = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de retour"
    )

    # Numéro de bon généré
    numero_bon = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Numéro de bon",
        help_text="Ex: BL-2025-001"
    )

    # Photo justificatif pris par l'agent
    photo_justificatif = models.ForeignKey(
        'filemanager.FileUpload',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bons_livraison_justificatif',
        verbose_name="Photo justificatif"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bons_livraison'
        verbose_name = 'Bon de livraison'
        verbose_name_plural = 'Bons de livraison'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['planning']),
            models.Index(fields=['utilise', 'retour']),
            models.Index(fields=['numero_bon']),
        ]

    def clean(self):
        super().clean()

        if not self.point_eau_id:
            return

        planning = self.planning
        point_eau = self.point_eau

        planning_tache = ''
        if planning and getattr(planning, 'fiche_poste_id', None) and getattr(planning, 'fiche_poste', None):
            planning_tache = getattr(planning.fiche_poste, 'tache', '') or ''

        normalized_tache = _normalize_planning_guard_label(planning_tache)
        if normalized_tache in ABSENCE_PLANNING_TACHE_LABELS:
            raise ValidationError({
                'point_eau': (
                    "Un bon de livraison sur planning d'absence ne doit pas porter de point d'eau "
                    f"({planning_tache or 'sans tache'})."
                )
            })

        point_eau_ouvrage_id = getattr(point_eau, 'ouvrage_id', None)
        if not point_eau_ouvrage_id:
            raise ValidationError({
                'point_eau': "Le point d'eau selectionne n'est rattache a aucun ouvrage."
            })

        if not planning:
            return

        planning_ouvrage_id = getattr(planning, 'ouvrage_id', None)
        if not planning_ouvrage_id:
            raise ValidationError({
                'point_eau': (
                    "Le planning doit etre rattache a un ouvrage avant d'associer un point d'eau au bon."
                )
            })

        if str(planning_ouvrage_id) != str(point_eau_ouvrage_id):
            planning_ouvrage_nom = getattr(getattr(planning, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'
            point_eau_ouvrage_nom = getattr(getattr(point_eau, 'ouvrage', None), 'nom_ouvrage', '') or 'Sans ouvrage'
            raise ValidationError({
                'point_eau': (
                    "Incoherence bon de livraison: le point d'eau appartient a "
                    f"'{point_eau_ouvrage_nom}' alors que le planning vise '{planning_ouvrage_nom}'."
                )
            })

    def __str__(self):
        return f"BL {self.numero_bon or self.id} - {self.designation.nom if self.designation else 'N/A'}"

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Deplacement(models.Model):
    """Modèle pour gérer les déplacements et leurs coûts"""
    MOYEN_TRANSPORT_CHOICES = [
        ('taxi-brousse', 'Taxi-brousse'),
        ('pirogue', 'Pirogue'),
        ('bac', 'Bac'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    point_a = models.ForeignKey(
        'geography.Village',
        on_delete=models.CASCADE,
        related_name='deplacements_depart',
        verbose_name="Point de départ (Village)"
    )
    point_b = models.ForeignKey(
        'geography.Village',
        on_delete=models.CASCADE,
        related_name='deplacements_arrivee',
        verbose_name="Point d'arrivée (Village)"
    )
    moyen_transport = models.CharField(
        max_length=20,
        choices=MOYEN_TRANSPORT_CHOICES,
        verbose_name="Moyen de transport"
    )
    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix unitaire (Ar)"
    )
    date_prix = models.DateField(
        verbose_name="Date du prix",
        help_text="Date à laquelle ce prix a été relevé"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'deplacements'
        verbose_name = 'Déplacement'
        verbose_name_plural = 'Déplacements'
        ordering = ['-date_prix']
        unique_together = ('point_a', 'point_b', 'moyen_transport', 'date_prix')
        indexes = [
            models.Index(fields=['point_a', 'point_b']),
            models.Index(fields=['moyen_transport']),
            models.Index(fields=['-date_prix']),
        ]

    def __str__(self):
        point_a_nom = self.point_a.nom if hasattr(self.point_a, 'nom') else str(self.point_a)
        point_b_nom = self.point_b.nom if hasattr(self.point_b, 'nom') else str(self.point_b)
        return f"{point_a_nom} → {point_b_nom} ({self.get_moyen_transport_display()}) - {self.prix_unitaire} Ar"

class PlanningDetailDeplacement(models.Model):
    TRAJET_CHOICES = [
        ('aller', 'Aller'),
        ('retour', 'Retour'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    planning_detail = models.OneToOneField(
        'PlanningDetail',
        on_delete=models.CASCADE,
        related_name='deplacement',
        verbose_name='Detail planning',
    )
    trajet = models.CharField(max_length=20, choices=TRAJET_CHOICES, verbose_name='Trajet')
    point_a = models.ForeignKey(
        'geography.Village',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planning_detail_deplacements_point_a',
        verbose_name='Point A (Village)',
    )
    point_b = models.ForeignKey(
        'geography.Village',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planning_detail_deplacements_point_b',
        verbose_name='Point B (Village)',
    )
    moyen_transport = models.CharField(
        max_length=20,
        choices=Deplacement.MOYEN_TRANSPORT_CHOICES,
        null=True,
        blank=True,
        verbose_name='Moyen de transport',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'planningdetail_deplacements'
        verbose_name = 'Deplacement de detail planning'
        verbose_name_plural = 'Deplacements de detail planning'

    def __str__(self):
        return f"{self.planning_detail_id} - {self.get_trajet_display()}"


class DebitSourceMesure(models.Model):
    """Mesure de debit de source saisie par date de visite."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey(
        'organization.Ouvrage',
        on_delete=models.CASCADE,
        related_name='debits_source',
        db_column='ouvrage_id'
    )
    date_visite = models.DateField(verbose_name='Date de visite', db_index=True)
    debit_l_s = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        verbose_name='Debit (L/s)',
        help_text='Debit mesure a la source en litres par seconde'
    )
    remarque = models.TextField(null=True, blank=True, verbose_name='Remarque')
    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='debits_source_mesures',
        verbose_name='Employe'
    )
    created_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='debits_source_crees',
        verbose_name='Cree par'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'debits_source_mesures'
        verbose_name = 'Debit de source'
        verbose_name_plural = 'Debits de source'
        ordering = ['-date_visite', '-created_at']
        indexes = [
            models.Index(fields=['ouvrage', '-date_visite']),
            models.Index(fields=['date_visite']),
        ]

    def __str__(self):
        return f"{self.ouvrage.nom_ouvrage if self.ouvrage_id else 'Ouvrage'} - {self.date_visite} - {self.debit_l_s} L/s"


class DesignationTypeActivite(models.Model):
    """Modèle de liaison entre Designation et TypeActivite"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    designation = models.ForeignKey(Designation, on_delete=models.CASCADE, related_name='types_activites')
    type_activite = models.ForeignKey(TypeActivite, on_delete=models.CASCADE, related_name='designations')
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    notes = models.TextField(null=True, blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'designation_type_activites'
        verbose_name = 'Liaison Désignation-Type d\'Activité'
        verbose_name_plural = 'Liaisons Désignation-Types d\'Activités'
        unique_together = ('designation', 'type_activite')

    def __str__(self):
        return f"{self.designation.nom} - {self.type_activite.nomtype}"


# Import des modèles de réparations
from .models_reparations import Reparation, HistoriqueReparation
from .models_pointage import PointageGPS  # noqa: E402,F401
from .models_fusion_activites import FusionFichePosteLog  # noqa: E402,F401
from .models_couts_types import CoutTypeActivite, CoutTypeLigne  # noqa: E402,F401
from .models_terrain_points import TerrainContribution  # noqa: E402,F401
