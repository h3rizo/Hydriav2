import os

filepath = r"c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\apps\employees\models.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

missing_header = """from django.db import models
from django.contrib.auth.models import User
from apps.organization.models import Organisation, Base, Compte
import uuid
from decimal import Decimal, ROUND_HALF_UP

# Import des modèles famille (frais médicaux et scolarité)
from .models_famille import FamilleEmploye, FraisMedicaux, FraisScolarite

# Import des modèles congés et permissions
from .models_conges import TypePermission, DemandeConge, SoldeConge

# Import des modèles récupérations
from .models_recuperations import Recuperation, SoldeRecuperation

# Import des modèles d'évaluation
from .models_evaluation import FichePoste, Evaluation, EvaluationDetail

# Import des modèles gardiens
from .models_gardiens import RotationGardien, HeuresSupplementairesGardien

# Import des modèles de revalorisation salariale
from .models_revalorisation import GrilleSalariale, Revalorisation


class Poste(models.Model):
    \"\"\"Modèle représentant les postes de travail dans les organisations\"\"\"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_poste = models.CharField(max_length=255, verbose_name="Nom du poste")
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='postes',
        db_column='organisation_id'
    )
    tarif_indemnite = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Tarif d'indemnité"
    )
    compte_salaire = models.ForeignKey(
        Compte,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='postes_salaire',
        db_column='compte_salaire_id',
"""

with open(filepath, "w", encoding="utf-8") as f:
    f.write(missing_header + content)

print("Fixed")
