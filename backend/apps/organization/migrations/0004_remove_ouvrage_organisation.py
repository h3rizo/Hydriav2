# Generated manually to remove organisation from ouvrage

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0003_organisation_logo'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ouvrage',
            name='organisation',
        ),
    ]
