from datetime import date

from django.db import migrations, models
import uuid


DEFAULT_JOURS_FERIES = [
    (date(2025, 1, 1), "Jour de l'An"),
    (date(2025, 3, 29), "Commemoration des martyrs de 1947"),
    (date(2025, 3, 31), "Lundi de Paques"),
    (date(2025, 5, 1), "Fete du Travail"),
    (date(2025, 5, 19), "Lundi de Pentecote"),
    (date(2025, 6, 26), "Fete de l'Independance"),
    (date(2025, 8, 15), "Assomption"),
    (date(2025, 11, 1), "Toussaint"),
    (date(2025, 12, 25), "Noel"),
    (date(2026, 1, 1), "Jour de l'An"),
    (date(2026, 3, 20), "Jour ferie exceptionnel"),
    (date(2026, 3, 29), "Commemoration des martyrs de 1947"),
    (date(2026, 4, 6), "Lundi de Paques"),
    (date(2026, 5, 1), "Fete du Travail"),
    (date(2026, 5, 14), "Ascension"),
    (date(2026, 5, 25), "Lundi de Pentecote"),
    (date(2026, 5, 27), "Aid-el-filtr"),
    (date(2026, 6, 26), "Fete de l'Independance"),
    (date(2026, 8, 15), "Assomption"),
    (date(2026, 11, 1), "Toussaint"),
    (date(2026, 12, 25), "Noel"),
]


def seed_jours_feries(apps, schema_editor):
    JourFerie = apps.get_model('employees', 'JourFerie')
    for holiday_date, holiday_name in DEFAULT_JOURS_FERIES:
        JourFerie.objects.update_or_create(
            date=holiday_date,
            defaults={
                'nom': holiday_name,
                'description': '',
                'actif': True,
            },
        )


def unseed_jours_feries(apps, schema_editor):
    JourFerie = apps.get_model('employees', 'JourFerie')
    JourFerie.objects.filter(date__in=[item[0] for item in DEFAULT_JOURS_FERIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0066_evaluation_developpement_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='JourFerie',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date', models.DateField(help_text='Date officielle du jour férié', unique=True, verbose_name='Date')),
                ('nom', models.CharField(help_text="Ex: Ascension, Lundi de Pâques, Jour de l'An", max_length=200, verbose_name='Nom')),
                ('description', models.TextField(blank=True, help_text='Commentaire ou précision éventuelle', null=True, verbose_name='Description')),
                ('actif', models.BooleanField(default=True, help_text="Ce jour férié est-il pris en compte dans l'application ?", verbose_name='Actif')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Jour férié',
                'verbose_name_plural': 'Jours fériés',
                'db_table': 'jours_feries',
                'ordering': ['date'],
            },
        ),
        migrations.RunPython(seed_jours_feries, unseed_jours_feries),
    ]
