from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recrutement', '0002_add_candidat_preconfigure'),
    ]

    operations = [
        migrations.AlterField(
            model_name='questiontest',
            name='type_question',
            field=models.CharField(
                choices=[
                    ('qcm', 'QCM (Choix multiples)'),
                    ('oui_non', 'Oui/Non'),
                    ('chiffres', 'Chiffres'),
                    ('texte_libre', 'Texte libre'),
                ],
                max_length=20,
                verbose_name='Type de question'
            ),
        ),
    ]
