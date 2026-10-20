#!/usr/bin/env python
"""
Script pour recalculer toutes les grilles de salaire existantes.
Utilisé après l'ajout du champ mutuelle_sante.
"""

import os
import sys
import django

# Configuration Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import GrilleSalaire

def recalculer_toutes_les_grilles():
    """
    Recalcule tous les champs dérivés de toutes les grilles de salaire.
    """
    grilles = GrilleSalaire.objects.all()
    total = grilles.count()

    print(f"[RECALCUL] {total} grilles de salaire a recalculer...")

    success_count = 0
    error_count = 0

    for i, grille in enumerate(grilles, 1):
        try:
            # Recalculer tous les champs
            grille.calculer_tous_les_champs()
            grille.save()

            success_count += 1

            # Afficher la progression tous les 50 enregistrements
            if i % 50 == 0:
                print(f"  Progression: {i}/{total} ({i*100//total}%)")

        except Exception as e:
            error_count += 1
            print(f"  [ERREUR] Grille {grille.id}: {str(e)}")

    print(f"\n[TERMINE] Recalcul termine:")
    print(f"  - Succes: {success_count}")
    print(f"  - Erreurs: {error_count}")

    # Vérifier que mutuelle_sante n'est plus à 0
    grilles_avec_mutuelle = GrilleSalaire.objects.filter(mutuelle_sante__gt=0).count()
    grilles_sans_mutuelle = GrilleSalaire.objects.filter(mutuelle_sante=0).count()

    print(f"\n[STATS] Mutuelle sante:")
    print(f"  - Avec mutuelle > 0: {grilles_avec_mutuelle}")
    print(f"  - Sans mutuelle (= 0): {grilles_sans_mutuelle}")

if __name__ == '__main__':
    recalculer_toutes_les_grilles()
