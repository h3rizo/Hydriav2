from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0021_add_paiements_forfaitaires_ids_to_diamex'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExplicationPaiementForfaitaire',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('annee', models.IntegerField(verbose_name='Année')),
                ('explication', models.TextField(blank=True, verbose_name='Explication')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Modifié le')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='explications_forfaitaire_creees', to='employees.employe', verbose_name='Créé par')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='explications_forfaitaire_modifiees', to='employees.employe', verbose_name='Modifié par')),
                ('ouvrage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='explications_forfaitaire', to='organization.ouvrage', verbose_name='Ouvrage')),
            ],
            options={
                'verbose_name': 'Explication paiement forfaitaire',
                'verbose_name_plural': 'Explications paiements forfaitaires',
                'db_table': 'explications_paiements_forfaitaires',
                'ordering': ['-annee', 'ouvrage_id'],
                'unique_together': {('ouvrage', 'annee')},
            },
        ),
    ]

