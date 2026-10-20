"""Table de cache / journal des extractions IA de justificatifs."""
from __future__ import annotations

import uuid

from django.db import models


class ScanExtraction(models.Model):
    """
    Une extraction Claude par fichier (cle = sha256 du contenu).
    Sert a la fois de cache (re-appel gratuit) et de journal de couts/qualite.
    """

    STATUS = (
        ("ok", "OK"),
        ("refusal", "Refus modele"),
        ("error", "Erreur"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_sha256 = models.CharField(max_length=64, unique=True, db_index=True)
    source_name = models.CharField(max_length=500, blank=True, default="", verbose_name="Nom fichier / scan")

    model = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS, default="ok", db_index=True)
    stop_reason = models.CharField(max_length=40, blank=True, default="")

    extracted = models.JSONField(null=True, blank=True, verbose_name="ReceiptExtraction (JSON)")

    tokens_in = models.IntegerField(default=0)
    tokens_out = models.IntegerField(default=0)
    tokens_cache_read = models.IntegerField(default=0)
    cout_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    latence_ms = models.IntegerField(default=0)

    request_id = models.CharField(max_length=64, blank=True, default="")
    erreur = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_prefill_scan_extraction"
        verbose_name = "Extraction IA de justificatif"
        verbose_name_plural = "Extractions IA de justificatifs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"], name="ai_prefill_created_idx"),
            models.Index(fields=["model", "-created_at"], name="ai_prefill_model_created_idx"),
            models.Index(fields=["status", "-created_at"], name="ai_prefill_status_created_idx"),
        ]

    def __str__(self):
        return f"{self.source_name or self.file_sha256[:12]} ({self.status})"
