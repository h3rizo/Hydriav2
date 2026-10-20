#!/usr/bin/env python
"""
Script de test pour l'API de calcul de grille de salaire
"""
import os
import sys
import django

# Configuration Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import Contrat
import json
from decimal import Decimal

def test_api_calcul():
    """Test de la logique de calcul"""

    # Prendre le premier contrat
    contrat = Contrat.objects.select_related('employe__poste').first()

    if not contrat:
        print("❌ Aucun contrat trouvé")
        return

    print(f"\n=== TEST API CALCUL GRILLE ===")
    print(f"Contrat ID: {contrat.id}")
    print(f"Employé: {contrat.employe.nom_employe}")
    print(f"Type contrat: {contrat.type_contrat}")
    print(f"Poste: {contrat.employe.poste.nom_poste if contrat.employe.poste else 'None'}")

    # Simuler le calcul comme dans l'API
    type_contrat = contrat.type_contrat
    poste_nom = contrat.employe.poste.nom_poste if contrat.employe.poste else ""
    est_gardien = "gardien" in poste_nom.lower()
    est_journalier = type_contrat.lower() == 'journalier'

    print(f"\n=== RÉSULTATS ===")
    print(f"Est gardien: {est_gardien}")
    print(f"Est journalier: {est_journalier}")

    # Simuler les données envoyées par le frontend
    salaire_brut_base = Decimal('100000')
    personnes_charge = 2
    nb_jours_presence = 22
    nb_jours_feries_gardien = 2
    nb_heures_remplacement_gardien = Decimal('10')

    print(f"\n=== PARAMÈTRES TEST ===")
    print(f"Salaire brut base: {salaire_brut_base} Ar")
    print(f"Personnes à charge: {personnes_charge}")
    print(f"Nb jours presence: {nb_jours_presence}")
    print(f"Nb jours fériés gardien: {nb_jours_feries_gardien}")
    print(f"Nb heures remplacement: {nb_heures_remplacement_gardien}")

    # Calcul majorations gardien
    if est_gardien:
        majoration_nuit = salaire_brut_base * Decimal('0.30') * Decimal('208') * Decimal('7') / Decimal('24') / Decimal('243')
        majoration_dimanche = salaire_brut_base * Decimal('0.40') * Decimal('52') / Decimal('12') / Decimal('3') * Decimal('24') / Decimal('243')
        montant_jours_feries = salaire_brut_base * Decimal('0.50') * Decimal(str(nb_jours_feries_gardien)) * Decimal('10') / Decimal('243')
        montant_remplacement = salaire_brut_base * Decimal(str(nb_heures_remplacement_gardien)) / Decimal('243')

        print(f"\n=== MAJORATIONS GARDIEN ===")
        print(f"Majoration nuit: {majoration_nuit:,.2f} Ar")
        print(f"Majoration dimanche: {majoration_dimanche:,.2f} Ar")
        print(f"Montant jours fériés: {montant_jours_feries:,.2f} Ar")
        print(f"Montant remplacement: {montant_remplacement:,.2f} Ar")
    else:
        majoration_nuit = Decimal('0')
        majoration_dimanche = Decimal('0')
        montant_jours_feries = Decimal('0')
        montant_remplacement = Decimal('0')

    # Calcul salaire brut total
    if est_journalier:
        salaire_brut_total = salaire_brut_base * Decimal(str(nb_jours_presence))
        print(f"\n=== CALCUL JOURNALIER ===")
        print(f"Brut total: {salaire_brut_base} × {nb_jours_presence} = {salaire_brut_total:,.2f} Ar")
    elif est_gardien:
        salaire_brut_total = salaire_brut_base + majoration_nuit + majoration_dimanche + montant_jours_feries + montant_remplacement
        print(f"\n=== CALCUL GARDIEN ===")
        print(f"Brut total: {salaire_brut_base} + majorations = {salaire_brut_total:,.2f} Ar")
    else:
        salaire_brut_total = salaire_brut_base
        print(f"\n=== CALCUL STANDARD ===")
        print(f"Brut total: {salaire_brut_total:,.2f} Ar")

    print(f"\n✅ Test terminé")

if __name__ == '__main__':
    test_api_calcul()
