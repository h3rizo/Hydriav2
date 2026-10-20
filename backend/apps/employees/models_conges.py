"""
Modèles pour la gestion des congés et permissions.
"""
from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import uuid


class TypePermission(models.Model):
    """
    Table des types de permissions avec nombre de jours accordés.
    Exemples: Décès proche, Mariage, Naissance, etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evenement = models.CharField(
        max_length=200,
        verbose_name="Événement",
        help_text="Type d'événement justifiant la permission"
    )
    nb_jours_accordes = models.IntegerField(
        verbose_name="Nombre de jours accordés",
        help_text="Nombre de jours d'absence permis pour cet événement"
    )
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name="Description",
        help_text="Détails sur les conditions d'octroi"
    )
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Ce type de permission est-il toujours en vigueur?"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'types_permissions'
        verbose_name = "Type de permission"
        verbose_name_plural = "Types de permissions"
        ordering = ['evenement']

    def __str__(self):
        return f"{self.evenement} ({self.nb_jours_accordes} jours)"


class JourFerie(models.Model):
    """Jour ferie officiel configurable depuis l'interface."""

    TYPE_OFFICIEL = 'officiel'
    TYPE_DECRET = 'decret'
    TYPE_CHOICES = [
        (TYPE_OFFICIEL, 'Jour férié officiel'),
        (TYPE_DECRET, 'Jour chômé et payé (décret ponctuel)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateField(
        unique=True,
        verbose_name="Date",
        help_text="Date officielle du jour férié",
    )
    nom = models.CharField(
        max_length=200,
        verbose_name="Nom",
        help_text="Ex: Ascension, Lundi de Pâques, Jour de l'An",
    )
    type_jour = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_OFFICIEL,
        verbose_name="Type de jour férié",
        help_text="Officiel (majoration 50%) ou chômé et payé par décret ponctuel (majoration 30%)",
    )
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name="Description",
        help_text="Commentaire ou précision éventuelle",
    )
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Ce jour férié est-il pris en compte dans l'application ?",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'jours_feries'
        verbose_name = "Jour férié"
        verbose_name_plural = "Jours fériés"
        ordering = ['date']

    def __str__(self):
        return f"{self.date.strftime('%d/%m/%Y')} - {self.nom}"

    @property
    def est_decret(self):
        return self.type_jour == self.TYPE_DECRET


class DemandeConge(models.Model):
    """
    Demande de congé ou permission d'un employé.
    Workflow: Demande → Validation chef → Validation directeur → Inscription planning
    """
    TYPE_CHOICES = [
        ('conge', 'Congé normal'),
        ('conge_demi', 'Congé demi-journée'),
        ('permission', 'Permission'),
        ('repos', 'Repos'),
        ('repos_medical', 'Repos médical'),
        ('jour_ferie', 'Jour férié'),
    ]

    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('soumise', 'Soumise'),
        ('validee_chef', 'Validée par chef'),
        ('validee_directeur', 'Validée par directeur'),
        ('refusee', 'Refusée'),
        ('annulee', 'Annulée'),
        ('inscrite_planning', 'Inscrite au planning'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Employé demandeur
    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='demandes_conges',
        verbose_name="Employé"
    )

    # Type et dates
    type_demande = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name="Type de demande"
    )
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(verbose_name="Date de fin")
    nb_jours_demandes = models.IntegerField(
        verbose_name="Nombre de jours demandés",
        help_text="Calculé automatiquement entre date_debut et date_fin"
    )

    # Spécifique aux permissions
    type_permission = models.ForeignKey(
        'TypePermission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demandes',
        verbose_name="Type de permission"
    )

    # Motif et contexte
    motif = models.TextField(
        verbose_name="Motif de la demande",
        help_text="Raison de la demande de congé/permission"
    )

    # Champs spécifiques pour certains types de demandes
    est_demi_journee = models.BooleanField(
        default=False,
        verbose_name="Demi-journée",
        help_text="Vrai si c'est une demi-journée (0.5 jour)"
    )

    justificatif_medical = models.FileField(
        upload_to='conges/justificatifs_medicaux/',
        null=True,
        blank=True,
        verbose_name="Justificatif médical",
        help_text="Document requis pour repos médical (certificat médical, ordonnance, etc.)"
    )

    # Soldes au moment de la demande (snapshot)
    reliquat_conge_avant = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Reliquat congés avant demande (jours)",
        help_text="Solde de congés au moment de la demande"
    )
    reliquat_permission_avant = models.IntegerField(
        default=0,
        verbose_name="Reliquat permissions avant demande (jours)",
        help_text="Jours de permission restants pour l'année"
    )

    # Workflow de validation
    statut = models.CharField(
        max_length=30,
        choices=STATUT_CHOICES,
        default='brouillon',
        verbose_name="Statut"
    )

    date_demande = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de soumission",
        help_text="Date à laquelle la demande a été soumise"
    )

    # Validation chef hiérarchique
    validee_par_chef = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conges_valides_chef',
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
        related_name='conges_valides_directeur',
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

    # Refus
    refusee_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conges_refuses',
        verbose_name="Refusé par"
    )
    date_refus = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de refus"
    )
    motif_refus = models.TextField(
        null=True,
        blank=True,
        verbose_name="Motif du refus"
    )

    # Inscription au planning
    inscrit_planning = models.BooleanField(
        default=False,
        verbose_name="Inscrit au planning",
        help_text="Les jours ont-ils été inscrits dans le planning?"
    )
    date_inscription_planning = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'inscription au planning"
    )

    # Annulation
    annulee_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demandes_conges_annulees',
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

    # Report (modification des dates)
    reporte_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demandes_conges_reportees',
        verbose_name="Reporté par"
    )
    date_report = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date du dernier report"
    )
    motif_report = models.TextField(
        null=True,
        blank=True,
        verbose_name="Motif du report"
    )
    dates_originales = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Dates originales",
        help_text="Historique des dates avant report: [{date_debut, date_fin, date_report}]"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='demandes_conges_creees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'demandes_conges'
        verbose_name = "Demande de congé"
        verbose_name_plural = "Demandes de congés"
        ordering = ['-date_demande', '-created_at']
        indexes = [
            models.Index(fields=['employe', 'statut']),
            models.Index(fields=['date_debut', 'date_fin']),
            models.Index(fields=['statut']),
        ]

    def __str__(self):
        return f"{self.employe} - {self.get_type_demande_display()} du {self.date_debut} au {self.date_fin}"

    @property
    def peut_etre_validee_chef(self):
        """La demande peut-elle être validée par le chef?"""
        return self.statut == 'soumise'

    @property
    def peut_etre_validee_directeur(self):
        """La demande peut-elle être validée par le directeur?"""
        return self.statut == 'validee_chef'

    @property
    def est_validee_complete(self):
        """La demande est-elle complètement validée?"""
        return self.statut == 'validee_directeur'


