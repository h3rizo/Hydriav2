from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0057_add_lieu_cin_fournisseur'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepenseService',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_facture', models.DateField(help_text="Date de la dépense / facture", verbose_name='Date de la facture')),
                ('designation', models.TextField(verbose_name='Désignation / Motif')),
                ('unite', models.CharField(max_length=120, verbose_name='Unité')),
                ('prix_unitaire', models.DecimalField(decimal_places=2, max_digits=18, verbose_name='Prix unitaire')),
                ('montant', models.DecimalField(decimal_places=2, max_digits=18, help_text='Quantité / base de calcul selon l\'unité', verbose_name='Montant')),
                ('total', models.DecimalField(decimal_places=2, max_digits=18, verbose_name='Total')),
                ('total_lettres', models.CharField(blank=True, max_length=500, verbose_name='Total en toutes lettres')),
                ('statut', models.CharField(choices=[('brouillon', 'Brouillon'), ('attente_signature', 'En attente 2e signature'), ('valide', 'Validé')], default='brouillon', max_length=20, verbose_name='Statut')),
                ('signataire_1', models.CharField(blank=True, max_length=255, verbose_name='Signataire 1')),
                ('date_signature_1', models.DateField(blank=True, null=True, verbose_name='Date signature 1')),
                ('signataire_2', models.CharField(blank=True, max_length=255, verbose_name='Signataire 2')),
                ('date_signature_2', models.DateField(blank=True, null=True, verbose_name='Date signature 2')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Mis à jour le')),
                ('fournisseur', models.ForeignKey(on_delete=models.deletion.PROTECT, related_name='depenses_services', to='billing.fournisseur', verbose_name='Fournisseur')),
            ],
            options={
                'verbose_name': 'Dépense de service',
                'verbose_name_plural': 'Dépenses de services',
                'db_table': 'depenses_services',
                'ordering': ['-date_facture', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='depenseservice',
            index=models.Index(fields=['fournisseur', 'date_facture'], name='idx_depense_fournisseur_date'),
        ),
        migrations.AddIndex(
            model_name='depenseservice',
            index=models.Index(fields=['statut'], name='idx_depense_statut'),
        ),
    ]
