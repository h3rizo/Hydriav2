import uuid

import django.db.models.deletion
from django.db import migrations, models

GROUPES = [
    ('ouvrages', 'Opérations sur les ouvrages', 'fa-water', 1),
    ('usagers', 'Opérations sur les usagers', 'fa-user-friends', 2),
    ('employes', 'Employés', 'fa-users', 3),
    ('administration', 'Administration', 'fa-building', 4),
    ('competences', 'Compétences des employés', 'fa-graduation-cap', 5),
    ('strategie', 'Stratégie', 'fa-chess', 6),
    ('autre', 'Autres', 'fa-ellipsis-h', 7),
]


def migrer_groupes(apps, schema_editor):
    Groupe = apps.get_model('planning', 'GroupeTypeActivite')
    Type = apps.get_model('planning', 'TypeActivite')
    par_code = {}
    for code, nom, icone, ordre in GROUPES:
        par_code[code] = Groupe.objects.create(nom=nom, icone=icone, ordre=ordre)
    for t in Type.objects.all():
        t.groupe = par_code.get(t.groupe_code)
        t.save(update_fields=['groupe'])


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0064_typeactivite_groupe'),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupeTypeActivite',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=255, unique=True, verbose_name='Nom du groupe')),
                ('icone', models.CharField(blank=True, default='fa-layer-group', max_length=50, verbose_name='Icône Font Awesome')),
                ('ordre', models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")),
                ('createdat', models.DateTimeField(auto_now_add=True)),
                ('updatedat', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': "Groupe de types d'activités",
                'verbose_name_plural': "Groupes de types d'activités",
                'db_table': 'groupes_types_activites',
                'ordering': ['ordre', 'nom'],
            },
        ),
        migrations.RenameField('typeactivite', 'groupe', 'groupe_code'),
        migrations.AddField(
            model_name='typeactivite',
            name='groupe',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='types', to='planning.groupetypeactivite', verbose_name='Groupe'),
        ),
        migrations.RunPython(migrer_groupes, migrations.RunPython.noop),
        migrations.RemoveField('typeactivite', 'groupe_code'),
    ]
