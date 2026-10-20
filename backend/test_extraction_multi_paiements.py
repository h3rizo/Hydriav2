#!/usr/bin/env python
"""
Test script pour vérifier l'extraction de multi-paiements
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_paiement_volume

# Test 1: Format avec ouvrage répété
print("=" * 80)
print("TEST 1: Format avec ouvrage répété")
print("=" * 80)
description1 = "Paiement au volume Anjahambe 03/2025 9200; Anjahambe 04/2025 246500; Anjahambe 05/2025 251400; Anjahambe"
print(f"\nDescription: {description1}")
result1 = extraire_ouvrage_et_mois_paiement_volume(description1)
print(f"\nRésultat (type: {type(result1).__name__}):")
if isinstance(result1, list):
    print(f"Nombre de paiements détectés: {len(result1)}")
    for i, item in enumerate(result1, 1):
        print(f"\nPaiement {i}:")
        print(f"  - Ouvrage: {item.get('ouvrage_nom')}")
        print(f"  - Mois: {item.get('mois')}")
        print(f"  - Année: {item.get('annee')}")
        print(f"  - Date: {item.get('date_str')}")
        print(f"  - Montant: {item.get('montant')}")
else:
    print(f"Résultat: {result1}")

# Test 2: Format avec ouvrage hérité
print("\n" + "=" * 80)
print("TEST 2: Format avec ouvrage hérité")
print("=" * 80)
description2 = "Paiement au volume Anjahambe 12/2025 41400; 01/2025 24200; 02/2025 21900; 03/2025 58700; 04/2025 30100; 05/2025 29000; 06/2025 93400; 07/2025 79800; 08/2025 156100; 09/2025 95800; 10/2025 237000"
print(f"\nDescription: {description2}")
result2 = extraire_ouvrage_et_mois_paiement_volume(description2)
print(f"\nRésultat (type: {type(result2).__name__}):")
if isinstance(result2, list):
    print(f"Nombre de paiements détectés: {len(result2)}")
    for i, item in enumerate(result2, 1):
        print(f"\nPaiement {i}:")
        print(f"  - Ouvrage: {item.get('ouvrage_nom')}")
        print(f"  - Mois: {item.get('mois')}")
        print(f"  - Année: {item.get('annee')}")
        print(f"  - Date: {item.get('date_str')}")
        print(f"  - Montant: {item.get('montant')}")
else:
    print(f"Résultat: {result2}")

# Test 3: Format simple (ancien comportement)
print("\n" + "=" * 80)
print("TEST 3: Format simple (vérifier rétrocompatibilité)")
print("=" * 80)
description3 = "Paiement au volume Ankorabe 01/12/2025"
print(f"\nDescription: {description3}")
result3 = extraire_ouvrage_et_mois_paiement_volume(description3)
print(f"\nRésultat (type: {type(result3).__name__}):")
print(f"  - Ouvrage: {result3.get('ouvrage_nom')}")
print(f"  - Mois: {result3.get('mois')}")
print(f"  - Année: {result3.get('annee')}")
print(f"  - Date: {result3.get('date_str')}")

print("\n" + "=" * 80)
print("Tests terminés!")
print("=" * 80)
