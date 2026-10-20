# Module ouvrages - Modèles spécialisés pour les ouvrages d'infrastructure
from django.db import models
import uuid

# Ce module ne contient que des imports et alias pour éviter les doublons
# Les modèles réels sont définis dans les apps spécialisées :
# - apps.infrastructure : Adresse, CarteSociale, EquipementConstitutif
# - apps.billing : CompteurTete, ModaliteGestion, TarifVolumetrique, TarifVolumetriqueTranche, Releve
# - apps.inspections : Visite

# Import des modèles depuis leurs apps respectives pour compatibilité
from apps.infrastructure.models import Adresse, CarteSociale, EquipementConstitutif
from apps.billing.models import CompteurTete, ModaliteGestion, TarifVolumetrique, Releve, Fournisseur
from apps.inspections.models import Visite

# Définition locale du modèle manquant TarifVolumetriqueTranche
class TarifVolumetriqueTranche(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tarifvolumetrique = models.ForeignKey(TarifVolumetrique, on_delete=models.CASCADE, related_name='tranches_volumetriques')
    tranchesuperieur = models.IntegerField()  # Volume supérieur de la tranche en m³
    tarif = models.IntegerField()  # Tarif en Ariary par m³
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tarifsvolumetriques_tranches'
        verbose_name = 'Tranche de Tarif Volumétrique'
        verbose_name_plural = 'Tranches de Tarifs Volumétriques'
        unique_together = ['tarifvolumetrique', 'tranchesuperieur']

    def __str__(self):
        return f"Tranche jusqu'à {self.tranchesuperieur} m³ - {self.tarif} Ar/m³"

# Exports pour la compatibilité
__all__ = [
    'Adresse', 'CarteSociale', 'EquipementConstitutif',
    'CompteurTete', 'ModaliteGestion', 'TarifVolumetrique', 'TarifVolumetriqueTranche', 'Releve',
    'Visite', 'Fournisseur'
]