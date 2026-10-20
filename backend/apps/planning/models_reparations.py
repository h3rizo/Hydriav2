"""
Modèles pour le suivi des réparations et réhabilitations
"""
import uuid
from django.db import models
from django.utils import timezone
from apps.employees.models import Employe
from apps.organization.models import Ouvrage
from apps.infrastructure.models import EquipementConstitutif
from apps.billing.models import PointEau


class Reparation(models.Model):
    """
    Suivi des réparations et réhabilitations des ouvrages.
    Workflow strict avec validation et suivi détaillé.
    """

    STATUT_CHOICES = [
        ('signalee', 'Signalée'),
        ('planifiee', 'Planifiée'),
        ('en_cours', 'En cours'),
        ('terminee', 'Terminée'),
        ('validee', 'Validée'),
        ('annulee', 'Annulée'),
    ]

    PRIORITE_CHOICES = [
        ('basse', 'Basse'),
        ('moyenne', 'Moyenne'),
        ('haute', 'Haute'),
        ('urgente', 'Urgente'),
    ]

    TYPE_CHOICES = [
        ('reparation', 'Réparation'),
        ('rehabilitation', 'Réhabilitation'),
        ('maintenance_preventive', 'Maintenance préventive'),
        ('maintenance_corrective', 'Maintenance corrective'),
    ]

    # Identifiant
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Informations de base
    ouvrage = models.ForeignKey(
        Ouvrage,
        on_delete=models.CASCADE,
        related_name='reparations',
        verbose_name="Ouvrage"
    )

    equipement = models.ForeignKey(
        EquipementConstitutif,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reparations',
        verbose_name="Équipement concerné"
    )

    point_eau = models.ForeignKey(
        PointEau,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reparations',
        verbose_name="Point d'eau concerné"
    )

    # Description du problème
    titre = models.CharField(
        max_length=200,
        verbose_name="Titre de la réparation"
    )

    description = models.TextField(
        verbose_name="Description du problème"
    )

    type_reparation = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        default='reparation',
        verbose_name="Type"
    )

    priorite = models.CharField(
        max_length=20,
        choices=PRIORITE_CHOICES,
        default='moyenne',
        verbose_name="Priorité"
    )

    # Dates
    date_signalement = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de signalement"
    )

    date_prevue = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date prévue d'intervention"
    )

    date_debut_travaux = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date début des travaux"
    )

    date_fin_travaux = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date fin des travaux"
    )

    date_validation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de validation"
    )

    # Personnes impliquées
    signale_par = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reparations_signalees',
        verbose_name="Signalé par"
    )

    assigne_a = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reparations_assignees',
        verbose_name="Assigné à"
    )

    valide_par = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reparations_validees',
        verbose_name="Validé par"
    )

    # Statut et suivi
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='signalee',
        verbose_name="Statut"
    )

    # Lien avec le planning
    planning = models.ForeignKey(
        'Planning',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reparations',
        verbose_name="Planning associé"
    )

    # Détails de la réparation
    materiel_utilise = models.TextField(
        null=True,
        blank=True,
        verbose_name="Matériel utilisé"
    )

    cout_estime = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coût estimé (Ar)"
    )

    cout_reel = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coût réel (Ar)"
    )

    # Compte rendu
    compte_rendu = models.TextField(
        null=True,
        blank=True,
        verbose_name="Compte rendu des travaux"
    )

    commentaire_validation = models.TextField(
        null=True,
        blank=True,
        verbose_name="Commentaire de validation"
    )

    # Informations usager
    nom_usager = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        verbose_name="Nom de l'usager plaignant"
    )

    contact_usager = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Contact de l'usager"
    )

    usager_informe = models.BooleanField(
        default=False,
        verbose_name="Usager informé de la réparation"
    )

    date_information_usager = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'information de l'usager"
    )

    # Photos/Documents
    photos = models.TextField(
        null=True,
        blank=True,
        verbose_name="Photos (JSON)",
        help_text="Stockage JSON des chemins de photos"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reparations'
        verbose_name = 'Réparation'
        verbose_name_plural = 'Réparations'
        ordering = ['-date_signalement']
        indexes = [
            models.Index(fields=['statut', '-date_signalement']),
            models.Index(fields=['ouvrage', 'statut']),
            models.Index(fields=['priorite', '-date_signalement']),
        ]

    def __str__(self):
        return f"{self.titre} - {self.get_statut_display()}"

    @property
    def est_en_retard(self):
        """Vérifier si la réparation est en retard par rapport à la date prévue"""
        if self.date_prevue and self.statut not in ['terminee', 'validee', 'annulee']:
            return timezone.now().date() > self.date_prevue
        return False

    @property
    def duree_travaux_jours(self):
        """Calculer la durée des travaux en jours"""
        if self.date_debut_travaux and self.date_fin_travaux:
            return (self.date_fin_travaux - self.date_debut_travaux).days
        return None

    @property
    def delai_signalement_jours(self):
        """Calculer le délai depuis le signalement"""
        return (timezone.now() - self.date_signalement).days

    def passer_en_planifiee(self, date_prevue, assigne_a=None):
        """Passer la réparation en statut planifiée"""
        self.statut = 'planifiee'
        self.date_prevue = date_prevue
        if assigne_a:
            self.assigne_a = assigne_a
        self.save()

    def demarrer_travaux(self):
        """Démarrer les travaux"""
        self.statut = 'en_cours'
        self.date_debut_travaux = timezone.now()
        self.save()

    def terminer_travaux(self, compte_rendu=None, cout_reel=None):
        """Terminer les travaux"""
        self.statut = 'terminee'
        self.date_fin_travaux = timezone.now()
        if compte_rendu:
            self.compte_rendu = compte_rendu
        if cout_reel:
            self.cout_reel = cout_reel
        self.save()

    def valider(self, validateur, commentaire=None):
        """Valider la réparation"""
        self.statut = 'validee'
        self.valide_par = validateur
        self.date_validation = timezone.now()
        if commentaire:
            self.commentaire_validation = commentaire
        self.save()

    def annuler(self, raison=None):
        """Annuler la réparation"""
        self.statut = 'annulee'
        if raison:
            self.commentaire_validation = raison
        self.save()

    def informer_usager(self):
        """Marquer l'usager comme informé"""
        self.usager_informe = True
        self.date_information_usager = timezone.now()
        self.save()


class HistoriqueReparation(models.Model):
    """
    Historique des changements de statut et actions sur une réparation
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    reparation = models.ForeignKey(
        Reparation,
        on_delete=models.CASCADE,
        related_name='historique'
    )

    action = models.CharField(max_length=100, verbose_name="Action")
    ancien_statut = models.CharField(max_length=20, null=True, blank=True)
    nouveau_statut = models.CharField(max_length=20, null=True, blank=True)
    commentaire = models.TextField(null=True, blank=True)

    effectue_par = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'historique_reparations'
        ordering = ['-date_action']

    def __str__(self):
        return f"{self.action} - {self.date_action.strftime('%Y-%m-%d %H:%M')}"
