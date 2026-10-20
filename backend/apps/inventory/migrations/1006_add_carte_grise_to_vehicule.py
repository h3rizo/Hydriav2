from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '1005_reparation_planification'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicule',
            name='carte_grise',
            field=models.FileField(blank=True, null=True, upload_to='vehicules/cartes_grises/', verbose_name='Carte grise / carte rose'),
        ),
    ]
