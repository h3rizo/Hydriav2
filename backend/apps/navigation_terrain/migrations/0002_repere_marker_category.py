from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('navigation_terrain', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='repere',
            name='marker_category',
            field=models.CharField(
                choices=[
                    ('landmark', 'Repere'),
                    ('water_point', "Point d'eau"),
                    ('equipment', 'Equipement'),
                ],
                default='landmark',
                max_length=20,
            ),
        ),
    ]
