import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0075_changementcompteurtete'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CompteurAbonne',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('numero', models.CharField(max_length=100, unique=True, verbose_name='Numero de compteur')),
                ('marque', models.CharField(blank=True, max_length=100, null=True)),
                ('modele', models.CharField(blank=True, max_length=100, null=True)),
                ('date_installation', models.DateField(verbose_name="Date d'installation")),
                ('date_retrait', models.DateField(blank=True, null=True)),
                ('index_initial', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('index_retrait', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('statut', models.CharField(choices=[('operationnel', 'Operationnel'), ('hors_service', 'Hors service'), ('perdu', 'Perdu ou vole')], default='operationnel', max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('point_eau', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='compteurs_abonnes', to='billing.pointeau')),
            ],
            options={
                'db_table': 'compteurs_abonnes',
                'ordering': ['point_eau_id', '-date_installation', '-created_at'],
                'indexes': [models.Index(fields=['point_eau', 'statut'], name='compteurs_a_point_e_be415e_idx')],
            },
        ),
        migrations.AddField(
            model_name='pointeau',
            name='compteur_abonne_actuel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='points_eau_actuels', to='billing.compteurabonne', verbose_name='Compteur abonne actuel'),
        ),
        migrations.AddField(
            model_name='releve',
            name='compteur_abonne',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='releves', to='billing.compteurabonne', verbose_name='Compteur abonne releve'),
        ),
        migrations.AddField(
            model_name='releve',
            name='origine_calcul',
            field=models.CharField(choices=[('legacy', 'Historique'), ('simple', 'Compteur unique'), ('multi_compteur', 'Changement de compteur')], default='legacy', help_text='Les anciennes lignes restent en mode historique sans recalcul.', max_length=20),
        ),
        migrations.CreateModel(
            name='ChangementCompteurAbonne',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_changement', models.DateField()),
                ('index_reference_ancien', models.DecimalField(decimal_places=2, max_digits=12)),
                ('index_retrait', models.DecimalField(decimal_places=2, max_digits=12)),
                ('index_initial_nouveau', models.DecimalField(decimal_places=2, max_digits=12)),
                ('motif', models.CharField(choices=[('defectueux', 'Compteur defectueux'), ('bloque', 'Compteur bloque'), ('casse', 'Compteur casse'), ('fin_vie', 'Fin de vie'), ('vole', 'Compteur vole'), ('preventif', 'Remplacement preventif'), ('autre', 'Autre')], max_length=30)),
                ('explication', models.TextField()),
                ('ancien_compteur_illisible', models.BooleanField(default=False)),
                ('consommation_ancienne_estimee', models.DecimalField(blank=True, decimal_places=2, help_text="Utilisee uniquement si l'ancien compteur est illisible.", max_digits=12, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ancien_compteur', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='changement_sortant', to='billing.compteurabonne')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='changements_compteurs_abonnes_crees', to=settings.AUTH_USER_MODEL)),
                ('nouveau_compteur', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='changement_entrant', to='billing.compteurabonne')),
                ('point_eau', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='changements_compteurs_abonnes', to='billing.pointeau')),
                ('releve_facture', models.ForeignKey(blank=True, help_text='Premier releve qui additionne les consommations avant et apres remplacement.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='changements_compteur_factures', to='billing.releve')),
                ('releve_precedent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='changements_compteur_apres_releve', to='billing.releve')),
            ],
            options={
                'db_table': 'changements_compteurs_abonnes',
                'ordering': ['-date_changement', '-created_at'],
                'indexes': [models.Index(fields=['point_eau', 'date_changement'], name='changements_point_e_eb3e70_idx'), models.Index(fields=['point_eau', 'releve_facture'], name='changements_point_e_54d000_idx')],
            },
        ),
        migrations.CreateModel(
            name='SegmentConsommationReleve',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ordre', models.PositiveSmallIntegerField(default=1)),
                ('type_segment', models.CharField(choices=[('normal', 'Compteur de la periode'), ('avant_changement', 'Avant changement'), ('apres_changement', 'Apres changement'), ('estime', 'Ancien compteur illisible - estimation')], default='normal', max_length=30)),
                ('date_debut', models.DateField(blank=True, null=True)),
                ('date_fin', models.DateField(blank=True, null=True)),
                ('index_debut', models.DecimalField(decimal_places=2, max_digits=12)),
                ('index_fin', models.DecimalField(decimal_places=2, max_digits=12)),
                ('volume', models.DecimalField(decimal_places=2, max_digits=12)),
                ('est_estime', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('compteur', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='segments_consommation', to='billing.compteurabonne')),
                ('releve', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='segments_consommation', to='billing.releve')),
            ],
            options={
                'db_table': 'segments_consommation_releves',
                'ordering': ['releve_id', 'ordre'],
                'constraints': [models.UniqueConstraint(fields=('releve', 'ordre'), name='uniq_segment_releve_ordre')],
            },
        ),
    ]
