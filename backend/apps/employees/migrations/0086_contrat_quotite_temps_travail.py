from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Quotite de temps de travail sur le contrat (100 = temps plein, 50 = mi-temps,
    25 = quart-temps), utilisee pour proratiser les fourchettes de la grille salariale.
    Les contrats existants passent a 100 %.
    """

    dependencies = [
        ('employees', '0085_niveau_junior_grille_salariale'),
    ]

    operations = [
        migrations.AddField(
            model_name='contrat',
            name='quotite_temps_travail',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('100.00'),
                help_text='100 = temps plein, 50 = mi-temps, 25 = quart-temps. '
                          'Sert a proratiser les fourchettes de la grille salariale.',
                max_digits=5,
                verbose_name='Quotite de temps de travail (%)',
            ),
        ),
    ]
