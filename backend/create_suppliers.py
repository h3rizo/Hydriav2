"""Créer des fournisseurs d'exemple"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.inventory.models import Supplier

fournisseurs = [
    {"supplier_name": "SARL MATERIEL HYDRO", "supplier_contact": "M. Rakoto", "supplier_phone": "+261 34 12 345 67", "supplier_email": "contact@materielhydro.mg"},
    {"supplier_name": "ETS ACCESSOIRES WATER", "supplier_contact": "Mme Ratsimbazafy", "supplier_phone": "+261 33 98 765 43", "supplier_email": "info@accessoireswater.mg"},
    {"supplier_name": "COMEX MADAGASCAR", "supplier_contact": "M. Randrianaivo", "supplier_phone": "+261 34 56 789 01", "supplier_email": "comex@example.mg"},
    {"supplier_name": "HYDRO SUPPLY", "supplier_contact": "M. Andrianasolo", "supplier_phone": "+261 32 11 223 34", "supplier_email": "contact@hydrosupply.mg"},
    {"supplier_name": "MATERIAU LOCAL TANA", "supplier_contact": "M. Raharison", "supplier_phone": "+261 33 44 556 67", "supplier_email": "materiau@local.mg"},
]

print("=== CRÉATION DES FOURNISSEURS ===")
for data in fournisseurs:
    supplier, created = Supplier.objects.get_or_create(
        supplier_name=data["supplier_name"],
        defaults={
            "supplier_contact": data.get("supplier_contact", ""),
            "supplier_phone": data.get("supplier_phone", ""),
            "supplier_email": data.get("supplier_email", ""),
            "is_active": True
        }
    )
    if created:
        print(f"✓ Créé: {supplier.supplier_name}")
    else:
        print(f"  Existe déjà: {supplier.supplier_name}")

print(f"\nTotal fournisseurs: {Supplier.objects.count()}")
