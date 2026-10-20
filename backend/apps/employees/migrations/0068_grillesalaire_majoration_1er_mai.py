from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0067_add_jours_feries_crud'),
    ]

    operations = [
        migrations.AddField(
            model_name='grillesalaire',
            name='a_travaille_1er_mai',
            field=models.BooleanField(
                default=False,
                help_text="Cocher si le gardien a travaille le 1er Mai (majore double d'un jour ferie normal)",
                verbose_name='Travaille le 1er Mai',
            ),
        ),
        migrations.AddField(
            model_name='grillesalaire',
            name='montant_majoration_1er_mai',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                verbose_name='Montant majoration 1er Mai (Ar)',
            ),
        ),
    ]
