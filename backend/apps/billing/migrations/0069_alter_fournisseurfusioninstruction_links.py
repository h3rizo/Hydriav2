from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0068_fournisseurfusioninstruction'),
    ]

    operations = [
        migrations.AddField(
            model_name='fournisseurfusioninstruction',
            name='source_nom_snapshot',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Nom source snapshot'),
        ),
        migrations.AddField(
            model_name='fournisseurfusioninstruction',
            name='target_nom_snapshot',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Nom cible snapshot'),
        ),
        migrations.AlterField(
            model_name='fournisseurfusioninstruction',
            name='source_fournisseur',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fusion_instructions_source', to='billing.fournisseur', verbose_name='Fournisseur fusionne'),
        ),
        migrations.AlterField(
            model_name='fournisseurfusioninstruction',
            name='target_fournisseur',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fusion_instructions_target', to='billing.fournisseur', verbose_name='Fournisseur conserve'),
        ),
    ]
