# Generated manually to keep salary grid state aligned without re-adding existing columns
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0019_add_fiche_impression_fields'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='grillesalaire',
                    name='nb_jours_presence',
                    field=models.IntegerField(
                        default=0,
                        help_text="Nombre de jours travaillés (journalier) ou de présence dans le mois (prorata temps plein/partiel)",
                        verbose_name='Nombre de jours de présence',
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.AddField(
            model_name='grillesalaire',
            name='est_prorata',
            field=models.BooleanField(
                default=False,
                help_text='Si True, le salaire brut total = salaire brut base × (nb_jours_presence / 30)',
                verbose_name='Calcul au prorata',
            ),
        ),
        migrations.AlterField(
            model_name='contrat',
            name='salaire_brut_base',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text='Salaire brut de base mensuel défini dans le contrat',
                max_digits=12,
                verbose_name='Salaire brut de base (Ar)',
            ),
        ),
    ]
