from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0019_add_fournisseur_fields'),
        ('geography', '0012_exprovince_region'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdresseFournisseurDistrict',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('adresse', models.TextField(unique=True, verbose_name='Adresse fournisseur')),
                ('actif', models.BooleanField(default=True, verbose_name='Actif')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('district', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='adresses_fournisseurs', to='geography.district', verbose_name='District')),
            ],
            options={
                'verbose_name': 'Adresse fournisseur / district',
                'verbose_name_plural': 'Adresses fournisseurs / districts',
                'db_table': 'adresses_fournisseurs_districts',
                'ordering': ['adresse'],
            },
        ),
    ]
