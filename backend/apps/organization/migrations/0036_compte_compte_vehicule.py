from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0035_compte_financement'),
    ]

    operations = [
        migrations.AddField(
            model_name='compte',
            name='compte_vehicule',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Si coché, ce compte porte des dépenses de véhicule (carburant, entretien) '
                    'réparties sur les ouvrages via le conducteur'
                ),
                verbose_name='Compte véhicule',
            ),
        ),
    ]
