#!/usr/bin/env python
"""Script pour mettre à jour le champ concerne_livraison des désignations"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.planning.models import Designation

print("Mise à jour du champ 'concerne_livraison'")
print("=" * 70)

# Étape 1: Marquer TOUS les "Bon de livraison" comme concerne_livraison=True
bon_livraison = Designation.objects.filter(type_avance_caissiere='Bon de livraison')
count_bl = bon_livraison.update(concerne_livraison=True)
print(f"\nÉtape 1: {count_bl} désignations 'Bon de livraison' marquées comme concerne_livraison=True")

# Étape 2: Exclure les services/frais qui ne sont PAS des articles physiques
non_livraison_keywords = [
    'Coupure d\'eau',
    'Carnet facture coupure',
    'Indemnité',
    'Frais de déplacement',
    'Carnet de reçu',
    'Carnet facture contrat',
]

total_excluded = 0
print("\nÉtape 2: Exclusion des services (concerne_livraison=False):")

for keyword in non_livraison_keywords:
    designations = Designation.objects.filter(
        nom__icontains=keyword,
        type_avance_caissiere='Bon de livraison'
    )

    if designations.exists():
        count = designations.update(concerne_livraison=False)
        print(f"  - '{keyword}': {count} désignation(s) exclue(s)")
        total_excluded += count

print("\n" + "=" * 70)
print(f"\nRésumé:")
print(f"  - Total 'Bon de livraison': {count_bl}")
print(f"  - Services exclus: {total_excluded}")
print(f"  - Articles physiques: {count_bl - total_excluded}")
