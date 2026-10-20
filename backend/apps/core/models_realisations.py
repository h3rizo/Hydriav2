"""Journal des réalisations constatées, pour les compteurs « fait » du widget Hydria.

Les pointages (couple numeroDiameX + baseDiameX) et les activités terminées
(Planning.statut = 'termine') n'ont aucune date fiable : ils sont écrits par une
dizaine de chemins différents, souvent via QuerySet.update() qui ne touche pas
updated_at. On ne date donc pas l'action elle-même : on CONSTATE périodiquement
l'état (apps.core.widget_realisations.constater) et on note le premier moment où
un objet apparaît comme fait.
"""
from django.db import models


class ConstatRealisation(models.Model):
    CATEGORIE_CHOICES = [
        ('pointage_volume', 'Facture au volume pointée'),
        ('pointage_forfait', 'Facture forfaitaire pointée'),
        ('activite_terminee', 'Activité terminée'),
    ]

    categorie = models.CharField(max_length=30, choices=CATEGORIE_CHOICES)
    # Identifiant de l'objet constaté (Releve, PaiementForfaitaire ou Planning).
    objet_id = models.CharField(max_length=64)
    ouvrage_id = models.UUIDField(null=True, blank=True)
    # Pour les activités : reparation, rehabilitation, installation ou autre.
    famille = models.CharField(max_length=20, blank=True)
    montant = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Moment du constat. NULL = déjà fait lors du tout premier constat (date
    # inconnue) : jamais compté dans une période.
    constate_le = models.DateTimeField(null=True, blank=True)
    # Moment où l'objet a cessé d'être fait (dépointé, activité rouverte).
    retire_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'core_constat_realisation'
        verbose_name = 'Constat de réalisation'
        verbose_name_plural = 'Constats de réalisation'
        constraints = [
            models.UniqueConstraint(fields=['categorie', 'objet_id'], name='constat_realisation_unique'),
        ]
        indexes = [models.Index(fields=['categorie', 'constate_le'], name='constat_cat_date_idx')]

    def __str__(self):
        return f"{self.categorie} {self.objet_id} {self.constate_le or 'initial'}"
