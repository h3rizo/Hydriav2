from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0036_compte_compte_vehicule'),
    ]

    operations = [
        migrations.AddField(
            model_name='compte',
            name='compte_ouvrage_analyse',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Si coché, la dépense est affectée à l'ouvrage identifié dans le libellé "
                    "UNIQUEMENT pour l'analyse des coûts par ouvrage. Sans effet sur le contrôle "
                    "DiameX (contrairement à « Nécessite ouvrage »)."
                ),
                verbose_name='Compte à répartir sur un ouvrage (analyse des coûts)',
            ),
        ),
    ]
