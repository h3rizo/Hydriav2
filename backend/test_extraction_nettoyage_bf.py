#!/usr/bin/env python
"""
Test script pour vérifier l'extraction des descriptions Nettoyage BF sans montant
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.extracteurs_description import extraire_indemnite_rbf_ppmh

# Test 1: Format Nettoyage BF sans montant (cas 1)
print("=" * 80)
print("TEST 1: Nettoyage BF3 sans montant - Vohipenohely")
print("=" * 80)
description1 = "_RAMIADANA Francelette_Nettoyage BF3_Vohipenohely"
print(f"\nDescription: {description1}")
result1 = extraire_indemnite_rbf_ppmh(description1)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result1.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result1.get('ouvrage_obj')}")
print(f"  - Point eau IDXLS: {result1.get('point_eau_idxls')}")
print(f"  - Type indemnité: {result1.get('type_indemnite')}")

# Test 2: Format Nettoyage BF sans montant (cas 2)
print("\n" + "=" * 80)
print("TEST 2: Nettoyage BF2 sans montant - Anjohy")
print("=" * 80)
description2 = "_RAVOLOLONIRINA Harimalala Lydia_Nettoyage BF2_Anjohy"
print(f"\nDescription: {description2}")
result2 = extraire_indemnite_rbf_ppmh(description2)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result2.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result2.get('ouvrage_obj')}")
print(f"  - Point eau IDXLS: {result2.get('point_eau_idxls')}")
print(f"  - Type indemnité: {result2.get('type_indemnite')}")

# Test 3: Format Nettoyage BF AVEC montant (vérifier rétrocompatibilité)
print("\n" + "=" * 80)
print("TEST 3: Nettoyage BF3 avec montant - Vohipenohely (rétrocompatibilité)")
print("=" * 80)
description3 = "RAMIADANA Francelette_Nettoyage BF3_Fft_20000_Vohipenohely"
print(f"\nDescription: {description3}")
result3 = extraire_indemnite_rbf_ppmh(description3)
print(f"\nRésultat:")
print(f"  - Ouvrage nom: {result3.get('ouvrage_nom')}")
print(f"  - Ouvrage obj: {result3.get('ouvrage_obj')}")
print(f"  - Point eau IDXLS: {result3.get('point_eau_idxls')}")
print(f"  - Type indemnité: {result3.get('type_indemnite')}")

print("\n" + "=" * 80)
print("Tests terminés!")
print("=" * 80)
