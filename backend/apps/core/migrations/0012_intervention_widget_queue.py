import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_widgetauthtoken_scope'),
        ('planning', '0060_merge_planning_nature_stock'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='InterventionWidgetState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('monitoring_started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('current_planning', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='planning.planning')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='intervention_widget_state', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'État du widget des interventions',
                'verbose_name_plural': 'États du widget des interventions',
                'db_table': 'core_intervention_widget_states',
            },
        ),
        migrations.CreateModel(
            name='InterventionWidgetRead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seen_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('planning', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='widget_reads', to='planning.planning')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='intervention_widget_reads', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Lecture du widget des interventions',
                'verbose_name_plural': 'Lectures du widget des interventions',
                'db_table': 'core_intervention_widget_reads',
                'indexes': [models.Index(fields=['user', '-seen_at'], name='core_int_widget_user_seen_idx')],
                'constraints': [models.UniqueConstraint(fields=('user', 'planning'), name='unique_intervention_widget_read')],
            },
        ),
    ]
