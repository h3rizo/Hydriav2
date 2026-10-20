from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0001_initial'),  # Assumant que organization a une migration initiale
        ('planning', '0015_create_designation_type_activite'),
    ]

    operations = [
        # Supprimer l'ancienne table s'il existe avec l'ancienne structure
        migrations.RunSQL(
            "DROP TABLE IF EXISTS designationcomptes CASCADE;",
            "-- Pas de rollback possible"
        ),

        # Créer le nouveau modèle DesignationCompte (en tant que liaison)
        migrations.CreateModel(
            name='DesignationCompte',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True, verbose_name='Actif')),
                ('notes', models.TextField(blank=True, null=True, verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('compte', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='designations', to='organization.compte')),
                ('designation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comptes', to='planning.designation')),
            ],
            options={
                'verbose_name': 'Liaison Désignation-Compte',
                'verbose_name_plural': 'Liaisons Désignation-Comptes',
                'db_table': 'designationcomptes',
            },
        ),

        # Ajouter la contrainte unique
        migrations.AlterUniqueTogether(
            name='designationcompte',
            unique_together={('designation', 'compte')},
        ),
    ]