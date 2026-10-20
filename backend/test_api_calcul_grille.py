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

from apps.employees.models import Contrat, GrilleSalaire
import json

def test_api_calcul():
    """Test de l'API de calcul avec un contrat existant"""

    # Trouver un contrat avec une grille
    grille = GrilleSalaire.objects.select_related('contrat__employe__poste').first()

    if not grille:
        print("❌ Aucune grille de salaire trouvée dans la base")
        return

    contrat = grille.contrat
    employe = contrat.employe
    poste = employe.poste if employe else None

    print("[TEST] Test avec:")
    print(f"  - Employe: {employe}")
    print(f"  - Poste: {poste.nom_poste if poste else 'N/A'}")
    print(f"  - Contrat: {contrat.type_contrat}")
    print(f"  - Contrat ID: {contrat.id}")
    print()

    # Simuler les données envoyées par le frontend
    data = {
        'contrat_id': str(contrat.id),
        'salaire_brut_base': float(grille.salaire_brut_base),
        'personnes_charge': grille.personnes_charge,
        'nb_jours_presence': grille.nb_jours_presence,
        'nb_jours_feries_gardien': grille.nb_jours_feries_gardien,
        'nb_heures_remplacement_gardien': float(grille.nb_heures_remplacement_gardien)
    }

    print("[DATA] Donnees d'entree:")
    print(json.dumps(data, indent=2))
    print()

    # Simuler l'appel API
    from django.test import RequestFactory
    from apps.employees.views import api_calculer_grille_preview

    factory = RequestFactory()
    request = factory.post(
        '/api/calculer-grille-preview/',
        data=json.dumps(data),
        content_type='application/json'
    )

    response = api_calculer_grille_preview(request)

    print(f"[HTTP] Statut HTTP: {response.status_code}")

    if response.status_code == 200:
        result = json.loads(response.content)
        print("[OK] Reponse JSON:")
        print(json.dumps(result, indent=2))

        if result.get('success'):
            calculs = result['calculs']
            config = calculs['config']

            print()
            print("[RESULT] Resultats du calcul:")
            print(f"  - Type contrat: {config['type_contrat']}")
            print(f"  - Poste: {config['poste']}")
            print(f"  - Est gardien: {config['est_gardien']}")
            print(f"  - Est journalier: {config['est_journalier']}")
            print()
            print(f"  - Salaire brut total: {calculs['salaire_brut_total']:,.2f} Ar")
            print(f"  - CNaPS: {calculs['charge_cnaps_employe']:,.2f} Ar")
            print(f"  - Base imposable: {calculs['base_imposable']:,.2f} Ar")
            print(f"  - IRSA: {calculs['irsa']:,.2f} Ar")
            print(f"  - Mutuelle Sante: {calculs['mutuelle_sante']:,.2f} Ar")
            print(f"  - Salaire net: {calculs['salaire_net']:,.2f} Ar")

            if config['est_gardien']:
                print()
                print("  Majorations gardien:")
                print(f"    - Nuit: {calculs['majoration_nuit_gardien']:,.2f} Ar")
                print(f"    - Dimanche: {calculs['majoration_dimanche_gardien']:,.2f} Ar")
                print(f"    - Jours feries: {calculs['montant_jours_feries_gardien']:,.2f} Ar")
                print(f"    - Remplacement: {calculs['montant_remplacement_gardien']:,.2f} Ar")
        else:
            print(f"[ERROR] Erreur API: {result.get('error')}")
    else:
        print(f"[ERROR] Erreur HTTP {response.status_code}")
        print(response.content.decode('utf-8')[:500])

if __name__ == '__main__':
    test_api_calcul()
