from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0058_merge_20260503_1045'),
    ]

    operations = [
        migrations.AddField(
            model_name='designation',
            name='nature_stock',
            field=models.CharField(
                choices=[('consommable', 'Consommable'), ('non_consommable', 'Non consommable')],
                default='consommable',
                help_text="Les consommables diminuent avec l'usage. Les non consommables restent au stock et se contrôlent surtout par inventaire.",
                max_length=20,
                verbose_name='Nature du stock',
            ),
        ),
    ]
