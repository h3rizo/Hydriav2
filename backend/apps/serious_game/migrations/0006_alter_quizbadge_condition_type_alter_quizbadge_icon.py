from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("serious_game", "0005_quizbadge_code_unique"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quizbadge",
            name="condition_type",
            field=models.CharField(blank=True, default="", max_length=120, verbose_name="Type de condition"),
        ),
        migrations.AlterField(
            model_name="quizbadge",
            name="icon",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Icone"),
        ),
    ]
