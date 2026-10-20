from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0030_ouvrage_ouvrage_source'),
        ('geography', '0001_initial'),
        ('accounting', '0026_remarquerecouvrementvolume'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImputationRemboursementTaxeCommune',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('annee', models.IntegerField(db_index=True, verbose_name='Année')),
                ('montant_impute', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Montant à rembourser cette année')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('commune', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='imputations_remboursement_taxe', to='geography.commune', verbose_name='Commune')),
                ('organisation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='imputations_remboursement_taxe', to='organization.organisation')),
            ],
            options={
                'verbose_name': 'Imputation remboursement taxe commune',
                'verbose_name_plural': 'Imputations remboursements taxes communes',
                'db_table': 'imputation_remboursement_taxe_commune',
                'unique_together': {('commune', 'organisation', 'annee')},
            },
        ),
    ]
