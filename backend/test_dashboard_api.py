#!/usr/bin/env python
"""
Test des APIs dashboard
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
                print(f"First item: {data['table_data'][0] if data['table_data'] else 'Empty'}")
        else:
            print(f"Error: {response.content[:200]}")

    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Tester plusieurs types
    types_to_test = [
        'villages-desservis',
        'communes',
        'ouvrages',
        'points-eau'
    ]

    for detail_type in types_to_test:
        test_api(detail_type)
