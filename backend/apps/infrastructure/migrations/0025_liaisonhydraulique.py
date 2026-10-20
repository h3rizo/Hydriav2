from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0061_rename_idx_depense_fournisseur_date_depenses_se_fournis_ea441f_idx_and_more'),
        ('organization', '0030_ouvrage_ouvrage_source'),
        ('infrastructure', '0024_equipementconstitutif_updated_by'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiaisonHydraulique',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ordre', models.PositiveIntegerField(default=0, verbose_name='Ordre')),
                ('actif', models.BooleanField(default=True, verbose_name='Actif')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('amont_compteur_tete', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='liaisons_sortantes', to='billing.compteurtete', verbose_name='Compteur amont')),
                ('amont_equipement', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='liaisons_sortantes', to='infrastructure.equipementconstitutif', verbose_name='Equipement amont')),
                ('amont_point_eau', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='liaisons_sortantes', to='billing.pointeau', verbose_name="Point d'eau amont")),
                ('aval_compteur_tete', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='liaisons_entrantes', to='billing.compteurtete', verbose_name='Compteur aval')),
                ('aval_equipement', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='liaisons_entrantes', to='infrastructure.equipementconstitutif', verbose_name='Equipement aval')),
                ('aval_point_eau', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='liaisons_entrantes', to='billing.pointeau', verbose_name="Point d'eau aval")),
                ('ouvrage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='liaisons_hydrauliques', to='organization.ouvrage', verbose_name='Ouvrage')),
            ],
            options={
                'verbose_name': 'Liaison hydraulique',
                'verbose_name_plural': 'Liaisons hydrauliques',
                'db_table': 'liaisons_hydrauliques',
                'ordering': ['ouvrage__nom_ouvrage', 'ordre', 'created_at'],
            },
        ),
    ]
