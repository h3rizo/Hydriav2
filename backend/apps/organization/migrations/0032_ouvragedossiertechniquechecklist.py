from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0031_ouvragedossiertechnique'),
    ]

    operations = [
        migrations.CreateModel(
            name='OuvrageDossierTechniqueChecklist',
            fields=[
                ('plan_reseau', models.BooleanField(default=False, verbose_name='Plan de réseau')),
                ('fiche_technique', models.BooleanField(default=False, verbose_name="Fiche technique de l'ouvrage")),
                ('profils', models.BooleanField(default=False, verbose_name='Profils entre les équipements et points d’eau')),
                ('dimensionnement_citernes', models.BooleanField(default=False, verbose_name='Dimensionnement des citernes')),
                ('devis_materiaux', models.BooleanField(default=False, verbose_name='Devis des matériaux')),
                ('devis_main_oeuvre', models.BooleanField(default=False, verbose_name='Devis de main-d’œuvre')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('ouvrage', models.OneToOneField(db_column='ouvrage_id', on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='dossier_technique_checklist', serialize=False, to='organization.ouvrage', verbose_name='Ouvrage')),
            ],
            options={
                'verbose_name': 'État du dossier technique AEPG',
                'verbose_name_plural': 'États des dossiers techniques AEPG',
                'db_table': 'ouvrage_dossier_technique_checklists',
            },
        ),
    ]
