# Generated manually to update Transfert models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0011_add_rapproche_and_utilisateur_to_stock'),
        ('organization', '0001_initial'),
        ('planning', '0001_initial'),
    ]

    operations = [
        # 1. Supprimer les anciennes colonnes de Transfert
        migrations.RemoveField(
            model_name='transfert',
            name='base_origine',
        ),
        migrations.RemoveField(
            model_name='transfert',
            name='base_destination',
        ),

        # 2. Ajouter les nouvelles colonnes magasin
        migrations.AddField(
            model_name='transfert',
            name='magasin_origine',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='transferts_sortants',
                to='organization.magasin',
                verbose_name="Magasin d'origine",
                null=True  # Temporairement nullable
            ),
        ),
        migrations.AddField(
            model_name='transfert',
            name='magasin_destination',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='transferts_entrants',
                to='organization.magasin',
                verbose_name='Magasin de destination',
                null=True  # Temporairement nullable
            ),
        ),

        # 3. Supprimer l'ancienne colonne product de TransfertItem
        migrations.RemoveField(
            model_name='transfertitem',
            name='product',
        ),

        # 4. Ajouter la nouvelle colonne designation
        migrations.AddField(
            model_name='transfertitem',
            name='designation',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='transfert_items',
                to='planning.designation',
                null=True  # Temporairement nullable
            ),
        ),

        # 5. Rendre les champs non-nullable (car table vide)
        migrations.AlterField(
            model_name='transfert',
            name='magasin_origine',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='transferts_sortants',
                to='organization.magasin',
                verbose_name="Magasin d'origine"
            ),
        ),
        migrations.AlterField(
            model_name='transfert',
            name='magasin_destination',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='transferts_entrants',
                to='organization.magasin',
                verbose_name='Magasin de destination'
            ),
        ),
        migrations.AlterField(
            model_name='transfertitem',
            name='designation',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='transfert_items',
                to='planning.designation'
            ),
        ),
    ]
