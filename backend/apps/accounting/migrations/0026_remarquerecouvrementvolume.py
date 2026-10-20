from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0030_ouvrage_ouvrage_source'),
        ('employees', '0066_evaluation_developpement_fields'),
        ('accounting', '0025_remboursementcommune_infopaiementtaxecommune'),
    ]

    operations = [
        migrations.CreateModel(
            name='RemarqueRecouvrementVolume',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('annee', models.IntegerField(db_index=True, verbose_name='Annee')),
                ('mois', models.IntegerField(db_index=True, verbose_name='Mois')),
                ('remarque', models.TextField(blank=True, default='', verbose_name='Remarque')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date de creation')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Date de modification')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='remarques_recouvrement_volume_creees', to='employees.employe', verbose_name='Cree par')),
                ('ouvrage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='remarques_recouvrement_volume', to='organization.ouvrage', verbose_name='Ouvrage')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='remarques_recouvrement_volume_modifiees', to='employees.employe', verbose_name='Modifie par')),
            ],
            options={
                'verbose_name': 'Remarque recouvrement volume',
                'verbose_name_plural': 'Remarques recouvrement volume',
                'db_table': 'remarque_recouvrement_volume',
                'ordering': ['ouvrage__nom_ouvrage', 'annee', 'mois'],
                'unique_together': {('ouvrage', 'annee', 'mois')},
            },
        ),
    ]
