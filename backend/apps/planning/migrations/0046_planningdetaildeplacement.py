from django.db import migrations, models
import django.db.models.deletion
import uuid


def migrate_planning_detail_deplacements(apps, schema_editor):
    PlanningDetail = apps.get_model('planning', 'PlanningDetail')
    PlanningDetailDeplacement = apps.get_model('planning', 'PlanningDetailDeplacement')

    for detail in PlanningDetail.objects.exclude(trajet__isnull=True).exclude(trajet=''):
        PlanningDetailDeplacement.objects.update_or_create(
            planning_detail_id=detail.id,
            defaults={
                'trajet': detail.trajet,
                'point_a_id': detail.point_a_id,
                'point_b_id': detail.point_b_id,
                'moyen_transport': detail.moyen_transport,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0045_fix_planning_employees_uuid'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlanningDetailDeplacement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('trajet', models.CharField(choices=[('aller', 'Aller'), ('retour', 'Retour')], max_length=20, verbose_name='Trajet')),
                ('moyen_transport', models.CharField(blank=True, choices=[('taxi-brousse', 'Taxi-brousse'), ('pirogue', 'Pirogue'), ('bac', 'Bac')], max_length=20, null=True, verbose_name='Moyen de transport')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('planning_detail', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='deplacement', to='planning.planningdetail', verbose_name='Detail planning')),
                ('point_a', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='planning_detail_deplacements_point_a', to='geography.village', verbose_name='Point A (Village)')),
                ('point_b', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='planning_detail_deplacements_point_b', to='geography.village', verbose_name='Point B (Village)')),
            ],
            options={
                'db_table': 'planningdetail_deplacements',
                'verbose_name': 'Deplacement de detail planning',
                'verbose_name_plural': 'Deplacements de detail planning',
            },
        ),
        migrations.RunPython(migrate_planning_detail_deplacements, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='planningdetail',
            name='moyen_transport',
        ),
        migrations.RemoveField(
            model_name='planningdetail',
            name='point_a',
        ),
        migrations.RemoveField(
            model_name='planningdetail',
            name='point_b',
        ),
        migrations.RemoveField(
            model_name='planningdetail',
            name='trajet',
        ),
    ]
