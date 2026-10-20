from django.db import models
from apps.organization.models import Base, Ouvrage
from apps.employees.models import Employe
from apps.geography.models import District, Commune
import uuid


class PrevisionBudget(models.Model):
    """
    Modèle pour les prévisions budgétaires mensuelles.
    Agrège toutes les prévisions de recettes et dépenses pour faciliter
    les demandes de fonds.
    """
    TYPE_CHOICES = [
        ('recette_forfaitaire', 'Recette Forfaitaire'),
        ('recette_volumetrique', 'Recette Volumétrique'),
        ('recette_nouveau_pe', "Recette Nouveaux Points d'Eau"),
        ('depense_bon_livraison', 'Dépense Bon de Livraison'),
        ('depense_avance', 'Dépense Avance'),
        ('depense_indemnites', 'Dépense Indemnités'),
        ('depense_salaires', 'Dépense Salaires'),
        ('depense_irsa', 'Dépense IRSA'),
        ('depense_cnaps', 'Dépense CNAPS'),
        ('depense_fmfp', 'Dépense FMFP'),
        ('depense_mutuelle', 'Dépense Mutuelle Santé'),
        ('depense_loyer', 'Dépense Loyers (613100)'),
        ('depense_recurrente', 'Dépense Récurrente (602, 606, 615, 623100, 626222, 626320, 626321, 627203, 627204, 631104)'),
        ('depense_autre', 'Dépense Autre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Colonnes demandées
    date = models.DateField(
        verbose_name="Date",
        help_text="Date de la prévision (mois concerné)"
    )
    cat = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Compte (Cat)",
        help_text="Code du compte comptable (ex: 6211, 7011)"
    )
    libelle = models.CharField(
        max_length=500,
        verbose_name="Libellé",
        help_text="Description de la prévision"
    )
    in_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="In (Recettes)",
        help_text="Montant des recettes prévues"
    )
    out_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Out (Dépenses)",
        help_text="Montant des dépenses prévues"
    )
    activ = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Activ (Organisation)",
        help_text="Code organisation/volet (ex: SOAKOJA)"
    )
    detail = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Detail",
        help_text="Détails supplémentaires"
    )
    designation = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Désignation",
        help_text="Nom de la désignation (BonLivraison ou PlanningDetail)"
    )
    quantite = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Quantité",
        help_text="Quantité prévue"
    )
    prix_unitaire = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prix Unitaire",
        help_text="Prix unitaire prévu"
    )

    # Champs métier supplémentaires
    type_prevision = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        verbose_name="Type de prévision"
    )
    base = models.ForeignKey(
        Base,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Base"
    )
    ouvrage = models.ForeignKey(
        Ouvrage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Ouvrage",
        help_text="Ouvrage concerné (pour recettes forfaitaires/volumétriques)"
    )
    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="District",
        help_text="District géographique de l'ouvrage"
    )
    commune = models.ForeignKey(
        Commune,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Commune",
        help_text="Commune géographique de l'ouvrage"
    )
    annee = models.IntegerField(
        verbose_name="Année",
        help_text="Année de la prévision"
    )
    mois = models.IntegerField(
        verbose_name="Mois",
        help_text="Mois de la prévision (1-12)"
    )

    # Flags de calcul automatique
    est_calculee_auto = models.BooleanField(
        default=True,
        verbose_name="Calculée automatiquement",
        help_text="Indique si cette ligne est calculée automatiquement"
    )
    source_calcul = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        verbose_name="Source du calcul",
        help_text="Description de la source (ex: 'PointEau ID: xxx')"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='previsions_creees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'previsions_budget'
        verbose_name = 'Prévision budgétaire'
        verbose_name_plural = 'Prévisions budgétaires'
        ordering = ['-annee', '-mois', 'date']
        indexes = [
            models.Index(fields=['annee', 'mois']),
            models.Index(fields=['type_prevision']),
            models.Index(fields=['base']),
            models.Index(fields=['est_calculee_auto']),
            models.Index(fields=['date']),
        ]
        # Contrainte unique pour éviter les doublons de calcul automatique
        unique_together = [
            ('type_prevision', 'annee', 'mois', 'source_calcul')
        ]

    def __str__(self):
        return f"{self.get_type_prevision_display()} - {self.annee}/{self.mois:02d} - {self.libelle[:50]}"

    @property
    def montant_net(self):
        """Calcule le montant net (recettes - dépenses)"""
        return self.in_amount - self.out_amount


class ConfigurationPrevision(models.Model):
    """
    Configuration pour les calculs de prévisions.
    Permet de paramétrer les hypothèses de calcul.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Prévisions nouveaux points d'eau
    nb_nouveaux_pe_prevus = models.IntegerField(
        default=25,
        verbose_name="Nombre de nouveaux PE prévus",
        help_text="Nombre de nouveaux points d'eau prévus pour l'année"
    )
    tarif_nouveau_pe_trimestre = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=75000,
        verbose_name="Tarif nouveau PE par trimestre",
        help_text="Tarif forfaitaire pour un nouveau point d'eau (Ar/trimestre)"
    )

    # Année de référence
    annee_reference = models.IntegerField(
        verbose_name="Année de référence",
        help_text="Année pour laquelle ces paramètres s'appliquent"
    )

    # Paramètres de calcul volumétrique
    nb_mois_moyenne_volumetrique = models.IntegerField(
        default=12,
        verbose_name="Nombre de mois pour moyenne volumétrique",
        help_text="Nombre de mois à prendre en compte pour la moyenne (défaut: 12)"
    )

    # Métadonnées
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Indique si cette configuration est active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'configurations_prevision'
        verbose_name = 'Configuration de prévision'
        verbose_name_plural = 'Configurations de prévision'
        ordering = ['-annee_reference']
        # Une seule configuration active par année
        unique_together = [('annee_reference', 'actif')]

    def __str__(self):
        return f"Configuration {self.annee_reference} {'(Active)' if self.actif else '(Inactive)'}"
