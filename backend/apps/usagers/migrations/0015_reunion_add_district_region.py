# Migration scindee manuellement (voir 0015b/0015c) pour limiter la portee de
# chaque verrou pris sur la table reunions/communes en production, la table
# communes etant tres sollicitee par le trafic web en continu.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0074_alter_contrat_categorie_professionnel'),
        ('geography', '0014_repair_missing_photo_columns'),
        ('usagers', '0014_autorite_reunion_pointagereuniondiamex_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='reunion',
            name='district',
            field=models.ForeignKey(blank=True, help_text='Renseigne pour les reunions/ateliers tenus au niveau district (sans commune precise).', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reunions', to='geography.district', verbose_name='District'),
        ),
        migrations.AddField(
            model_name='reunion',
            name='region',
            field=models.ForeignKey(blank=True, help_text='Renseigne pour les reunions/ateliers tenus au niveau regional (sans commune ni district precis).', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reunions', to='geography.region', verbose_name='Region'),
        ),
        migrations.AddIndex(
            model_name='reunion',
            index=models.Index(fields=['district'], name='reunions_distric_be3928_idx'),
        ),
        migrations.AddIndex(
            model_name='reunion',
            index=models.Index(fields=['region'], name='reunions_region__095fa6_idx'),
        ),
    ]
