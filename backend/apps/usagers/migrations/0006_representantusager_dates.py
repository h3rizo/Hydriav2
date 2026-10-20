from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("usagers", "0005_dedupe_avisrepresentant_and_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="representantusager",
            name="date_debut",
            field=models.DateField(blank=True, db_index=True, null=True, verbose_name="Date début"),
        ),
        migrations.AddField(
            model_name="representantusager",
            name="date_fin",
            field=models.DateField(blank=True, db_index=True, null=True, verbose_name="Date fin"),
        ),
    ]
