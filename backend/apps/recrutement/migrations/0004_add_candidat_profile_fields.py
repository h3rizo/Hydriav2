from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recrutement', '0003_add_chiffres_question_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidat',
            name='adresse',
            field=models.TextField(blank=True, default='', verbose_name='Adresse'),
        ),
        migrations.AddField(
            model_name='candidat',
            name='convocation_entretien',
            field=models.BooleanField(default=False, help_text='Indique si le candidat est sélectionné pour un entretien', verbose_name='Convocation entretien'),
        ),
        migrations.AddField(
            model_name='candidat',
            name='date_naissance',
            field=models.DateField(blank=True, null=True, verbose_name='Date de naissance'),
        ),
    ]
