import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('organization', '0033_gpsdataqualityreview'),
    ]

    operations = [
        migrations.CreateModel(
            name='OuvrageAlias',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('alias', models.CharField(max_length=255, verbose_name='Erreur ou variante')),
                ('alias_normalise', models.CharField(editable=False, max_length=255, unique=True, verbose_name='Clé normalisée')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ouvrage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aliases_extraction', to='organization.ouvrage')),
            ],
            options={
                'verbose_name': "Alias d'ouvrage",
                'verbose_name_plural': "Alias d'ouvrages",
                'db_table': 'ouvrage_aliases',
                'ordering': ['ouvrage__nom_ouvrage', 'alias'],
            },
        ),
    ]
