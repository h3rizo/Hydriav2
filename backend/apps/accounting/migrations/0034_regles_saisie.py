"""
Regles de saisie guidee par compte + fournisseurs autorises par compte.

Migration ecrite a la main (cf. memoire projet : desync d'etat sur l'app
accounting). Ne cree que 2 modeles isoles.

Sur le VPS, le graphe de migrations a des branches supplementaires (merges) :
apres deploiement, lancer  `python manage.py makemigrations --merge --noinput`
pour reconcilier (comme pour 0032_scanextraction -> 0033_merge).
"""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0032_scanextraction"),
        ("organization", "0001_initial"),
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RegleSaisieCompte",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("compte_cible", models.CharField(help_text="Code compte exact (ex: 601011) ou prefixe (ex: 641, 218)", max_length=20)),
                ("est_prefixe", models.BooleanField(default=False, help_text="Si coche, s'applique a tous les comptes commencant par compte_cible")),
                ("libelle", models.CharField(blank=True, default="", max_length=255, verbose_name="Libelle de la regle")),
                ("mode", models.CharField(choices=[("fournisseur", "Depense fournisseur"), ("employe", "Depense / charge employe"), ("libre", "Ecriture libre"), ("recette", "Recette (ouvrage / abonne)")], max_length=20)),
                ("sens", models.CharField(choices=[("out", "Depense (Out)"), ("in", "Recette (In)")], max_length=3)),
                ("config", models.JSONField(blank=True, default=dict, verbose_name="Configuration (champs + gabarit description)")),
                ("actif", models.BooleanField(default=True)),
                ("ordre", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organisation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="regles_saisie_compte", to="organization.organisation")),
            ],
            options={
                "verbose_name": "Regle de saisie par compte",
                "verbose_name_plural": "Regles de saisie par compte",
                "db_table": "regle_saisie_compte",
                "ordering": ["organisation_id", "compte_cible"],
                "unique_together": {("organisation", "compte_cible")},
            },
        ),
        migrations.CreateModel(
            name="CompteFournisseurAutorise",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("compte_code", models.CharField(help_text="Code compte exact", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("fournisseur", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comptes_autorises", to="billing.fournisseur")),
                ("organisation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comptes_fournisseurs_autorises", to="organization.organisation")),
            ],
            options={
                "verbose_name": "Fournisseur autorise par compte",
                "verbose_name_plural": "Fournisseurs autorises par compte",
                "db_table": "compte_fournisseur_autorise",
                "unique_together": {("organisation", "compte_code", "fournisseur")},
            },
        ),
        migrations.AddIndex(
            model_name="reglesaisiecompte",
            index=models.Index(fields=["organisation", "actif"], name="regle_saisie_org_actif_idx"),
        ),
        migrations.AddIndex(
            model_name="reglesaisiecompte",
            index=models.Index(fields=["organisation", "est_prefixe"], name="regle_saisie_org_prefixe_idx"),
        ),
        migrations.AddIndex(
            model_name="comptefournisseurautorise",
            index=models.Index(fields=["organisation", "compte_code"], name="cfa_org_compte_idx"),
        ),
    ]
