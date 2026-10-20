from django.db import models
from django.utils import timezone
import uuid
from apps.geography.models import Village
from apps.organization.models import TypeOuvrage, Ouvrage
from apps.employees.models import Employe
from apps.filemanager.models import FileUpload


class Tacheron(models.Model):
    """Tâcherons intervenant sur les chantiers"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    nom = models.CharField(
        max_length=255,
        verbose_name="Nom complet du tâcheron"
    )
    numero_cin = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Numéro CIN"
    )
    date_delivrance_cin = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de délivrance CIN"
    )
    lieu_delivrance_cin = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Lieu de délivrance CIN"
    )
    numero_nif = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Numéro NIF"
    )
    numero_stat = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Numéro STAT"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'tacherons'
        verbose_name = "Tâcheron"
        verbose_name_plural = "Tâcherons"
        ordering = ['nom']

    def __str__(self):
        return self.nom


class DemandeVillage(models.Model):
    """Demandes de travaux des villages"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    STATUT_CHOICES = [
        ('demande', 'Demande'),
        ('source_non_validee', 'Source non validée'),
        ('source_validee', 'Source validée'),
        ('preparation_en_cours', 'Préparation en cours'),
        ('suspendu', 'Suspendu'),
        ('acheve', 'Achevé'),
    ]

    TYPE_TRAVAUX_CHOICES = [
        ('construction', 'Construction'),
        ('rehabilitation', 'Réhabilitation'),
        ('reparation', 'Réparation'),
    ]

    TYPE_MAIN_OEUVRE_CHOICES = [
        ('communautaire', 'Communautaire'),
        ('paye', 'Payé'),
    ]

    village = models.ForeignKey(
        Village,
        on_delete=models.CASCADE,
        related_name='demandes',
        verbose_name="Village"
    )
    statut = models.CharField(
        max_length=50,
        choices=STATUT_CHOICES,
        default='demande',
        verbose_name="Statut de la demande"
    )
    type_travaux = models.CharField(
        max_length=50,
        choices=TYPE_TRAVAUX_CHOICES,
        verbose_name="Type de travaux"
    )
    type_ouvrage = models.ForeignKey(
        TypeOuvrage,
        on_delete=models.PROTECT,
        related_name='demandes',
        verbose_name="Type d'ouvrage"
    )
    detail_travaux = models.TextField(
        verbose_name="Détail des travaux",
        help_text="Description détaillée des travaux demandés"
    )
    type_main_oeuvre = models.CharField(
        max_length=50,
        choices=TYPE_MAIN_OEUVRE_CHOICES,
        verbose_name="Type de main d'œuvre"
    )
    semestre_prevision = models.CharField(
        max_length=20,
        verbose_name="Semestre de prévision",
        help_text="Ex: S1 2025, S2 2025"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'demandes_villages'
        verbose_name = "Demande de village"
        verbose_name_plural = "Demandes de villages"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.village.nom_village} - {self.get_type_travaux_display()} - {self.get_statut_display()}"


