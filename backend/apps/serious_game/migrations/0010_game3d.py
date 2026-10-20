# Hydria Quest 3D (spec §14.1) : parties, records par niveau et badges du jeu.
# Compatible Django 4.2 (VPS) : pas de db_comment ni de GeneratedField.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


GAME_BADGES = [
    # (code, nom, icone, description, valeur de condition)
    ("jeu_premiers_pas", "Premiers pas", "fa-shoe-prints",
     "Terminer le niveau « Premier jour au village » de Hydria Quest 3D.", 0),
    ("jeu_reparateur", "Réparateur", "fa-wrench",
     "Obtenir la 3e étoile du niveau « La pompe en panne » de Hydria Quest 3D.", 1),
    ("jeu_tournee_a_l_heure", "Tournée à l'heure", "fa-cash-register",
     "Obtenir la 3e étoile du niveau « Tournée d'encaissement » de Hydria Quest 3D.", 2),
    ("jeu_chateau", "Maître du château d'eau", "fa-water",
     "Terminer le niveau « Journée chargée au château d'eau » de Hydria Quest 3D.", 3),
    ("jeu_12_etoiles", "Douze étoiles", "fa-star",
     "Réunir les 12 étoiles de Hydria Quest 3D.", 12),
]


def seed_game_badges(apps, schema_editor):
    QuizBadge = apps.get_model("serious_game", "QuizBadge")
    for code, nom, icon, description, condition_value in GAME_BADGES:
        QuizBadge.objects.get_or_create(
            code=code,
            defaults={
                "nom": nom,
                "icon": icon,
                "description": description,
                "condition_type": "jeu3d",
                "condition_value": condition_value,
                "actif": True,
            },
        )


def unseed(apps, schema_editor):
    QuizBadge = apps.get_model("serious_game", "QuizBadge")
    QuizBadge.objects.filter(code__in=[badge[0] for badge in GAME_BADGES], condition_type="jeu3d").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("serious_game", "0009_sync_model_labels"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GameRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("level", models.PositiveSmallIntegerField()),
                ("statut", models.CharField(
                    choices=[("en_cours", "En cours"), ("termine", "Terminé"), ("abandonne", "Abandonné"), ("rejete", "Rejeté")],
                    default="en_cours",
                    max_length=20,
                )),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("client_duration_ms", models.PositiveIntegerField(default=0)),
                ("quiz_snapshot", models.JSONField(blank=True, default=list)),
                ("answers", models.JSONField(blank=True, default=list)),
                ("quiz_first_try", models.PositiveSmallIntegerField(default=0)),
                ("gouttes", models.PositiveSmallIntegerField(default=0)),
                ("gouttes_total", models.PositiveSmallIntegerField(default=0)),
                ("events", models.JSONField(blank=True, default=dict)),
                ("segments", models.JSONField(blank=True, default=list)),
                ("falls", models.PositiveIntegerField(default=0)),
                ("help_bridges", models.PositiveSmallIntegerField(default=0)),
                ("assists", models.JSONField(blank=True, default=list)),
                ("stars_mask", models.PositiveSmallIntegerField(default=0)),
                ("new_stars_mask", models.PositiveSmallIntegerField(default=0)),
                ("score", models.PositiveIntegerField(default=0)),
                ("xp_etoiles", models.PositiveIntegerField(default=0)),
                ("xp_pratique", models.PositiveIntegerField(default=0)),
                ("xp_bonus", models.PositiveIntegerField(default=0)),
                ("xp_gagne", models.PositiveIntegerField(default=0)),
                ("rewards_processed", models.BooleanField(default=False)),
                ("quality_tier", models.CharField(blank=True, default="", max_length=12)),
                ("client_version", models.CharField(blank=True, default="", max_length=20)),
                ("rejected_reason", models.CharField(blank=True, default="", max_length=120)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="game3d_runs",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Partie Hydria Quest 3D",
                "verbose_name_plural": "Parties Hydria Quest 3D",
                "db_table": "game3d_runs",
                "ordering": ["-started_at"],
                "indexes": [models.Index(fields=["user", "level", "-started_at"], name="game3d_run_user_lvl_idx")],
            },
        ),
        migrations.CreateModel(
            name="GameLevelBest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("level", models.PositiveSmallIntegerField()),
                ("best_stars_mask", models.PositiveSmallIntegerField(default=0)),
                ("best_score", models.PositiveIntegerField(default=0)),
                ("best_time_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("runs_completed", models.PositiveIntegerField(default=0)),
                ("first_completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="game3d_bests",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Record Hydria Quest 3D",
                "verbose_name_plural": "Records Hydria Quest 3D",
                "db_table": "game3d_level_best",
                "unique_together": {("user", "level")},
            },
        ),
        migrations.RunPython(seed_game_badges, unseed),
    ]
