from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0083_tarifs_forfaitaires_initiaux'),
    ]

    operations = [
        migrations.AddField(
            model_name='tarifvolumetrique',
            name='institutionnel',
            field=models.BooleanField(
                default=False,
                help_text="Appliqué aux points d'eau cochés « branchement institutionnel » ; à défaut, ils prennent le tarif ordinaire de leur type.",
                verbose_name='Tarif des branchements institutionnels',
            ),
        ),
    ]
