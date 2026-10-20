from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '1008_cloture_carburant_mois'),
    ]

    operations = [
        migrations.AddField(
            model_name='relevécompteur',
            name='photo_compteur',
            field=models.ImageField(blank=True, null=True, upload_to='vehicules/releves_compteur/', verbose_name='Photo compteur'),
        ),
    ]
