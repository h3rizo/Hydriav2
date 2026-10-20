# Generated manually on 2025-10-05 14:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0002_alter_contrat_categorie_professionnel_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='employe',
            name='signature',
            field=models.ImageField(blank=True, null=True, upload_to='signatures/employes/', verbose_name="Signature de l'employé"),
        ),
    ]
