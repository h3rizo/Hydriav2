from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0067_merge_20260530_2142'),
    ]

    operations = [
        migrations.CreateModel(
            name='FournisseurFusionInstruction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ancien_idxls', models.IntegerField(blank=True, null=True, verbose_name='Ancien IDxls')),
                ('nouvel_idxls', models.IntegerField(blank=True, null=True, verbose_name='Nouvel IDxls')),
                ('lignes_diamex_a_corriger', models.PositiveIntegerField(default=0, verbose_name='Lignes DiameX a corriger')),
                ('statut', models.CharField(choices=[('pending', 'En attente'), ('done', 'Corrige')], db_index=True, default='pending', max_length=20, verbose_name='Statut')),
                ('note', models.TextField(blank=True, default='', help_text='Texte montre aux admins pour corriger les codes fournisseurs dans DiameX.', verbose_name='Instruction')),
                ('commentaire_admin', models.TextField(blank=True, default='', verbose_name='Commentaire admin')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Cree le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Mis a jour le')),
                ('done_at', models.DateTimeField(blank=True, null=True, verbose_name='Corrige le')),
                ('source_fournisseur', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fusion_instructions_source', to='billing.fournisseur', verbose_name='Fournisseur fusionne')),
                ('target_fournisseur', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fusion_instructions_target', to='billing.fournisseur', verbose_name='Fournisseur conserve')),
            ],
            options={
                'verbose_name': 'Instruction fusion fournisseur',
                'verbose_name_plural': 'Instructions fusion fournisseurs',
                'db_table': 'fournisseur_fusion_instructions',
                'ordering': ['statut', '-created_at'],
            },
        ),
    ]
