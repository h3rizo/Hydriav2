import uuid

import apps.core.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0012_intervention_widget_queue'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='widgetauthtoken',
            name='expires_at',
            field=models.DateTimeField(blank=True, db_index=True, help_text='Expiration du jeton. Null conserve la compatibilité des anciens clients.', null=True),
        ),
        migrations.AddField(
            model_name='widgetauthtoken',
            name='revoked_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.CreateModel(
            name='MobileRefreshToken',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.CharField(db_index=True, default=apps.core.models.generate_widget_token, max_length=64, unique=True)),
                ('device_id', models.UUIDField(db_index=True)),
                ('device_label', models.CharField(blank=True, default='', max_length=120)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mobile_refresh_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'core_mobile_refresh_tokens',
                'ordering': ['-created_at'],
            },
        ),
    ]
