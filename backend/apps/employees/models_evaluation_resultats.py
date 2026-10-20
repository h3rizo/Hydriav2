"""
Modèles pour l'évaluation des employés basée sur les résultats
Système complémentaire au système d'évaluation par tâches
"""
import uuid
from django.db import models
from django.utils import timezone
from decimal import Decimal


class EvaluationResultats(models.Model):
    MODE_EVALUATION_CHOICES = [
        ('recouvrement', 'Recouvrement'),
        ('reparations', 'Reparations'),
        ('hierarchie', 'Hierarchie'),
        ('aucun', 'Aucune regle'),
    ]

    """
    Évaluation d'un employé basée sur ses résultats (performance de recouvrement)
    Système de scoring binaire : 1 point par point d'eau avec paiement >= prévu
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.CASCADE,
        related_name='evaluations_resultats',
        verbose_name="Employé évalué"
    )

    periode_debut = models.DateField(
        verbose_name="Début de la période évaluée",
        help_text="Date de début de la période d'évaluation"
    )

    periode_fin = models.DateField(
        verbose_name="Fin de la période évaluée",
        help_text="Date de fin de la période d'évaluation"
    )

    date_calcul = models.DateField(
        default=timezone.now,
        verbose_name="Date de calcul",
        help_text="Date à laquelle l'évaluation a été calculée"
    )

    # Scores
    score_obtenu = models.PositiveIntegerField(
        default=0,
        verbose_name="Score obtenu",
        help_text="Nombre de points d'eau avec paiement conforme"
    )

    score_maximum = models.PositiveIntegerField(
        default=0,
        verbose_name="Score maximum",
        help_text="Nombre total de points d'eau sous responsabilité"
    )

    pourcentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Pourcentage de réussite",
        help_text="Pourcentage du score obtenu (score_obtenu / score_maximum * 100)"
    )

    # Détails des ouvrages évalués
    nb_ouvrages = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre d'ouvrages",
        help_text="Nombre d'ouvrages dont l'employé est responsable"
    )

    # Montants collectés
    montant_collecte_forfaitaire = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Montant collecté (forfaitaire)",
        help_text="Montant total collecté pour paiements forfaitaires"
    )

    montant_collecte_volume = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Montant collecté (volume)",
        help_text="Montant total collecté pour paiements au volume"
    )

    montant_prevu_forfaitaire = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Montant prévu (forfaitaire)",
        help_text="Montant total prévu pour paiements forfaitaires"
    )

    montant_prevu_volume = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Montant prévu (volume)",
        help_text="Montant total prévu pour paiements au volume"
    )

    # Statut
    statut = models.CharField(
        max_length=20,
        choices=[
            ('provisoire', 'Provisoire'),
            ('validee', 'Validée'),
        ],
        default='provisoire',
        verbose_name="Statut",
        help_text="Statut de l'évaluation"
    )

    commentaire = models.TextField(
        blank=True,
        verbose_name="Commentaire",
        help_text="Observations sur l'évaluation"
    )

    mode_evaluation = models.CharField(
        max_length=20,
        choices=MODE_EVALUATION_CHOICES,
        default='recouvrement',
        verbose_name="Mode d'évaluation",
        help_text="Indique si le score provient du recouvrement, des réparations, ou de la hiérarchie."
    )

    details_snapshot = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Snapshot des détails",
        help_text="Détails calculés au moment de l'évaluation (recouvrement, réparations, hiérarchie)."
    )

    metrics_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Snapshot des métriques",
        help_text="Synthèse métier calculée au moment de l'évaluation."
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evaluations_resultats'
        ordering = ['-periode_fin', '-date_calcul']
        verbose_name = "Évaluation (Résultats)"
        verbose_name_plural = "Évaluations (Résultats)"
        # Un employé ne peut avoir qu'une seule évaluation par période
        unique_together = ('employe', 'periode_debut', 'periode_fin')

    def __str__(self):
        return f"Évaluation résultats - {self.employe.nom_complet} - {self.periode_debut} au {self.periode_fin}"

    @property
    def montant_total_collecte(self):
        """Montant total collecté (forfaitaire + volume)"""
        return self.montant_collecte_forfaitaire + self.montant_collecte_volume

    @property
    def montant_total_prevu(self):
        """Montant total prévu (forfaitaire + volume)"""
        return self.montant_prevu_forfaitaire + self.montant_prevu_volume

    @property
    def taux_recouvrement(self):
        """Taux de recouvrement global (montant collecté / montant prévu)"""
        if self.montant_total_prevu == 0:
            return Decimal('0.00')
        return round((self.montant_total_collecte / self.montant_total_prevu) * 100, 2)

    def save(self, *args, **kwargs):
        # Calculer le pourcentage automatiquement
        if self.score_maximum > 0:
            self.pourcentage = round(
                (Decimal(self.score_obtenu) / Decimal(self.score_maximum)) * 100,
                2
            )
        else:
            self.pourcentage = Decimal('0.00')

        super().save(*args, **kwargs)


class EvaluationResultatsDetail(models.Model):
    """
    Détail d'une évaluation résultats par point d'eau
    Permet de tracer le calcul du score pour chaque point d'eau
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    evaluation = models.ForeignKey(
        'EvaluationResultats',
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name="Évaluation"
    )

    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.CASCADE,
        related_name='evaluations_resultats',
        verbose_name="Point d'eau"
    )

    ouvrage = models.ForeignKey(
        'organization.Ouvrage',
        on_delete=models.CASCADE,
        related_name='evaluations_resultats_details',
        verbose_name="Ouvrage",
        help_text="Ouvrage auquel appartient ce point d'eau"
    )

    # Type de paiement
    type_paiement = models.CharField(
        max_length=20,
        choices=[
            ('forfaitaire', 'Forfaitaire'),
            ('volume', 'Volume'),
        ],
        verbose_name="Type de paiement"
    )

    # Montants
    montant_prevu = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Montant prévu",
        help_text="Montant attendu pour ce point d'eau"
    )

    montant_paye = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Montant payé",
        help_text="Montant effectivement payé"
    )

    # Scoring
    point_obtenu = models.BooleanField(
        default=False,
        verbose_name="Point obtenu",
        help_text="True si montant_paye >= montant_prevu"
    )

    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'evaluations_resultats_details'
        ordering = ['ouvrage__nom_ouvrage', 'point_eau__nomabonne']
        verbose_name = "Détail évaluation (Résultats)"
        verbose_name_plural = "Détails évaluation (Résultats)"
        unique_together = ('evaluation', 'point_eau', 'type_paiement')

    def __str__(self):
        statut = "✓" if self.point_obtenu else "✗"
        return f"{statut} {self.point_eau.nomabonne} - {self.type_paiement}"

    def save(self, *args, **kwargs):
        # Déterminer automatiquement si le point est obtenu
        self.point_obtenu = (self.montant_paye >= self.montant_prevu)
        super().save(*args, **kwargs)
