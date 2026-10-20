# Generated manually to keep migration state aligned after raw SQL column drop
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('geography', '0007_remove_village_commune_village_accessibilite_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='village',
                    name='commune',
                ),
            ],
            database_operations=[],
        ),
    ]
