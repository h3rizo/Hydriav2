# Generated manually on 2025-10-05 14:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0002_update_deduction_irsa_to_decimal'),
    ]

    operations = [
        migrations.AddField(
            model_name='organisation',
            name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='logos/organisations/', verbose_name="Logo de l'organisation"),
        ),
    ]
