import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0072_pointeau_problematique_paiement'),
        ('core', '0008_repairactivityequipmentpolicy'),
        ('employees', '0069_grillesalaire_nb_dimanches_travailles'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RepairActivityPointTypePolicy',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('allowed_activities', models.ManyToManyField(
                    blank=True,
                    related_name='allowed_point_type_repair_policies',
                    to='employees.ficheposte',
                    verbose_name='Activités autorisées',
                )),
                ('type_point_eau', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='repair_activity_policy',
                    to='billing.typepointeau',
                    verbose_name="Type de point d'eau",
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='updated_repair_activity_point_type_policies',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': "Règle d'activités de réparation par type de point d'eau",
                'verbose_name_plural': "Règles d'activités de réparation par type de point d'eau",
                'db_table': 'core_repair_activity_point_type_policies',
                'ordering': ['type_point_eau__nom_type'],
            },
        ),
    ]
