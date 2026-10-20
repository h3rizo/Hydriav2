"""
Modèles pour la gestion des gardiens et leurs rotations
"""
from django.db import models
from django.utils import timezone
import uuid
from decimal import Decimal
from apps.employees.utils_conges import est_jour_ferie


class RotationGardien(models.Model):
    """Modèle pour gérer les rotations des gardiens"""

    SHIFT_CHOICES = [
        ('jour', 'Jour (8h-18h)'),
        ('nuit', 'Nuit (18h-8h lendemain)'),
        ('conge', 'Congé'),
        ('etendu', 'Étendu (8h-8h lendemain)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='rotations_gardien',
        verbose_name="Employé gardien"
    )
    date = models.DateField(verbose_name="Date")
    shift_type = models.CharField(
        max_length=10,
        choices=SHIFT_CHOICES,
        verbose_name="Type de shift"
    )
    heure_debut = models.TimeField(verbose_name="Heure de début")
    heure_fin = models.TimeField(verbose_name="Heure de fin")
    heures_travaillees = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Heures travaillées"
    )
    est_dimanche = models.BooleanField(
        default=False,
        verbose_name="Travail le dimanche",
        help_text="Si le shift tombe un dimanche"
    )
    est_jour_ferie = models.BooleanField(
        default=False,
        verbose_name="Travail un jour férié",
        help_text="Si le shift tombe un jour férié"
    )
    est_extension = models.BooleanField(
        default=False,
        verbose_name="Extension de shift",
        help_text="Shift étendu suite au congé d'un collègue"
    )
    remplace_employe = models.ForeignKey(
        'Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rotations_remplace',
        verbose_name="Remplace l'employé",
        help_text="Employé remplacé (si extension)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rotations_gardiens'
        verbose_name = 'Rotation Gardien'
        verbose_name_plural = 'Rotations Gardiens'
        unique_together = ('employe', 'date')
        ordering = ['date', 'heure_debut']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['employe', 'date']),
            models.Index(fields=['shift_type']),
        ]

    def __str__(self):
        return f"{self.employe.surnom or self.employe.nom} - {self.date} - {self.get_shift_type_display()}"

    def calculer_heures(self):
        """Calcule les heures travaillées pour ce shift"""
        from datetime import datetime, timedelta

        # Créer des datetime pour calculer la différence
        debut = datetime.combine(self.date, self.heure_debut)
        fin = datetime.combine(self.date, self.heure_fin)

        # Si heure de fin < heure de début, c'est un shift de nuit (passe minuit)
        if self.heure_fin < self.heure_debut:
            fin += timedelta(days=1)

        # Calculer la différence en heures
        duree = fin - debut
        heures = Decimal(str(duree.total_seconds() / 3600))

        self.heures_travaillees = heures
        return heures

    def save(self, *args, **kwargs):
        # Calculer automatiquement les heures si pas déjà défini
        if not self.heures_travaillees or self.heures_travaillees == 0:
            self.calculer_heures()

        # Vérifier si c'est un dimanche
        self.est_dimanche = self.date.weekday() == 6  # 6 = dimanche
        self.est_jour_ferie = est_jour_ferie(self.date)

        super().save(*args, **kwargs)


class HeuresSupplementairesGardien(models.Model):
    """Modèle pour calculer les heures supplémentaires et majorations des gardiens"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='heures_supplementaires_gardien',
        verbose_name="Employé gardien"
    )
    mois = models.IntegerField(verbose_name="Mois")
    annee = models.IntegerField(verbose_name="Année")

    # Heures travaillées
    heures_normales = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Heures normales",
        help_text="Jusqu'à 240h"
    )
    heures_supplementaires = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Heures supplémentaires",
        help_text="Heures au-delà de 240h"
    )
    heures_dimanche = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Heures le dimanche",
        help_text="Heures travaillées le dimanche"
    )
    heures_jours_feries = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Heures jours fériés",
        help_text="Heures travaillées les jours fériés"
    )
    heures_extensions = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Heures d'extension",
        help_text="Heures d'extension de shift (remplacement collègue)"
    )

    # Calculs financiers (à remplir lors du calcul de paie)
    montant_heures_supplementaires = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Montant heures supplémentaires"
    )
    montant_majoration_dimanche = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Montant majoration dimanche"
    )
    montant_majoration_jours_feries = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Montant majoration jours fériés"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'heures_supplementaires_gardiens'
        verbose_name = 'Heures Supplémentaires Gardien'
        verbose_name_plural = 'Heures Supplémentaires Gardiens'
        unique_together = ('employe', 'mois', 'annee')
        ordering = ['-annee', '-mois']
        indexes = [
            models.Index(fields=['employe', 'mois', 'annee']),
        ]

    def __str__(self):
        return f"{self.employe.surnom or self.employe.nom} - {self.mois}/{self.annee}"

    @classmethod
    def calculer_pour_mois(cls, employe_id, mois, annee):
        """
        Calcule les heures supplémentaires et majorations pour un gardien sur un mois donné

        Returns:
            HeuresSupplementairesGardien: Instance créée/mise à jour
        """
        from datetime import date
        from calendar import monthrange

        # Constante heures normales par mois
        HEURES_NORMALES_MOIS = Decimal('240')

        # Récupérer toutes les rotations du mois
        premier_jour = date(annee, mois, 1)
        dernier_jour = date(annee, mois, monthrange(annee, mois)[1])

        rotations = RotationGardien.objects.filter(
            employe_id=employe_id,
            date__gte=premier_jour,
            date__lte=dernier_jour
        )

        # Calculer les différents types d'heures
        heures_totales = sum(r.heures_travaillees for r in rotations)
        heures_dimanche = sum(r.heures_travaillees for r in rotations if r.est_dimanche)
        heures_jours_feries = sum(r.heures_travaillees for r in rotations if r.est_jour_ferie)
        heures_extensions = sum(r.heures_travaillees for r in rotations if r.est_extension)

        # Calculer heures normales et supplémentaires
        if heures_totales > HEURES_NORMALES_MOIS:
            heures_normales = HEURES_NORMALES_MOIS
            heures_supplementaires = heures_totales - HEURES_NORMALES_MOIS
        else:
            heures_normales = heures_totales
            heures_supplementaires = Decimal('0')

        # Créer ou mettre à jour l'enregistrement
        obj, created = cls.objects.get_or_create(
            employe_id=employe_id,
            mois=mois,
            annee=annee,
            defaults={
                'heures_normales': heures_normales,
                'heures_supplementaires': heures_supplementaires,
                'heures_dimanche': heures_dimanche,
                'heures_jours_feries': heures_jours_feries,
                'heures_extensions': heures_extensions,
            }
        )

        if not created:
            # Mettre à jour
            obj.heures_normales = heures_normales
            obj.heures_supplementaires = heures_supplementaires
            obj.heures_dimanche = heures_dimanche
            obj.heures_jours_feries = heures_jours_feries
            obj.heures_extensions = heures_extensions
            obj.save()

        return obj
