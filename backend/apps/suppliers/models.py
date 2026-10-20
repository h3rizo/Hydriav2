# Import du modèle depuis l'app billing qui le définit déjà
from apps.billing.models import Fournisseur

# Export pour la compatibilité
__all__ = ['Fournisseur']