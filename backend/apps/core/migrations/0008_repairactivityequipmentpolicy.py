import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_documentationmodule_workspace'),
        ('employees', '0069_grillesalaire_nb_dimanches_travailles'),
        ('infrastructure', '0028_alter_citerne_volume_half_step'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RepairActivityEquipmentPolicy',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('allowed_activities', models.ManyToManyField(
                    blank=True,
                    related_name='allowed_equipment_repair_policies',
                    to='employees.ficheposte',
                    verbose_name='Activités autorisées',
                )),
                ('type_equipement', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='repair_activity_policy',
                    to='infrastructure.typeequipement',
                    verbose_name="Type d'équipement",
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='updated_repair_activity_equipment_policies',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': "Règle d'activités de réparation par type d'équipement",
                'verbose_name_plural': "Règles d'activités de réparation par type d'équipement",
                'db_table': 'core_repair_activity_equipment_policies',
                'ordering': ['type_equipement__nom_type'],
            },
        ),
    ]
