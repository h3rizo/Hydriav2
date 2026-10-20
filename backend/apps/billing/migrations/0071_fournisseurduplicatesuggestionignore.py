from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0070_fournisseurfusioninstruction_lignes_diamex_details'),
    ]

    operations = [
        migrations.CreateModel(
            name='FournisseurDuplicateSuggestionIgnore',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('signature', models.CharField(max_length=500, unique=True, verbose_name='Signature suggestion')),
                ('label', models.CharField(blank=True, default='', max_length=255, verbose_name='Libelle suggestion')),
                ('reason', models.TextField(blank=True, default='', verbose_name='Raison')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Cree le')),
            ],
            options={
                'verbose_name': 'Suggestion doublon ignoree',
                'verbose_name_plural': 'Suggestions doublons ignorees',
                'db_table': 'fournisseur_duplicate_suggestion_ignores',
                'ordering': ['-created_at'],
            },
        ),
    ]
