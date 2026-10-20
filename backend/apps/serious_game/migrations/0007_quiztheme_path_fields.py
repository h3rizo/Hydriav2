import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("serious_game", "0006_alter_quizbadge_condition_type_alter_quizbadge_icon"),
    ]

    operations = [
        migrations.AddField(
            model_name="quiztheme",
            name="icon",
            field=models.CharField(blank=True, default="", max_length=120, verbose_name="Icone"),
        ),
        migrations.AddField(
            model_name="quiztheme",
            name="module_code",
            field=models.CharField(blank=True, default="", max_length=120, verbose_name="Code module"),
        ),
        migrations.AddField(
            model_name="quiztheme",
            name="module_precedent",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="modules_suivants", to="serious_game.quiztheme", verbose_name="Module precedent"),
        ),
        migrations.AddField(
            model_name="quiztheme",
            name="parcours_code",
            field=models.CharField(blank=True, default="", max_length=80, verbose_name="Code parcours"),
        ),
        migrations.AddField(
            model_name="quiztheme",
            name="score_deblocage",
            field=models.PositiveIntegerField(default=80, verbose_name="Score de deblocage"),
        ),
    ]
