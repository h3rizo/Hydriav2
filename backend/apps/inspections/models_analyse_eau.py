"""
Modèles pour les analyses d'eau.
Gestion des analyses de qualité de l'eau (coliformes fécaux, pH).
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


class AnalyseEau(models.Model):
    """Modèle pour les analyses d'eau (coliformes fécaux, pH)"""

    VOLUME_CHOICES = [
        (10, '10 mL'),
        (20, '20 mL'),
        (25, '25 mL'),
        (50, '50 mL'),
        (60, '60 mL'),
        (100, '100 mL'),
    ]

    TYPE_PRELEVEMENT_CHOICES = [
        ('equipement', 'Équipement'),
        ('point_eau', 'Point d\'eau'),
        ('point_eau_traditionnel', 'Point d\'eau traditionnel'),
        ('bouteille', 'Bouteille d\'eau cachetée'),
        ('autre', 'Autre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Type et localisation du prélèvement
    type_prelevement = models.CharField(
        max_length=50,
        choices=TYPE_PRELEVEMENT_CHOICES,
        verbose_name="Type de prélèvement"
    )

    # Relations optionnelles (selon type)
    equipement = models.ForeignKey(
        'infrastructure.EquipementConstitutif',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analyses_eau',
        verbose_name="Équipement"
    )

    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analyses_eau',
        verbose_name="Point d'eau"
    )

    # Description libre pour autres types (traditionnels, bouteilles, etc.)
    description_lieu = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Description du lieu de prélèvement",
        help_text="Pour points d'eau traditionnels, bouteilles, ou autres"
    )

    # Dates et heures
    date_prelevement = models.DateTimeField(
        verbose_name="Date et heure de prélèvement"
    )

    date_analyse = models.DateTimeField(
        verbose_name="Date et heure d'analyse"
    )

    date_resultat = models.DateTimeField(
        verbose_name="Date et heure du résultat"
    )

    # Paramètres de l'analyse
    volume_analyse = models.IntegerField(
        choices=VOLUME_CHOICES,
        verbose_name="Volume analysé (mL)",
        help_text="Volume d'eau analysé en millilitres"
    )

    # Résultats coliformes
    nombre_coliformes = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Nombre de coliformes comptés",
        help_text="Laisser vide si TNC (trop nombreux pour être compté)"
    )

    tnc = models.BooleanField(
        default=False,
        verbose_name="TNC (Trop Nombreux pour être Compté)"
    )

    # Résultat pH
    ph = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(14)],
        verbose_name="pH",
        help_text="Valeur du pH (0-14)"
    )

    # Observation
    observation = models.TextField(
        blank=True,
        verbose_name="Observation",
        help_text="Observations et remarques diverses"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analyses_eau_creees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'analyses_eau'
        verbose_name = "Analyse d'eau"
        verbose_name_plural = "Analyses d'eau"
        ordering = ['-date_prelevement']
        indexes = [
            models.Index(fields=['type_prelevement']),
            models.Index(fields=['date_prelevement']),
            models.Index(fields=['date_analyse']),
            models.Index(fields=['-date_prelevement']),
        ]

    @property
    def nombre_pour_100ml(self):
        """Calcule le nombre de coliformes pour 100mL"""
        if self.tnc:
            return None  # TNC ne peut pas être calculé
        if self.nombre_coliformes is None:
            return None
        if self.volume_analyse == 0:
            return None
        return int((100 * self.nombre_coliformes) / self.volume_analyse)

    @property
    def est_positif(self):
        """Indique si l'analyse est positive (coliformes > 0 ou TNC)"""
        if self.tnc:
            return True
        if self.nombre_coliformes is not None and self.nombre_coliformes > 0:
            return True
        return False

    @property
    def lieu_affichage(self):
        """Retourne le lieu de prélèvement pour affichage"""
        if self.type_prelevement == 'equipement' and self.equipement:
            return f"Équipement: {self.equipement.nom}"
        elif self.type_prelevement == 'point_eau' and self.point_eau:
            return f"Point d'eau: {self.point_eau.code_point_eau}"
        else:
            return self.description_lieu or f"{self.get_type_prelevement_display()}"

    @property
    def commune_nom(self):
        """Retourne le nom de la commune"""
        if self.point_eau and self.point_eau.parcelle:
            parcelle = self.point_eau.parcelle
            if parcelle.village and parcelle.village.fokontany and parcelle.village.fokontany.commune:
                return parcelle.village.fokontany.commune.nom_commune
        elif self.equipement:
            # Récupérer via ouvrage → point_eau → parcelle → village → fokontany → commune
            ouvrage = self.equipement.ouvrage
            if ouvrage:
                point_eau_premier = ouvrage.pointeau_set.first()
                if point_eau_premier and point_eau_premier.parcelle:
                    parcelle = point_eau_premier.parcelle
                    if parcelle.village and parcelle.village.fokontany and parcelle.village.fokontany.commune:
                        return parcelle.village.fokontany.commune.nom_commune
        return ""

    @property
    def village_nom(self):
        """Retourne le nom du village"""
        if self.point_eau and self.point_eau.parcelle:
            parcelle = self.point_eau.parcelle
            if parcelle.village:
                return parcelle.village.nom_village
        elif self.equipement:
            ouvrage = self.equipement.ouvrage
            if ouvrage:
                point_eau_premier = ouvrage.pointeau_set.first()
                if point_eau_premier and point_eau_premier.parcelle:
                    parcelle = point_eau_premier.parcelle
                    if parcelle.village:
                        return parcelle.village.nom_village
        return ""

    def __str__(self):
        date_str = self.date_prelevement.strftime('%d/%m/%Y %H:%M')
        return f"{self.lieu_affichage} - {date_str}"
