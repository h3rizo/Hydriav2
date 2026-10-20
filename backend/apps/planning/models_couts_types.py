"""
Coûts types par activité (réparation, installation, réhabilitation, remplacement).

Un coût type est un barème : pour une activité (FichePoste), un type de cible
(type d'équipement OU type de point d'eau) et, éventuellement, un composant de ce
type, la liste des désignations (matériaux / prestations) avec leur quantité type.
Le prix unitaire vient de la désignation, sauf surcharge sur la ligne.

Dans un planning, le coût type pré-remplit les PlanningDetail ; on les ajuste
ensuite selon la réalité.
"""
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class CoutTypeActivite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fiche_poste = models.ForeignKey(
        'employees.FichePoste', on_delete=models.CASCADE,
        related_name='couts_types', verbose_name="Activité",
    )
    type_equipement = models.ForeignKey(
        'infrastructure.TypeEquipement', on_delete=models.CASCADE, null=True, blank=True,
        related_name='couts_types', verbose_name="Type d'équipement",
    )
    type_point_eau = models.ForeignKey(
        'billing.TypePointEau', on_delete=models.CASCADE, null=True, blank=True,
        related_name='couts_types', verbose_name="Type de point d'eau",
    )
    composant_equipement = models.ForeignKey(
        'inspections.ComposantTypeEquipement', on_delete=models.CASCADE, null=True, blank=True,
        related_name='couts_types', verbose_name="Composant d'équipement",
    )
    composant_point_eau = models.ForeignKey(
        'inspections.ComposantTypePointEau', on_delete=models.CASCADE, null=True, blank=True,
        related_name='couts_types', verbose_name="Composant de point d'eau",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'couts_types_activites'
        verbose_name = "Coût type d'activité"
        verbose_name_plural = "Coûts types d'activités"
        ordering = ['fiche_poste__tache']

    def __str__(self):
        return f"{self.fiche_poste.tache} — {self.cible_libelle}"

    @property
    def cible_genre(self):
        if self.type_equipement_id:
            return 'equipement'
        if self.type_point_eau_id:
            return 'point_eau'
        return ''

    @property
    def composant(self):
        return self.composant_equipement or self.composant_point_eau

    @property
    def cible_libelle(self):
        type_cible = self.type_equipement or self.type_point_eau
        nom_type = getattr(type_cible, 'nom_type', '') if type_cible else ''
        composant = self.composant
        if composant:
            return f"{nom_type} / {composant.nom_composant}"
        return nom_type or "—"

    @property
    def total_estime(self):
        return sum((ligne.montant for ligne in self.lignes.all()), Decimal('0'))

    def clean(self):
        super().clean()
        if bool(self.type_equipement_id) == bool(self.type_point_eau_id):
            raise ValidationError("Indiquez un type d'équipement OU un type de point d'eau.")
        if self.composant_equipement_id and self.composant_point_eau_id:
            raise ValidationError("Un seul composant peut être indiqué.")
        if self.composant_equipement_id:
            if not self.type_equipement_id or self.composant_equipement.type_equipement_id != self.type_equipement_id:
                raise ValidationError("Ce composant n'appartient pas au type d'équipement choisi.")
        if self.composant_point_eau_id:
            if not self.type_point_eau_id or self.composant_point_eau.type_point_eau_id != self.type_point_eau_id:
                raise ValidationError("Ce composant n'appartient pas au type de point d'eau choisi.")
        doublons = CoutTypeActivite.objects.filter(
            fiche_poste_id=self.fiche_poste_id,
            type_equipement_id=self.type_equipement_id,
            type_point_eau_id=self.type_point_eau_id,
            composant_equipement_id=self.composant_equipement_id,
            composant_point_eau_id=self.composant_point_eau_id,
        ).exclude(pk=self.pk)
        if doublons.exists():
            raise ValidationError("Un coût type existe déjà pour cette activité, cette cible et ce composant.")


class CoutTypeLigne(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cout_type = models.ForeignKey(CoutTypeActivite, on_delete=models.CASCADE, related_name='lignes')
    designation = models.ForeignKey(
        'planning.Designation', on_delete=models.PROTECT, related_name='lignes_couts_types',
    )
    quantite = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1'))
    pu = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name="Prix unitaire (surcharge)",
        help_text="Vide = prix unitaire par défaut de la désignation",
    )
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'couts_types_lignes'
        ordering = ['ordre', 'designation__nom']
        unique_together = ('cout_type', 'designation')

    def __str__(self):
        return f"{self.designation.nom} × {self.quantite}"

    @property
    def pu_effectif(self):
        if self.pu is not None:
            return self.pu
        return self.designation.prix_unitaire or Decimal('0')

    @property
    def montant(self):
        return (self.quantite or Decimal('0')) * self.pu_effectif
