from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_contribution_terrain'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConstatRealisation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('categorie', models.CharField(choices=[
                    ('pointage_volume', 'Facture au volume pointée'),
                    ('pointage_forfait', 'Facture forfaitaire pointée'),
                    ('activite_terminee', 'Activité terminée'),
                ], max_length=30)),
                ('objet_id', models.CharField(max_length=64)),
                ('ouvrage_id', models.UUIDField(blank=True, null=True)),
                ('famille', models.CharField(blank=True, max_length=20)),
                ('montant', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('constate_le', models.DateTimeField(blank=True, null=True)),
                ('retire_le', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Constat de réalisation',
                'verbose_name_plural': 'Constats de réalisation',
                'db_table': 'core_constat_realisation',
                'indexes': [models.Index(fields=['categorie', 'constate_le'], name='constat_cat_date_idx')],
                'constraints': [models.UniqueConstraint(fields=('categorie', 'objet_id'), name='constat_realisation_unique')],
            },
        ),
    ]
