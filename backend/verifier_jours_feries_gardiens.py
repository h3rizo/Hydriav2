"""
Script pour vérifier et corriger les flags est_jour_ferie sur les rotations existantes
"""
import os
import django
import sys

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models_gardiens import RotationGardien
from datetime import date

def est_jour_ferie(date_obj):
    """
    Vérifie si une date est un jour férié
    """
    # Liste des jours fériés 2025
    jours_feries_2025 = [
        date(2025, 1, 1),   # Jour de l'an
        date(2025, 3, 29),  # Commémoration des martyrs
        date(2025, 3, 31),  # Lundi de Pâques
        date(2025, 5, 1),   # Fête du travail
        date(2025, 5, 8),   # Jeudi de l'Ascension
        date(2025, 5, 19),  # Lundi de Pentecôte
        date(2025, 6, 26),  # Fête de l'indépendance
        date(2025, 8, 15),  # Assomption
        date(2025, 11, 1),  # Toussaint
        date(2025, 12, 25), # Noël
    ]

    # Liste des jours fériés 2026
    jours_feries_2026 = [
        date(2026, 1, 1),   # Jour de l'an
        date(2026, 3, 29),  # Commémoration des martyrs
        date(2026, 4, 6),   # Lundi de Pâques
        date(2026, 5, 1),   # Fête du travail
        date(2026, 5, 14),  # Jeudi de l'Ascension
        date(2026, 5, 25),  # Lundi de Pentecôte
        date(2026, 6, 26),  # Fête de l'indépendance
        date(2026, 8, 15),  # Assomption
        date(2026, 11, 1),  # Toussaint
        date(2026, 12, 25), # Noël
    ]

    return date_obj in jours_feries_2025 or date_obj in jours_feries_2026

# Récupérer toutes les rotations de 2025 et 2026
rotations = RotationGardien.objects.filter(date__year__in=[2025, 2026]).order_by('date')

print(f"Total rotations 2025-2026: {rotations.count()}")

# Vérifier les rotations du 1er janvier 2025 spécifiquement
rotations_1er_janvier_2025 = RotationGardien.objects.filter(date=date(2025, 1, 1))
print(f"\nRotations du 1er janvier 2025: {rotations_1er_janvier_2025.count()}")
for rot in rotations_1er_janvier_2025:
    print(f"  - {rot.employe.surnom}: {rot.shift_type}, est_jour_ferie={rot.est_jour_ferie}")

# Vérifier les rotations du 1er janvier 2026 spécifiquement
rotations_1er_janvier_2026 = RotationGardien.objects.filter(date=date(2026, 1, 1))
print(f"\nRotations du 1er janvier 2026: {rotations_1er_janvier_2026.count()}")
for rot in rotations_1er_janvier_2026:
    print(f"  - {rot.employe.surnom}: {rot.shift_type}, est_jour_ferie={rot.est_jour_ferie}")

# Compter combien n'ont pas le flag correctement rempli
a_corriger = 0
for rot in rotations:
    devrait_etre_ferie = est_jour_ferie(rot.date)
    if rot.est_jour_ferie != devrait_etre_ferie:
        a_corriger += 1

print(f"\nRotations à corriger: {a_corriger}")

# Demander confirmation pour corriger
if a_corriger > 0:
    reponse = input("\nVoulez-vous corriger ces rotations? (o/n): ")
    if reponse.lower() == 'o':
        corriges = 0
        for rot in rotations:
            devrait_etre_ferie = est_jour_ferie(rot.date)
            if rot.est_jour_ferie != devrait_etre_ferie:
                rot.est_jour_ferie = devrait_etre_ferie
                rot.save()
                corriges += 1

        print(f"\n[OK] {corriges} rotations corrigées!")

        # Vérifier à nouveau le 1er janvier 2025
        print("\nRotations du 1er janvier 2025 après correction:")
        for rot in RotationGardien.objects.filter(date=date(2025, 1, 1)):
            print(f"  - {rot.employe.surnom}: {rot.shift_type}, est_jour_ferie={rot.est_jour_ferie}")

        # Vérifier à nouveau le 1er janvier 2026
        print("\nRotations du 1er janvier 2026 après correction:")
        for rot in RotationGardien.objects.filter(date=date(2026, 1, 1)):
            print(f"  - {rot.employe.surnom}: {rot.shift_type}, est_jour_ferie={rot.est_jour_ferie}")
    else:
        print("\nAnnulé.")
else:
    print("\n[OK] Toutes les rotations ont déjà les bons flags!")
