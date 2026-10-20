from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0059_modalitegestion_explication_fin'),
    ]

    operations = [
        migrations.AddField(
            model_name='paiementforfaitaire',
            name='traite_en_avance',
            field=models.BooleanField(default=False, help_text='Indique si la ligne a déjà été sortie de la file des avances', verbose_name='Traité en avance'),
        ),
    ]