class SoldeConge(models.Model):
    """
    Suivi des soldes de congés et permissions par employé.
    Historique mensuel pour traçabilité.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='soldes_conges',
        verbose_name="Employé"
    )

    # Période
    annee = models.IntegerField(verbose_name="Année")
    mois = models.IntegerField(
        verbose_name="Mois",
        help_text="Mois (1-12)"
    )

    # Soldes congés (en jours, peut être décimal pour demi-journées)
    solde_conges_debut = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Solde congés début de mois (jours)",
        help_text="Report du mois précédent"
    )
    acquisition_conges = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.5'),
        verbose_name="Acquisition congés (jours)",
        help_text="2.5 jours par mois travaillé"
    )
    consommation_conges = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Consommation congés (jours)",
        help_text="Jours de congés pris ce mois"
    )
    solde_conges_fin = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Solde congés fin de mois (jours)",
        help_text="Solde après acquisition et consommation"
    )

    # Soldes permissions (en jours entiers, max 10 par an)
    solde_permissions_debut = models.IntegerField(
        default=0,
        verbose_name="Solde permissions début d'année (jours)",
        help_text="Nombre de jours de permission restants"
    )
    consommation_permissions = models.IntegerField(
        default=0,
        verbose_name="Consommation permissions (jours)",
        help_text="Jours de permission utilisés ce mois"
    )
    solde_permissions_fin = models.IntegerField(
        default=0,
        verbose_name="Solde permissions fin de mois (jours)",
        help_text="Jours de permission restants"
    )

    # Paiement de congés non pris (exceptionnel)
    conges_payes_non_pris = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Congés payés (non pris) (jours)",
        help_text="Jours de congés payés en indemnité au lieu d'être pris"
    )
    montant_indemnite_conges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Montant indemnité congés (Ar)",
        help_text="Montant payé pour les congés non pris"
    )

    # Métadonnées
    calcule_auto = models.BooleanField(
        default=False,
        verbose_name="Calculé automatiquement",
        help_text="Ce solde a-t-il été calculé automatiquement?"
    )
    notes = models.TextField(
        null=True,
        blank=True,
        verbose_name="Notes"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'soldes_conges'
        verbose_name = "Solde de congés"
        verbose_name_plural = "Soldes de congés"
        unique_together = ('employe', 'annee', 'mois')
        ordering = ['-annee', '-mois', 'employe']
        indexes = [
            models.Index(fields=['employe', 'annee', 'mois']),
            models.Index(fields=['annee', 'mois']),
        ]

    def __str__(self):
        return f"{self.employe} - {self.mois}/{self.annee} - Solde: {self.solde_conges_fin}j"

    def calculer_soldes(self):
        """Calcule les soldes de fin de mois"""
        # Solde congés fin = début + acquisition - consommation - payés
        self.solde_conges_fin = (
            self.solde_conges_debut +
            self.acquisition_conges -
            self.consommation_conges -
            self.conges_payes_non_pris
        )

        # Solde permissions (pas d'acquisition mensuelle, juste consommation)
        self.solde_permissions_fin = (
            self.solde_permissions_debut -
            self.consommation_permissions
        )

    def save(self, *args, **kwargs):
        """Recalculer les soldes avant sauvegarde"""
        self.calculer_soldes()
        super().save(*args, **kwargs)
