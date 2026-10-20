# Isolee volontairement (voir 0015) : c'est l'operation la plus susceptible
# d'entrer en contention avec le trafic web sur la table communes (referencee
# par la FK). A relancer isolement, si besoin a une heure de trafic plus calme.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('geography', '0014_repair_missing_photo_columns'),
        ('usagers', '0015_reunion_add_district_region'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reunion',
            name='commune',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reunions', to='geography.commune', verbose_name='Commune'),
        ),
    ]
