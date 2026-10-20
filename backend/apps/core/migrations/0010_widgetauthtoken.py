# Generated manually to isolate WidgetAuthToken from an unrelated
# pre-existing AlterField drift on DocumentationModule.workspace.

import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.core.models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_repairactivitypointtypepolicy'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WidgetAuthToken',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.CharField(db_index=True, default=apps.core.models.generate_widget_token, max_length=64, unique=True)),
                ('device_label', models.CharField(blank=True, default='', help_text="Ex: 'PC bureau', pour identifier ce token dans l'admin", max_length=120, verbose_name='Appareil')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='widget_auth_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Token widget desktop',
                'verbose_name_plural': 'Tokens widget desktop',
                'db_table': 'core_widget_auth_tokens',
            },
        ),
    ]
