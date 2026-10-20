import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0076_compteurs_abonnes'),
        ('employees', '0001_initial'),
    ]

    operations = [
        migrations.AddField(model_name='releve', name='terrain_local_uuid', field=models.UUIDField(blank=True, db_index=True, null=True, unique=True)),
        migrations.AddField(model_name='releve', name='terrain_agent', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='releves_terrain_saisis', to='employees.employe')),
        migrations.AddField(model_name='releve', name='terrain_captured_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='releve', name='terrain_latitude', field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='releve', name='terrain_longitude', field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='releve', name='terrain_gps_accuracy_m', field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='releve', name='terrain_distance_point_m', field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='releve', name='terrain_gps_anomaly', field=models.BooleanField(default=False)),
    ]
