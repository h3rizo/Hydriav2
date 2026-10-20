"""
Regles de saisie guidee par compte : decrivent comment composer la `description`
DiameX (et remplir `fournisseur` / `detail`) a partir de champs structures saisis
par l'operateur.

Voir apps/accounting/regles_saisie/ pour le moteur et le schema de `config`.
"""
from __future__ import annotations

import uuid

from django.db import models


class RegleSaisieCompte(models.Model):
    MODE_CHOICES = [
        ("fournisseur", "Depense fournisseur"),
        ("employe", "Depense / charge employe"),
        ("libre", "Ecriture libre"),
        ("recette", "Recette (ouvrage / abonne)"),
    ]
    SENS_CHOICES = [
        ("out", "Depense (Out)"),
        ("in", "Recette (In)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        "organization.Organisation",
        on_delete=models.CASCADE,
        related_name="regles_saisie_compte",
    )
    compte_cible = models.CharField(
        max_length=20,
        help_text="Code compte exact (ex: 601011) ou prefixe (ex: 641, 218)",
    )
    est_prefixe = models.BooleanField(
        default=False,
        help_text="Si coche, s'applique a tous les comptes commencant par compte_cible",
    )
    libelle = models.CharField(max_length=255, blank=True, default="", verbose_name="Libelle de la regle")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    sens = models.CharField(max_length=3, choices=SENS_CHOICES)
    config = models.JSONField(default=dict, blank=True, verbose_name="Configuration (champs + gabarit description)")
    actif = models.BooleanField(default=True)
    ordre = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "regle_saisie_compte"
        verbose_name = "Regle de saisie par compte"
        verbose_name_plural = "Regles de saisie par compte"
        unique_together = ("organisation", "compte_cible")
        ordering = ["organisation_id", "compte_cible"]
        indexes = [
            models.Index(fields=["organisation", "actif"], name="regle_saisie_org_actif_idx"),
            models.Index(fields=["organisation", "est_prefixe"], name="regle_saisie_org_prefixe_idx"),
        ]

    def __str__(self):
        return f"{self.compte_cible}{'*' if self.est_prefixe else ''} ({self.mode}) - {self.organisation_id}"


class CompteFournisseurAutorise(models.Model):
    """
    Restreint les fournisseurs proposes en autocompletion pour un compte donne.
    Aucune ligne pour un compte => tous les fournisseurs sont autorises.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        "organization.Organisation",
        on_delete=models.CASCADE,
        related_name="comptes_fournisseurs_autorises",
    )
    compte_code = models.CharField(max_length=20, help_text="Code compte exact")
    fournisseur = models.ForeignKey(
        "billing.Fournisseur",
        on_delete=models.CASCADE,
        related_name="comptes_autorises",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compte_fournisseur_autorise"
        verbose_name = "Fournisseur autorise par compte"
        verbose_name_plural = "Fournisseurs autorises par compte"
        unique_together = ("organisation", "compte_code", "fournisseur")
        indexes = [
            models.Index(fields=["organisation", "compte_code"], name="cfa_org_compte_idx"),
        ]

    def __str__(self):
        return f"{self.compte_code} <- {self.fournisseur_id} ({self.organisation_id})"
