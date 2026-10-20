from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('infrastructure', '0025_liaisonhydraulique'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipementconstitutif',
            name='particularite_equipement',
            field=models.TextField(blank=True, help_text="Ã‰lÃ©ments particuliers Ã  connaÃ®tre sur cet Ã©quipement", null=True, verbose_name="ParticularitÃ© de l'Ã©quipement"),
        ),
    ]
