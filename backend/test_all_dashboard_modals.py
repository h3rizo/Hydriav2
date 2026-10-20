#!/usr/bin/env python
"""
Test complet de tous les modals du dashboard
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from hydria.views import dashboard_details_api
import json

User = get_user_model()

def test_api(detail_type):
    """Teste une API dashboard"""
    print(f"\n{'=' * 60}")
    print(f"TEST: {detail_type}")
    print('=' * 60)

    try:
        # Créer une requête simulée
        factory = RequestFactory()
        request = factory.get(f'/api/dashboard/details/{detail_type}/')
        request.user = User.objects.first()

        # Appeler l'API
        response = dashboard_details_api(request, detail_type)

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = json.loads(response.content)
            print(f"Keys: {list(data.keys())}")
            print(f"Total items: {data.get('total_items', 0)}")

            if data.get('table_data'):
                if data['table_data']:
                    print(f"First item: {data['table_data'][0]}")
                else:
                    print("Table data is empty")

            print("[OK] SUCCESS")
        else:
            print(f"[ERROR] Error response: {response.content[:300]}")

    except Exception as e:
        print(f"[EXCEPTION] Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Liste complète des types de modals du dashboard
    types_to_test = [
        # Géographie
        'communes',
        'villages',
        'villages-desservis',

        # Infrastructures
        'ouvrages',
        'equipements',
        'compteurs',
        'adresses',

        # Points d'eau
        'points-eau',
        'points-eau-prives',
        'points-eau-publics',
        'points-eau-coupes',

        # Habitants
        'habitants',
        'habitants-desservis',
        'habitants-prives',
        'habitants-publics',

        # Autres
        'cartes-sociales',
        'tarifs',
        'modalites',
        'fournisseurs'
    ]

    print("\n" + "=" * 60)
    print("TEST DE TOUS LES MODALS DU DASHBOARD")
    print("=" * 60)
    print(f"Total de {len(types_to_test)} types à tester")

    errors = []
    successes = []

    for detail_type in types_to_test:
        test_api(detail_type)

        # Faire un mini test pour capturer succès/erreurs
        try:
            factory = RequestFactory()
            request = factory.get(f'/api/dashboard/details/{detail_type}/')
            request.user = User.objects.first()
            response = dashboard_details_api(request, detail_type)

            if response.status_code == 200:
                successes.append(detail_type)
            else:
                errors.append(detail_type)
        except:
            errors.append(detail_type)

    # Résumé final
    print("\n" + "=" * 60)
    print("RÉSUMÉ FINAL")
    print("=" * 60)
    print(f"[OK] Succès: {len(successes)}/{len(types_to_test)}")
    print(f"[ERROR] Erreurs: {len(errors)}/{len(types_to_test)}")

    if errors:
        print(f"\n[ERROR] Types avec erreurs:")
        for err_type in errors:
            print(f"  - {err_type}")

    if successes:
        print(f"\n[OK] Types fonctionnels:")
        for succ_type in successes:
            print(f"  - {succ_type}")
