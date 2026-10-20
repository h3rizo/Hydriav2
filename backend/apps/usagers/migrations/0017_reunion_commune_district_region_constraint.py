# Derniere etape de la scission de 0015 : ajoute la contrainte CHECK une fois
# que commune est bien nullable (0016) et que district/region existent (0015).
# Ne porte que sur la table reunions elle-meme, sans dependance a communes.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usagers', '0016_reunion_commune_nullable'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='reunion',
            # ``check`` reste compatible avec Django 4.2 (VPS) et Django 5.x.
            constraint=models.CheckConstraint(check=models.Q(('commune__isnull', False), ('district__isnull', False), ('region__isnull', False), _connector='OR'), name='reunion_commune_district_ou_region_requise'),
        ),
    ]
