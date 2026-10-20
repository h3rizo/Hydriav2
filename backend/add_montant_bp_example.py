"""Script pour ajouter des montants d'exemple aux demandes BP"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.billing.models import PointEau
from decimal import Decimal

# Prendre les 5 premières demandes BP et leur ajouter des montants
bps = PointEau.objects.filter(type_point_eau__nom_type='BP')[:5]

print("=== AJOUT DE MONTANTS D'EXEMPLE ===")
for i, bp in enumerate(bps, 1):
    montant = Decimal('50000') * i  # 50K, 100K, 150K, 200K, 250K
    bp.montant_demande_bp = montant
    bp.save()
    print(f"{i}. {bp.code_point_eau} - {bp.nomabonne}: {montant} Ar ajouté")

print("\n✅ 5 demandes BP ont maintenant des montants")
print("Les boutons d'export 'Demande' devraient maintenant apparaître pour ces 5 demandes")
