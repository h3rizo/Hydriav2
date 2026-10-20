# Generated manually - seed du referentiel TypeAutorite avec les 6 types precedemment
# codes en dur (Autorite.TYPE_CHOICES avant migration 0025), pour que les fiches Autorite
# existantes gardent le meme libelle affiche (get_type_autorite_display) apres bascule vers
# le referentiel editable.

from django.db import migrations


TYPES_INITIAUX = [
    ('maire', 'Maire', 1),
    ('chef_fokontany', 'Chef Fokontany', 2),
    ('chef_district', 'Chef District', 3),
    ('chef_region', 'Chef Region', 4),
    ('prefet', 'Prefet', 5),
    ('autre', 'Autre', 6),
]


def seed_types(apps, schema_editor):
    TypeAutorite = apps.get_model('usagers', 'TypeAutorite')
    for slug, nom, ordre in TYPES_INITIAUX:
        TypeAutorite.objects.get_or_create(slug=slug, defaults={'nom': nom, 'ordre': ordre, 'actif': True})


def unseed_types(apps, schema_editor):
    TypeAutorite = apps.get_model('usagers', 'TypeAutorite')
    TypeAutorite.objects.filter(slug__in=[slug for slug, _, _ in TYPES_INITIAUX]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usagers', '0025_alter_autorite_type_autorite_typeautorite'),
    ]

    operations = [
        migrations.RunPython(seed_types, unseed_types),
    ]
