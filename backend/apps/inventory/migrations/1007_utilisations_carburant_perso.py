from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '1006_add_carte_grise_to_vehicule'),
        ('employees', '0001_initial'),
        ('organization', '0001_initial'),
        ('planning', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UtilisationCarburantVehicule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_utilisation', models.DateField(verbose_name="Date d'utilisation")),
                ('quantite', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Quantité')),
                ('montant', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Montant')),
                ('source_type', models.CharField(choices=[('achat', 'Achat fournisseur'), ('stock', 'Stock magasin')], max_length=20, verbose_name='Source')),
                ('is_personnel', models.BooleanField(default=False, verbose_name='Usage personnel')),
                ('notes', models.TextField(blank=True, null=True, verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date de création')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Date de modification')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_carburant_vehicules', to=settings.AUTH_USER_MODEL, verbose_name='Créé par')),
                ('employe', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_carburant_vehicules', to='employees.employe', verbose_name='Employé')),
                ('magasin', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_carburant_vehicules', to='organization.magasin', verbose_name='Magasin')),
                ('purchase_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_carburant_vehicules', to='inventory.purchaseitem', verbose_name='Achat associé')),
                ('releve', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='carburants', to='inventory.relevécompteur', verbose_name='Relevé')),
                ('stock_movement', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_carburant_vehicules', to='inventory.stockmovement', verbose_name='Mouvement de stock')),
                ('vehicule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='utilisations_carburant', to='inventory.vehicule', verbose_name='Véhicule')),
            ],
            options={
                'verbose_name': 'Utilisation carburant véhicule',
                'verbose_name_plural': 'Utilisations carburant véhicules',
                'db_table': 'utilisations_carburant_vehicules',
                'ordering': ['-date_utilisation', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='UtilisationPersoVehicule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_debut', models.DateField(verbose_name='Date début')),
                ('date_fin', models.DateField(verbose_name='Date fin')),
                ('motif', models.TextField(blank=True, null=True, verbose_name='Motif')),
                ('statut', models.CharField(choices=[('demande', 'Demande'), ('refusee', 'Refusée'), ('approuvee', 'Approuvée'), ('en_cours', 'En cours'), ('retour_soumis', 'Retour soumis'), ('retour_valide', 'Retour validé')], default='demande', max_length=30, verbose_name='Statut')),
                ('regles_acceptees', models.BooleanField(default=False, verbose_name='Règles acceptées')),
                ('casque_obligatoire', models.BooleanField(default=False, verbose_name='Casque obligatoire')),
                ('directeur_avis', models.BooleanField(blank=True, null=True, verbose_name='Avis directeur')),
                ('directeur_commentaire', models.TextField(blank=True, null=True, verbose_name='Commentaire directeur')),
                ('date_avis_directeur', models.DateTimeField(blank=True, null=True, verbose_name='Date avis directeur')),
                ('chef_commentaire', models.TextField(blank=True, null=True, verbose_name='Commentaire chef')),
                ('date_validation_chef', models.DateTimeField(blank=True, null=True, verbose_name='Date validation chef')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date de création')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Date de modification')),
                ('carburant_apres', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_perso_apres', to='inventory.utilisationcarburantvehicule', verbose_name='Carburant après')),
                ('carburant_avant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_perso_avant', to='inventory.utilisationcarburantvehicule', verbose_name='Carburant avant')),
                ('chef', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_perso_validees_chef', to='employees.employe', verbose_name='Chef validateur')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_perso_vehicules', to=settings.AUTH_USER_MODEL, verbose_name='Créé par')),
                ('directeur', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utilisations_perso_validees_directeur', to='employees.employe', verbose_name='Directeur')),
                ('employe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='utilisations_perso_vehicules', to='employees.employe', verbose_name='Employé demandeur')),
                ('vehicule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='utilisations_perso', to='inventory.vehicule', verbose_name='Véhicule')),
            ],
            options={
                'verbose_name': 'Utilisation personnelle véhicule',
                'verbose_name_plural': 'Utilisations personnelles véhicules',
                'db_table': 'utilisations_perso_vehicules',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='utilisationcarburantvehicule',
            index=models.Index(fields=['vehicule', '-date_utilisation'], name='utilisatio_vehicul_3e3653_idx'),
        ),
        migrations.AddIndex(
            model_name='utilisationcarburantvehicule',
            index=models.Index(fields=['-date_utilisation'], name='utilisatio_-date_u_67fa48_idx'),
        ),
        migrations.AddIndex(
            model_name='utilisationpersovehicule',
            index=models.Index(fields=['vehicule', '-created_at'], name='utilisatio_vehicul_079a0b_idx'),
        ),
        migrations.AddIndex(
            model_name='utilisationpersovehicule',
            index=models.Index(fields=['employe', '-created_at'], name='utilisatio_employe_21a536_idx'),
        ),
        migrations.AddIndex(
            model_name='utilisationpersovehicule',
            index=models.Index(fields=['statut'], name='utilisatio_statut_2c09c7_idx'),
        ),
    ]
