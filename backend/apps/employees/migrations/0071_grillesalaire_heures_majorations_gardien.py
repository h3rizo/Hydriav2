from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0070_alter_demandeconge_est_demi_journee_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='grillesalaire',
            name='nb_heures_1er_mai_gardien',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Heures travaillées le 1er mai calculées depuis les rotations', max_digits=7, verbose_name='Heures du 1er mai gardien'),
        ),
        migrations.AddField(
            model_name='grillesalaire',
            name='nb_heures_dimanche_gardien',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Heures travaillées le dimanche calculées depuis les rotations', max_digits=7, verbose_name='Heures du dimanche gardien'),
        ),
        migrations.AddField(
            model_name='grillesalaire',
            name='nb_heures_feries_gardien',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Heures travaillées les jours fériés, hors 1er mai', max_digits=7, verbose_name='Heures fériées gardien'),
        ),
        migrations.AddField(
            model_name='grillesalaire',
            name='nb_heures_nuit_gardien',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Heures de nuit calculées depuis les rotations du gardien', max_digits=7, verbose_name='Heures de nuit gardien'),
        ),
    ]
