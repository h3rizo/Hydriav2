from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0063_merge_contact_into_telephone_fournisseur'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepenseServiceLigne',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('designation', models.TextField(verbose_name='Désignation')),
                ('unite', models.CharField(max_length=120, verbose_name='Unité')),
                ('prix_unitaire', models.DecimalField(decimal_places=2, max_digits=18, verbose_name='Prix unitaire')),
                ('montant', models.DecimalField(decimal_places=2, help_text="Quantité / base de calcul selon l'unité", max_digits=18, verbose_name='Montant')),
                ('total', models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name='Total')),
                ('ordre', models.PositiveIntegerField(default=0, verbose_name='Ordre')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Mis à jour le')),
                ('depense_service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lignes', to='billing.depenseservice', verbose_name='Dépense de service')),
            ],
            options={
                'verbose_name': 'Ligne de dépense de service',
                'verbose_name_plural': 'Lignes de dépenses de services',
                'db_table': 'depenses_services_lignes',
                'ordering': ['ordre', 'created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='depenseserviceligne',
            index=models.Index(fields=['depense_service', 'ordre'], name='billing_dep_depense_5968f8_idx'),
        ),
    ]
