import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('geography', '0014_repair_missing_photo_columns'),
        ('organization', '0032_ouvragedossiertechniquechecklist'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='GPSDataQualityReview',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('entity_type', models.CharField(choices=[('point_eau', "Point d'eau"), ('equipement', 'Équipement')], max_length=20)),
                ('entity_id', models.UUIDField()),
                ('status', models.CharField(choices=[('confirmed', 'Position correcte et expliquée'), ('to_correct', 'Correction nécessaire')], max_length=20)),
                ('explanation', models.TextField(blank=True, default='')),
                ('latitude_snapshot', models.DecimalField(blank=True, decimal_places=8, max_digits=11, null=True)),
                ('longitude_snapshot', models.DecimalField(blank=True, decimal_places=8, max_digits=11, null=True)),
                ('distance_km_snapshot', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ('reviewed_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reference_village', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gps_quality_reviews', to='geography.village')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gps_quality_reviews', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'gps_data_quality_reviews', 'unique_together': {('entity_type', 'entity_id')}},
        ),
        migrations.AddIndex(model_name='gpsdataqualityreview', index=models.Index(fields=['entity_type', 'status'], name='gps_quality_entity_status_idx')),
        migrations.AddIndex(model_name='gpsdataqualityreview', index=models.Index(fields=['entity_id'], name='gps_quality_entity_id_idx')),
    ]
