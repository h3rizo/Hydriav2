from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Niveau Junior dans la grille salariale :
    - GrilleSalariale.niveau (junior / confirme, les grilles existantes restent 'confirme')
    - Employe.date_sortie_junior (vide = encore Junior ; point de depart de l'anciennete grille)
    """

    dependencies = [
        ('employees', '0084_ficheposte_composants_admis'),
    ]

    operations = [
        migrations.AddField(
            model_name='grillesalariale',
            name='niveau',
            field=models.CharField(
                choices=[('junior', 'Junior (non autonome)'), ('confirme', 'Confirme (par anciennete)')],
                default='confirme',
                help_text="Junior : fourchette unique, independante de l'anciennete. "
                          "Confirme : tranches d'anciennete comptees depuis la sortie du niveau Junior.",
                max_length=20,
                verbose_name='Niveau',
            ),
        ),
        migrations.AddField(
            model_name='employe',
            name='date_sortie_junior',
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Vide = encore Junior (non autonome). L'anciennete de la grille salariale "
                          "est comptee a partir de cette date.",
                verbose_name='Date de sortie du niveau Junior',
            ),
        ),
    ]
