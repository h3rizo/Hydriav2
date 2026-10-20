from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0068_grillesalaire_majoration_1er_mai'),
    ]

    operations = [
        migrations.AddField(
            model_name='grillesalaire',
            name='nb_dimanches_travailles',
            field=models.IntegerField(
                default=0,
                help_text='Nombre de dimanches travailles sur le mois de salaire',
                verbose_name='Dimanches travailles',
            ),
        ),
    ]
