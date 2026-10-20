#!/usr/bin/env python
"""
Script pour migrer les valeurs de salaire_brut_base depuis les grilles vers les contrats.
Pour chaque contrat ayant salaire_brut_base = 0 ou NULL, on récupère la première valeur
depuis une grille de salaire liée (la plus ancienne).

Usage:
    python manage.py shell < scripts/migrate_salaire_brut_base.py

    OU

    python scripts/migrate_salaire_brut_base.py
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

from apps.employees.models import Contrat, GrilleSalaire
from decimal import Decimal

def migrate_salaire_brut_base():
    """
    Migre les valeurs de salaire_brut_base depuis les grilles vers les contrats.
    """
    print("=" * 80)
    print("MIGRATION DES SALAIRES BRUT DE BASE")
    print("=" * 80)
    print()

    # Récupérer tous les contrats avec salaire_brut_base = 0 ou NULL
    contrats_a_migrer = Contrat.objects.filter(
        salaire_brut_base__isnull=True
    ) | Contrat.objects.filter(
        salaire_brut_base=0
    )

    total_contrats = contrats_a_migrer.count()
    print(f"[INFO] Nombre de contrats a traiter : {total_contrats}")
    print()

    if total_contrats == 0:
        print("[OK] Aucun contrat a migrer. Tous les contrats ont deja un salaire brut de base defini.")
        return

    contrats_migres = 0
    contrats_sans_grille = 0
    contrats_avec_grille_vide = 0

    for contrat in contrats_a_migrer:
        # Récupérer la première grille de salaire (la plus ancienne)
        grille = GrilleSalaire.objects.filter(
            contrat=contrat
        ).order_by('date_salaire').first()

        if not grille:
            print(f"[WARN] Contrat {contrat.employe.nom_complet} ({contrat.debut_contrat}) : Aucune grille trouvee")
            contrats_sans_grille += 1
            continue

        if not grille.salaire_brut_base or grille.salaire_brut_base == 0:
            print(f"[WARN] Contrat {contrat.employe.nom_complet} ({contrat.debut_contrat}) : Grille sans salaire brut")
            contrats_avec_grille_vide += 1
            continue

        # Mettre à jour le contrat
        contrat.salaire_brut_base = grille.salaire_brut_base
        contrat.save()

        print(f"[OK] Contrat {contrat.employe.nom_complet} ({contrat.debut_contrat}) : {grille.salaire_brut_base:,.2f} Ar")
        contrats_migres += 1

    print()
    print("=" * 80)
    print("RESULTAT DE LA MIGRATION")
    print("=" * 80)
    print(f"[OK]   Contrats migres avec succes : {contrats_migres}")
    print(f"[WARN] Contrats sans grille        : {contrats_sans_grille}")
    print(f"[WARN] Contrats avec grille vide   : {contrats_avec_grille_vide}")
    print(f"[INFO] Total traite                : {total_contrats}")
    print()

    if contrats_migres > 0:
        print("[SUCCESS] Migration terminee avec succes !")
    else:
        print("[WARN] Aucune migration effectuee.")

if __name__ == '__main__':
    migrate_salaire_brut_base()
