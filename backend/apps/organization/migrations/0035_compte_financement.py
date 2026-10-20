from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0034_ouvragealias'),
    ]

    operations = [
        migrations.AddField(
            model_name='compte',
            name='financement',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Aucun contrôle'),
                    ('RL Activités', 'RL Activités'),
                    ('FAN', 'FAN'),
                    ('MEB', 'MEB'),
                ],
                default='',
                help_text='Valeur attendue dans la colonne Fin des saisies DiameX pour ce compte',
                max_length=50,
                verbose_name='Financement attendu',
            ),
        ),
    ]
