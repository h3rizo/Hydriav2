from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0056_alter_fournisseur_type_fournisseur'),
    ]

    operations = [
        migrations.AddField(
            model_name='fournisseur',
            name='lieu_cin',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Lieu CIN'),
        ),
    ]

