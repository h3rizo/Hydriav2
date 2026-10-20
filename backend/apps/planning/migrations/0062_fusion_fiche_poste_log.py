import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0081_configsalaire_plafond_anciennete_autonomie_annees_and_more'),
        ('planning', '0061_planning_cible_composants'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FusionFichePosteLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('nom_cible_avant', models.CharField(max_length=255)),
                ('nom_cible_apres', models.CharField(max_length=255)),
                ('resume', models.JSONField(blank=True, default=dict)),
                ('donnees', models.JSONField(blank=True, default=dict)),
                ('annulee_le', models.DateTimeField(blank=True, null=True)),
                ('annulee_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fusions_fiches_poste_annulees', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fusions_fiches_poste', to=settings.AUTH_USER_MODEL)),
                ('fiche_cible', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fusions_log', to='employees.ficheposte')),
            ],
            options={
                'verbose_name': "Fusion d'activités de réparation",
                'verbose_name_plural': "Fusions d'activités de réparation",
                'db_table': 'planning_fusion_fiche_poste_log',
                'ordering': ['-created_at'],
            },
        ),
    ]
