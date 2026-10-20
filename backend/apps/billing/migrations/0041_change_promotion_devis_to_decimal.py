# Generated manually to handle boolean to decimal conversion

from django.db import migrations, models


def convert_boolean_to_decimal(apps, schema_editor):
    """
    Convert existing boolean values to decimal:
    - False -> 0
    - True -> 0 (no way to know the actual promotion amount)
    """
    PointEau = apps.get_model('billing', 'PointEau')
    # Update all True values to 0 (we can't know the actual promotion amount)
    # This is safe because the field will now store the actual amount
    PointEau.objects.filter(promotion_devis=True).update(promotion_devis=False)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0040_add_distance_promotion_devis'),
    ]

    operations = [
        # Step 1: Convert all True to False (prepare for type change)
        migrations.RunPython(convert_boolean_to_decimal, migrations.RunPython.noop),

        # Step 2: Drop the old boolean column and create a new decimal column
        migrations.RemoveField(
            model_name='pointeau',
            name='promotion_devis',
        ),
        migrations.AddField(
            model_name='pointeau',
            name='promotion_devis',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text='Montant de la promotion accordée sur le devis (en Ariary)',
                max_digits=10,
                null=True,
                verbose_name='Promotion devis (Ar)'
            ),
        ),
    ]
