from django.db import migrations, models
import django.db.models.deletion
import uuid
import apps.organization.models


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0030_ouvrage_ouvrage_source'),
    ]

    operations = [
        migrations.CreateModel(
            name='OuvrageDossierTechnique',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('fichier', models.FileField(upload_to=apps.organization.models.ouvrage_dossier_technique_upload_to, verbose_name='Fichier')),
                ('nom_affichage', models.CharField(blank=True, max_length=255, verbose_name='Nom d affichage')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ouvrage', models.ForeignKey(db_column='ouvrage_id', on_delete=django.db.models.deletion.CASCADE, related_name='dossiers_techniques', to='organization.ouvrage', verbose_name='Ouvrage')),
            ],
            options={
                'verbose_name': 'Dossier technique ouvrage',
                'verbose_name_plural': 'Dossiers techniques ouvrages',
                'db_table': 'ouvrage_dossiers_techniques',
                'ordering': ['-created_at', 'nom_affichage'],
            },
        ),
    ]
