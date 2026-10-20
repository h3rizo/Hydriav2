#!/usr/bin/env python
"""
Test script pour vérifier l'extraction des descriptions Installation BP/BF avec texte entre crochets
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.extracteurs_description import extraire_installation_bp_bf

# Test 1: Format avec texte entre crochets
print("=" * 80)
print("TEST 1: Installation BP avec [facilité de paiement]")
print("=" * 80)
description1 = "Paiement pour installation BP_81_Vohipeno [facilité de paiement]"
print(f"\nDescription: {description1}")
result1 = extraire_installation_bp_bf(description1)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result1.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result1.get('ouvrage_obj')}")
print(f"  - Point eau IDXLS: {result1.get('point_eau_idxls')}")

# Test 2: Format classique sans crochets (rétrocompatibilité)
print("\n" + "=" * 80)
print("TEST 2: Installation BP classique sans crochets")
print("=" * 80)
description2 = "Paiement demande devis installation BP_78_Vohipeno"
print(f"\nDescription: {description2}")
result2 = extraire_installation_bp_bf(description2)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result2.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result2.get('ouvrage_obj')}")
print(f"  - Point eau IDXLS: {result2.get('point_eau_idxls')}")

# Test 3: Format avec nom de personne + crochets
print("\n" + "=" * 80)
print("TEST 3: Installation BP avec nom de personne + crochets")
print("=" * 80)
description3 = "_RAVAOJANAHARY Hanta_Paiement pour installation BP_01_Antsahafilo [facilité]"
print(f"\nDescription: {description3}")
result3 = extraire_installation_bp_bf(description3)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result3.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result3.get('ouvrage_obj')}")
print(f"  - Point eau IDXLS: {result3.get('point_eau_idxls')}")

# Test 4: Format avec crochets multiples
print("\n" + "=" * 80)
print("TEST 4: Installation BP avec crochets multiples")
print("=" * 80)
description4 = "Paiement pour installation BP_81_Vohipeno [facilité] [autre info]"
print(f"\nDescription: {description4}")
result4 = extraire_installation_bp_bf(description4)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result4.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result4.get('ouvrage_obj')}")
print(f"  - Point eau IDXLS: {result4.get('point_eau_idxls')}")

print("\n" + "=" * 80)
print("Tests terminés!")
print("=" * 80)
