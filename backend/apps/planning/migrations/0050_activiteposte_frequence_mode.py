from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0049_alter_activiteposte_fiche_poste'),
    ]

    operations = [
        migrations.AddField(
            model_name='activiteposte',
            name='frequence_mois',
            field=models.IntegerField(choices=[(1, 'Tous les mois'), (2, 'Tous les 2 mois'), (6, 'Tous les 6 mois'), (12, 'Tous les ans')], default=1, verbose_name='Fréquence (mois)'),
        ),
        migrations.AddField(
            model_name='activiteposte',
            name='mode_frequence',
            field=models.CharField(choices=[('par_employe', 'Par employé'), ('par_employe_ouvrage', 'Par employé et ouvrage')], default='par_employe', max_length=30, verbose_name='Mode de fréquence'),
        ),
    ]
