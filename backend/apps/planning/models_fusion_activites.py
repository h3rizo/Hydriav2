import uuid

from django.conf import settings
from django.db import models


class FusionFichePosteLog(models.Model):
    """
    Journal d'une fusion d'activités de réparation (FichePoste).

    `donnees` conserve tout ce qu'il faut pour annuler : identifiants des lignes
    repointées, état d'origine des fiches sources, composants ajoutés, etc.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fusions_fiches_poste',
    )
    fiche_cible = models.ForeignKey(
        'employees.FichePoste', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fusions_log',
    )
    nom_cible_avant = models.CharField(max_length=255)
    nom_cible_apres = models.CharField(max_length=255)
    resume = models.JSONField(default=dict, blank=True)
    donnees = models.JSONField(default=dict, blank=True)
    annulee_le = models.DateTimeField(null=True, blank=True)
    annulee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fusions_fiches_poste_annulees',
    )

    class Meta:
        db_table = 'planning_fusion_fiche_poste_log'
        ordering = ['-created_at']
        verbose_name = "Fusion d'activités de réparation"
        verbose_name_plural = "Fusions d'activités de réparation"

    def __str__(self):
        return f"{self.nom_cible_apres} ({self.created_at:%Y-%m-%d %H:%M})"
