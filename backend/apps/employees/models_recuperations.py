"""
Modèle pour gérer les récupérations (jours de repos après travail dimanche/férié)
"""
from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import uuid


class Recuperation(models.Model):
    """
    Récupération = Jour de repos accordé après avoir travaillé un dimanche ou jour férié

    Workflow:
    1. Employé travaille un dimanche/jour férié → Acquisition de droits de récupération
    2. Employé demande une récupération → Validation chef → Validation directeur
    3. Inscription au planning pour effectuer la récupération
    """

    MOTIF_ACQUISITION_CHOICES = [
        ('dimanche', 'Travail un dimanche'),
        ('jour_ferie', 'Travail un jour férié'),
    ]

    STATUT_CHOICES = [
        ('acquise', 'Acquise (non utilisée)'),
        ('demandee', 'Demandée (en attente)'),
        ('validee_chef', 'Validée par chef'),
        ('validee_directeur', 'Validée par directeur'),
        ('utilisee', 'Utilisée'),
        ('expiree', 'Expirée'),
        ('annulee', 'Annulée'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Employé
    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='recuperations',
        verbose_name="Employé"
    )

    # === PARTIE 1: ACQUISITION (quand la récup est gagnée) ===

    # Date du travail exceptionnel (dimanche ou férié)
    date_travail_exceptionnel = models.DateField(
        verbose_name="Date du travail exceptionnel",
        help_text="Date du dimanche ou jour férié travaillé"
    )

    motif_acquisition = models.CharField(
        max_length=20,
        choices=MOTIF_ACQUISITION_CHOICES,
        verbose_name="Motif d'acquisition",
        help_text="Pourquoi cette récupération a été acquise"
    )

    # Nombre de jours acquis (généralement 1 jour = 1 jour travaillé)
    nb_jours_acquis = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal('1.0'),
        verbose_name="Nombre de jours acquis",
        help_text="Généralement 1 jour, peut être 0.5 pour demi-journée"
    )

    date_acquisition = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'enregistrement",
        help_text="Date à laquelle la récupération a été enregistrée dans le système"
    )

    # Référence au planning du jour travaillé (optionnel)
    planning_travail = models.ForeignKey(
        'planning.Planning',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recuperations_acquises',
        verbose_name="Planning du travail exceptionnel"
    )

    # === PARTIE 2: UTILISATION (quand l'employé prend sa récup) ===

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='acquise',
        verbose_name="Statut"
    )

    # Date de la demande de récupération
    date_demande = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de la demande",
        help_text="Quand l'employé a demandé à utiliser cette récupération"
    )

    # Date(s) souhaitée(s) pour prendre la récupération
    date_debut_recup = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date début récupération",
        help_text="Date à laquelle l'employé souhaite récupérer"
    )

    date_fin_recup = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date fin récupération",
        help_text="Si plusieurs jours de récupération"
    )

    motif_demande = models.TextField(
        null=True,
        blank=True,
        verbose_name="Motif de la demande",
        help_text="Pourquoi l'employé souhaite prendre cette récupération maintenant"
    )

    # === VALIDATION ===

    # Validation chef
    validee_par_chef = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recuperations_validees_chef',
        verbose_name="Validé par (chef)"
    )
    date_validation_chef = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date validation chef"
    )
    commentaire_chef = models.TextField(
        null=True,
        blank=True,
        verbose_name="Commentaire du chef"
    )

    # Validation directeur
    validee_par_directeur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recuperations_validees_directeur',
        verbose_name="Validé par (directeur)"
    )
    date_validation_directeur = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date validation directeur"
    )
    commentaire_directeur = models.TextField(
        null=True,
        blank=True,
        verbose_name="Commentaire du directeur"
    )

    # === INSCRIPTION AU PLANNING ===

    inscrit_planning = models.BooleanField(
        default=False,
        verbose_name="Inscrit au planning",
        help_text="La récupération a-t-elle été inscrite dans le planning?"
    )
    date_inscription_planning = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'inscription au planning"
    )

    # Référence au planning de récupération (optionnel)
    planning_recup = models.ForeignKey(
        'planning.Planning',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recuperations_effectuees',
        verbose_name="Planning de la récupération"
    )

    # === ANNULATION ===

    annulee_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recuperations_annulees',
        verbose_name="Annulé par"
    )
    date_annulation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'annulation"
    )
    motif_annulation = models.TextField(
        null=True,
        blank=True,
        verbose_name="Motif d'annulation"
    )

    # === EXPIRATION ===

    date_expiration = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date d'expiration",
        help_text="Date limite pour utiliser cette récupération (ex: fin d'année)"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'recuperations'
        verbose_name = 'Récupération'
        verbose_name_plural = 'Récupérations'
        ordering = ['-date_travail_exceptionnel']
        indexes = [
            models.Index(fields=['employe', 'statut']),
            models.Index(fields=['date_travail_exceptionnel']),
            models.Index(fields=['statut']),
        ]

    def __str__(self):
        employe_nom = self.employe.nom_affichage if self.employe else 'Sans employé'
        return f"{employe_nom} - {self.get_motif_acquisition_display()} le {self.date_travail_exceptionnel} ({self.get_statut_display()})"

    @property
    def est_disponible(self):
        """La récupération est-elle disponible pour être utilisée?"""
        return self.statut == 'acquise'

    @property
    def est_en_attente_validation(self):
        """La récupération est-elle en attente de validation?"""
        return self.statut in ['demandee', 'validee_chef']

    @property
    def peut_etre_utilisee(self):
        """Peut-on demander à utiliser cette récupération?"""
        # Disponible ET non expirée
        if not self.est_disponible:
            return False
        if self.date_expiration and self.date_expiration < timezone.now().date():
            return False
        return True


class SoldeRecuperation(models.Model):
    """
    Suivi des soldes de récupérations par employé (historique mensuel)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='soldes_recuperations',
        verbose_name="Employé"
    )

    # Période
    annee = models.IntegerField(verbose_name="Année")
    mois = models.IntegerField(
        verbose_name="Mois",
        help_text="Mois (1-12)"
    )

    # Soldes récupérations (en jours)
    solde_debut = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=Decimal('0'),
        verbose_name="Solde début de mois (jours)",
        help_text="Report du mois précédent"
    )

    acquisitions = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=Decimal('0'),
        verbose_name="Acquisitions (jours)",
        help_text="Jours de récupération acquis ce mois (dimanches/fériés travaillés)"
    )

    utilisations = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=Decimal('0'),
        verbose_name="Utilisations (jours)",
        help_text="Jours de récupération utilisés ce mois"
    )

    expirations = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=Decimal('0'),
        verbose_name="Expirations (jours)",
        help_text="Jours de récupération expirés ce mois"
    )

    solde_fin = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=Decimal('0'),
        verbose_name="Solde fin de mois (jours)",
        help_text="Solde après acquisitions, utilisations et expirations"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'soldes_recuperations'
        verbose_name = 'Solde Récupération'
        verbose_name_plural = 'Soldes Récupérations'
        unique_together = ('employe', 'annee', 'mois')
        ordering = ['-annee', '-mois']
        indexes = [
            models.Index(fields=['employe', 'annee', 'mois']),
        ]

    def __str__(self):
        employe_nom = self.employe.nom_affichage if self.employe else 'Sans employé'
        return f"{employe_nom} - {self.mois:02d}/{self.annee}: {self.solde_fin} jours"


# Import nécessaire pour timezone
from django.utils import timezone
