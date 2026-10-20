"""
Phase 2 - table de cache / journal des extractions IA de justificatifs.

Migration ecrite a la main (cf. CLAUDE.md / memoire projet : les migrations de
l'app accounting sont ecrites manuellement pour ne pas embarquer la desync d'etat
de InfoPaiementTaxeCommune). Cette migration ne cree qu'un modele isole.
"""
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0031_pointage_manuel_trois_niveaux"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScanExtraction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("file_sha256", models.CharField(db_index=True, max_length=64, unique=True)),
                ("source_name", models.CharField(blank=True, default="", max_length=500, verbose_name="Nom fichier / scan")),
                ("model", models.CharField(blank=True, default="", max_length=64)),
                ("status", models.CharField(choices=[("ok", "OK"), ("refusal", "Refus modele"), ("error", "Erreur")], db_index=True, default="ok", max_length=12)),
                ("stop_reason", models.CharField(blank=True, default="", max_length=40)),
                ("extracted", models.JSONField(blank=True, null=True, verbose_name="ReceiptExtraction (JSON)")),
                ("tokens_in", models.IntegerField(default=0)),
                ("tokens_out", models.IntegerField(default=0)),
                ("tokens_cache_read", models.IntegerField(default=0)),
                ("cout_usd", models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ("latence_ms", models.IntegerField(default=0)),
                ("request_id", models.CharField(blank=True, default="", max_length=64)),
                ("erreur", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Extraction IA de justificatif",
                "verbose_name_plural": "Extractions IA de justificatifs",
                "db_table": "ai_prefill_scan_extraction",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="scanextraction",
            index=models.Index(fields=["-created_at"], name="ai_prefill_created_idx"),
        ),
        migrations.AddIndex(
            model_name="scanextraction",
            index=models.Index(fields=["model", "-created_at"], name="ai_prefill_model_created_idx"),
        ),
        migrations.AddIndex(
            model_name="scanextraction",
            index=models.Index(fields=["status", "-created_at"], name="ai_prefill_status_created_idx"),
        ),
    ]
