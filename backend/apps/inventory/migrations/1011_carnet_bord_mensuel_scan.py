# Generated manually for vehicules carnet scans workflow

import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '1010_alter_affectationvehicule_options_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CarnetBordMensuelScan',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('mois', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)], verbose_name='Mois')),
                ('annee', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(2000), django.core.validators.MaxValueValidator(2100)], verbose_name='Annee')),
                ('fichier_scan', models.FileField(upload_to='vehicules/carnets_bord/', verbose_name='Scan carnet')),
                ('commentaire', models.TextField(blank=True, null=True, verbose_name='Commentaire')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date de creation')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Date de modification')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='carnets_bord_vehicules_uploades', to=settings.AUTH_USER_MODEL, verbose_name='Charge par')),
                ('vehicule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='carnets_bord_scans', to='inventory.vehicule', verbose_name='Vehicule')),
            ],
            options={
                'verbose_name': 'Scan carnet de bord vehicule',
                'verbose_name_plural': 'Scans carnets de bord vehicules',
                'db_table': 'vehicules_carnets_bord_scans',
                'ordering': ['-annee', '-mois', 'vehicule__immatriculation', '-updated_at'],
                'unique_together': {('vehicule', 'annee', 'mois')},
            },
        ),
        migrations.AddIndex(
            model_name='carnetbordmensuelscan',
            index=models.Index(fields=['annee', 'mois'], name='vehicules_c_annee_8d2f1c_idx'),
        ),
        migrations.AddIndex(
            model_name='carnetbordmensuelscan',
            index=models.Index(fields=['vehicule', 'annee', 'mois'], name='vehicules_c_vehicul_ef0d16_idx'),
        ),
        migrations.AddIndex(
            model_name='carnetbordmensuelscan',
            index=models.Index(fields=['-updated_at'], name='vehicules_c_updated_27c601_idx'),
        ),
    ]

