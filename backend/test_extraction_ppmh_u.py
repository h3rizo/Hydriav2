#!/usr/bin/env python
"""
Test script pour vérifier l'extraction du format PPMH avec _U_
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.extracteurs_description import extraire_indemnite_rbf_ppmh

# Test 1: Format PPMH avec _U_ (cas utilisateur)
print("=" * 80)
print("TEST 1: Indemnité PPMH avec _U_1_5000_ - Ampetsapetsa PPMH2")
print("=" * 80)
description1 = "_RAVONIARIMANANA Lucie_Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2"
print(f"\nDescription: {description1}")
result1 = extraire_indemnite_rbf_ppmh(description1)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result1.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result1.get('ouvrage_obj')}")
print(f"  - Type indemnité: {result1.get('type_indemnite')}")
print(f"  - Point eau obj: {result1.get('point_eau_obj')}")

# Test 2: Format PPMH avec _U_ variations de chiffres
print("\n" + "=" * 80)
print("TEST 2: Indemnité PPMH avec _U_2_10000_ - Test Ouvrage")
print("=" * 80)
description2 = "_NOM Prénom_Indemnité PPMH_U_2_10000_Test Ouvrage"
print(f"\nDescription: {description2}")
result2 = extraire_indemnite_rbf_ppmh(description2)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result2.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result2.get('ouvrage_obj')}")
print(f"  - Type indemnité: {result2.get('type_indemnite')}")

# Test 3: Rétrocompatibilité - Format PPMH classique sans _U_ doit toujours fonctionner
print("\n" + "=" * 80)
print("TEST 3: Indemnité PPMH classique (rétrocompatibilité)")
print("=" * 80)
description3 = "_RAZAFINDRAVAO Pierette_Indemnité PPMH_Ambohijatovo PPMH"
print(f"\nDescription: {description3}")
result3 = extraire_indemnite_rbf_ppmh(description3)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result3.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result3.get('ouvrage_obj')}")
print(f"  - Type indemnité: {result3.get('type_indemnite')}")

print("\n" + "=" * 80)
print("Tests terminés!")
print("=" * 80)
