from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0003_pagevisit_userpresence'),
    ]

    operations = [
        migrations.CreateModel(
            name='StorageSnapshot',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('root_path', models.CharField(max_length=255, verbose_name='Racine surveillee')),
                ('total_bytes', models.BigIntegerField(verbose_name='Capacite totale')),
                ('used_bytes', models.BigIntegerField(verbose_name='Espace utilise')),
                ('free_bytes', models.BigIntegerField(verbose_name='Espace libre')),
                ('used_percent', models.DecimalField(decimal_places=2, max_digits=5, verbose_name='Pourcentage utilise')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date du snapshot')),
            ],
            options={
                'verbose_name': 'Snapshot stockage',
                'verbose_name_plural': 'Snapshots stockage',
                'db_table': 'storage_snapshots',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='storagesnapshot',
            index=models.Index(fields=['-created_at'], name='storage_sna_created_1da4f6_idx'),
        ),
        migrations.AddIndex(
            model_name='storagesnapshot',
            index=models.Index(fields=['root_path'], name='storage_sna_root_pa_08914d_idx'),
        ),
    ]