class ValidationSource(models.Model):
    """Validation des sources d'eau pour les demandes"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    DONATION_CHOICES = [
        ('en_cours', 'En cours'),
        ('realisee', 'Réalisée'),
    ]

    PROPOSITION_CHOICES = [
        ('construction', 'Construction'),
        ('rehabilitation', 'Réhabilitation'),
        ('reparation', 'Réparation'),
    ]

    village = models.ForeignKey(
        Village,
        on_delete=models.CASCADE,
        related_name='validations_sources',
        verbose_name="Village"
    )
    nom_source = models.CharField(
        max_length=255,
        verbose_name="Nom de la source"
    )
    debit_source = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Débit de la source (L/s)",
        help_text="Débit en litres par seconde"
    )
    date_mesure_debit = models.DateField(
        verbose_name="Date de mesure du débit"
    )
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name="Latitude"
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name="Longitude"
    )
    photo_source = models.ForeignKey(
        FileUpload,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='validations_sources_photos',
        verbose_name="Photo de la source"
    )
    fiche_validation = models.ForeignKey(
        FileUpload,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='validations_sources_fiches',
        verbose_name="Fiche de validation (PDF/Image)"
    )
    distance_source_km = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Distance source-village (km)"
    )
    denivele_m = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Dénivelé source-village (m)",
        help_text="Dénivelé en mètres"
    )
    commentaires = models.TextField(
        blank=True,
        verbose_name="Commentaires sur la validation"
    )
    donation_source = models.CharField(
        max_length=20,
        choices=DONATION_CHOICES,
        default='en_cours',
        verbose_name="Donation de source"
    )
    proposition = models.CharField(
        max_length=20,
        choices=PROPOSITION_CHOICES,
        null=True,
        blank=True,
        verbose_name="Proposition de travaux",
        help_text="Type de travaux proposés suite à la validation"
    )
    nombre_sources_visitees = models.IntegerField(
        default=1,
        verbose_name="Nombre de sources visitées"
    )
    visiteur = models.ForeignKey(
        Employe,
        on_delete=models.PROTECT,
        related_name='validations_sources',
        verbose_name="Visiteur",
        help_text="Employé ayant effectué la visite"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'validations_sources'
        verbose_name = "Validation de source"
        verbose_name_plural = "Validations de sources"
        ordering = ['-date_mesure_debit']

    def __str__(self):
        return f"{self.nom_source} - {self.village.nom_village}"


class CaracteristiqueChantier(models.Model):
    """Caractéristiques et suivi des chantiers"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ouvrage = models.OneToOneField(
        Ouvrage,
        on_delete=models.CASCADE,
        related_name='caracteristique_chantier',
        verbose_name="Ouvrage"
    )
    employe = models.ForeignKey(
        Employe,
        on_delete=models.PROTECT,
        related_name='chantiers',
        verbose_name="Employé responsable"
    )
    tacheron = models.ForeignKey(
        Tacheron,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='chantiers',
        verbose_name="Tâcheron"
    )
    longueur_adduction_m = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Longueur de l'adduction (m)"
    )
    date_fin_chantier = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de fin de chantier"
    )

    # Dates du workflow
    date_ag_explication = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date AG explication collaboration"
    )
    date_suspension_animation = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date suspension animation"
    )
    date_reprise_animation = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date reprise animation"
    )
    date_preparation_chantier = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date préparation chantier"
    )
    date_ouverture_chantier = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date ouverture chantier"
    )
    date_suspension_chantier = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date suspension chantier"
    )
    date_reouverture_chantier = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date réouverture chantier"
    )
    date_reception_provisoire = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date réception provisoire"
    )
    date_reception_definitive = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date réception définitive"
    )

    # Coûts
    cout_estimatif_materiaux = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coût estimatif matériaux"
    )
    cout_estimatif_main_oeuvre = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coût estimatif main d'œuvre"
    )
    pourcentage_apports_locaux = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="% apports locaux valorisés",
        help_text="Pourcentage des apports locaux valorisés"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'caracteristiques_chantiers'
        verbose_name = "Caractéristique de chantier"
        verbose_name_plural = "Caractéristiques de chantiers"
        ordering = ['-created_at']

    def __str__(self):
        return f"Chantier {self.ouvrage.nom_ouvrage}"

    @property
    def etat_actuel(self):
        """Détermine l'état actuel du chantier en fonction des dates renseignées"""
        if self.date_reception_definitive:
            return 'reception_definitive'
        elif self.date_reception_provisoire:
            return 'reception_provisoire'
        elif self.date_reouverture_chantier:
            return 'chantier_rouvert'
        elif self.date_suspension_chantier:
            return 'chantier_suspendu'
        elif self.date_ouverture_chantier:
            return 'chantier_ouvert'
        elif self.date_preparation_chantier:
            return 'preparation_chantier'
        elif self.date_reprise_animation:
            return 'animation_reprise'
        elif self.date_suspension_animation:
            return 'animation_suspendue'
        elif self.date_ag_explication:
            return 'ag_explication'
        else:
            return 'non_demarre'

# Import des modèles d'enquêtes et animations
from .models_enquetes import Menage, EnqueteMenage, TypeAnimation, SessionAnimation, ParticipantAnimation
from .models_workflow import *  # noqa: F401,F403
