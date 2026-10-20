from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0048_fraismedicaux_justificatif_hospitalisation_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='ficheposte',
            name='preuve_obligatoire',
            field=models.BooleanField(default=False, help_text="Une preuve (pi\u00e8ce jointe) est requise pour l'accomplissement", verbose_name='Preuve obligatoire'),
        ),
    ]
