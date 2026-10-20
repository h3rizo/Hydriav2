#!/usr/bin/env python
"""
Script pour corriger les valeurs de type_contrat dans la table contrats.
Les valeurs sont actuellement stockées avec le label (ex: "Temps plein")
au lieu de la clé (ex: "temps_plein").

Usage:
    python scripts/fix_type_contrat_values.py
"""

import os
import sys
import django

# Configuration Django si le script est exécuté directement
if __name__ == '__main__':
    # Ajouter le répertoire parent au path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Configuration Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
    django.setup()

from apps.employees.models import Contrat

def fix_type_contrat_values():
    """
    Corrige les valeurs de type_contrat pour utiliser les clés au lieu des labels.
    """
    print("=" * 80)
    print("CORRECTION DES VALEURS TYPE_CONTRAT")
    print("=" * 80)
    print()

    # Mapping des anciennes valeurs vers les nouvelles
    mapping = {
        'Temps plein': 'temps_plein',
        'Temps partiel': 'temps_partiel',
        'Journalier': 'journalier',
    }

    total_corriges = 0

    for old_value, new_value in mapping.items():
        contrats = Contrat.objects.filter(type_contrat=old_value)
        count = contrats.count()

        if count > 0:
            print(f"[INFO] Correction '{old_value}' -> '{new_value}' : {count} contrat(s)")
            contrats.update(type_contrat=new_value)
            total_corriges += count

    print()
    print("=" * 80)
    print("RESULTAT DE LA CORRECTION")
    print("=" * 80)
    print(f"[OK] Total de contrats corriges : {total_corriges}")
    print()

    if total_corriges > 0:
        print("[SUCCESS] Correction terminee avec succes !")

        # Vérification
        print()
        print("Verification:")
        for key, label in Contrat.TYPE_CHOICES:
            count = Contrat.objects.filter(type_contrat=key).count()
            if count > 0:
                print(f"  - '{key}' : {count} contrat(s)")
    else:
        print("[INFO] Aucune correction necessaire.")

if __name__ == '__main__':
    fix_type_contrat_values()
