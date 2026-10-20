import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0036_merge_20260917_1415'),
        ('employees', '0086_contrat_quotite_temps_travail'),
        ('inventory', '1019_alter_fichestock_operation_type_and_more'),
        ('organization', '0038_ouvrage_marque_non_fonctionnel'),
        ('planning', '0065_groupes_types_activites'),
    ]

    operations = [
        migrations.CreateModel(
            name='SaisieComptableArticle',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('mode', models.CharField(choices=[('stock', 'Entree en stock'), ('hors_stock', 'Hors stock (livraison directe)')], default='stock', max_length=12)),
                ('quantite', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Quantite achetee')),
                ('quantite_recue', models.DecimalField(decimal_places=2, default=0, help_text='Le reste (quantite - recue) est un reste a livrer', max_digits=10, verbose_name='Quantite recue / livree')),
                ('prix_unitaire', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('destination_type', models.CharField(blank=True, choices=[('ouvrage', 'Ouvrage / chantier'), ('employe', 'Employe (equipement)'), ('vehicule', 'Vehicule')], default='', max_length=10)),
                ('appliquee_at', models.DateTimeField(blank=True, null=True)),
                ('fiche_stock_id', models.CharField(blank=True, default='', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('designation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lignes_saisie_comptable', to='planning.designation', verbose_name='Designation')),
                ('employe', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='articles_saisie_comptable', to='employees.employe')),
                ('ouvrage', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='articles_saisie_comptable', to='organization.ouvrage')),
                ('saisie', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='articles', to='accounting.saisiecomptable', verbose_name='Saisie')),
                ('vehicule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='articles_saisie_comptable', to='inventory.vehicule')),
            ],
            options={
                'verbose_name': 'Article de saisie comptable',
                'verbose_name_plural': 'Articles de saisie comptable',
                'db_table': 'saisie_comptable_articles',
                'ordering': ['created_at'],
                'indexes': [
                    models.Index(fields=['saisie'], name='saisie_comp_saisie__606648_idx'),
                    models.Index(fields=['mode', 'appliquee_at'], name='saisie_comp_mode_f249ce_idx'),
                ],
            },
        ),
    ]
