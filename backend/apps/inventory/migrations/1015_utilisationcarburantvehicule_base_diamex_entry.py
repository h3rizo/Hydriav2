from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0001_initial'),
        ('inventory', '1014_add_ajustement_to_fichestock'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilisationcarburantvehicule',
            name='base_diamex_entry',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_carburant_vehicules', to='accounting.basediamex', verbose_name='Ligne comptable associee'),
        ),
    ]
