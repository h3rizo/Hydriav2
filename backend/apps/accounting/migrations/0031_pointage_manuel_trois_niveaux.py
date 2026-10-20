# Circuit de pointage manuel à trois niveaux (caissière → responsable → directeur).
# Toutes les données de pointage restent dans Hydria : aucune colonne n'est
# ajoutée aux bases Access.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0030_alter_infopaiementtaxecommune_unique_together_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MoisPointage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fichier_source', models.CharField(max_length=255)),
                ('periode', models.DateField(help_text='Premier jour du mois comptable (Date mouvement)')),
                ('empreinte_validee', models.CharField(blank=True, max_length=64)),
                ('valide_le', models.DateTimeField(blank=True, null=True)),
                ('valide_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ObjetPointage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cle', models.CharField(max_length=400)),
                ('nature', models.CharField(choices=[('ligne', 'Ligne DiameX'), ('solde', 'Rapprochement')], max_length=20)),
                ('empreinte', models.CharField(blank=True, max_length=64)),
                ('niveau', models.PositiveSmallIntegerField(default=0)),
                ('correction', models.BooleanField(default=False)),
                ('solde_reference', models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ('justification', models.TextField(blank=True)),
                ('document', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='accounting.documentationcomptable')),
                ('mois', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='objets', to='accounting.moispointage')),
            ],
        ),
        migrations.CreateModel(
            name='DecisionPointage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('auteur_libelle', models.CharField(max_length=255)),
                ('role', models.CharField(blank=True, max_length=20)),
                ('action', models.CharField(max_length=30)),
                ('remarque', models.TextField(blank=True)),
                ('empreinte', models.CharField(blank=True, max_length=64)),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
                ('auteur', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('mois', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='decisions', to='accounting.moispointage')),
                ('objet', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='decisions', to='accounting.objetpointage')),
            ],
            options={
                'ordering': ['-cree_le', '-pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='moispointage',
            constraint=models.UniqueConstraint(fields=('fichier_source', 'periode'), name='pointage_mois_unique'),
        ),
        migrations.AddConstraint(
            model_name='objetpointage',
            constraint=models.UniqueConstraint(fields=('mois', 'cle'), name='pointage_objet_unique'),
        ),
        migrations.AddConstraint(
            model_name='objetpointage',
            constraint=models.CheckConstraint(condition=models.Q(('niveau__lte', 3)), name='pointage_niveau_valide'),
        ),
    ]
