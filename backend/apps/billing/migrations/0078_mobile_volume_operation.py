from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0077_releve_terrain_gps'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.CreateModel(
        name='MobileVolumeOperation',
        fields=[
            ('id', models.UUIDField(primary_key=True, editable=False, serialize=False)),
            ('payload_hash', models.CharField(max_length=64)),
            ('response', models.JSONField()),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
        ],
    ), migrations.CreateModel(
        name='MobileVolumeInvoiceSnapshot',
        fields=[
            ('releve', models.OneToOneField(primary_key=True, serialize=False, on_delete=django.db.models.deletion.CASCADE, to='billing.releve')),
            ('data', models.JSONField()),
        ],
    )]
