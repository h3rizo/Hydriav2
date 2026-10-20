import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.views_verification_paiements import detecter_type_paiement, normaliser_texte

# Test avec la description
description = "_STAG RAZAFIMANANTSOA Hadji Jarrel_Indemnité de stage_1 x 8 000Ar du 30_2025 01"

print("=" * 60)
print("TEST DE DÉTECTION INDEMNITÉ DE STAGE")
print("=" * 60)
print(f"\nDescription: {description}")
print(f"\nDescription normalisée: {normaliser_texte(description)}")
print(f"\nType détecté: {detecter_type_paiement(description)}")

# Test avec différentes variantes
variantes = [
    "_STAG Test_Indemnité de stage_2025 01",
    "_STAG Test_indemnité de stage_2025 01",
    "_STAG Test_Indemnite de stage_2025 01",
]

print("\n" + "=" * 60)
print("TESTS AVEC VARIANTES")
print("=" * 60)
for var in variantes:
    type_det = detecter_type_paiement(var)
    print(f"\n{var}")
    print(f"  → Normalisé: {normaliser_texte(var)}")
    print(f"  → Type: {type_det}")
