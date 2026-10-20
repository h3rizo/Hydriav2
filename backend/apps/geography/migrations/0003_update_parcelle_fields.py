# Generated manually - Update parcelle fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('geography', '0002_add_fokontany'),
    ]

    operations = [
        # Renommer nom_parcelle en reference_parcelle
        migrations.RenameField(
            model_name='parcelle',
            old_name='nom_parcelle',
            new_name='reference_parcelle',
        ),

        # Ajouter les nouveaux champs démographiques
        migrations.AddField(
            model_name='parcelle',
            name='nombre_habitants',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Nombre d'habitants"),
        ),

        migrations.AddField(
            model_name='parcelle',
            name='nombre_menages',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Nombre de ménages'),
        ),

        migrations.AddField(
            model_name='parcelle',
            name='source_donnees',
            field=models.CharField(blank=True, help_text='Source des données démographiques (ex: Recensement 2018, Enquête locale 2023)', max_length=255, null=True, verbose_name='Source des données'),
        ),

        # Mettre à jour les contraintes unique_together
        migrations.AlterUniqueTogether(
            name='parcelle',
            unique_together={('reference_parcelle', 'village')},
        ),
    ]