"""
Test de l'API d'import avec des données minimales
"""
import requests
import json

# Données test minimales (1 seule ligne)
test_data = {
    'data_rows': json.dumps([{
        'ID': 1,
        'Prog': 'TEST',
        'Journal': 'BQ',
        'DateM': '2025-01-01',
        'Description': 'Test API',
        'In': 1000.0,
        'Out': 0.0,
        'Cat': '512',
        'Rec': '001',
        'DateRec': None,
        'PERS': None,
        'Detail': None,
        'Info': None,
        'Fin': None,
        'Activ': 'TEST',
        'Scan': None,
        'Fournisseur': None,
        'DateInput': None,
        'Check': False,
        'Match': None,
        'BankRec': None
    }]),
    'soldes_rows': json.dumps([]),
    'fichier_nom': 'TEST_API.accde',
    'employe_surnom': 'HERIZO'
}

print("[TEST] Envoi requête à https://www.hydria.mg/comptabilite/api/import-from-access/")
print(f"[DATA] {len(test_data['data_rows'])} caractères de JSON")

try:
    response = requests.post(
        'https://www.hydria.mg/comptabilite/api/import-from-access/',
        data=test_data,
        timeout=30
    )

    print(f"[RESPONSE] Status: {response.status_code}")
    print(f"[RESPONSE] Headers: {dict(response.headers)}")

    if response.status_code == 200:
        result = response.json()
        print(f"[SUCCESS] {result.get('success')}")
        print(f"[MESSAGE] {result.get('message')}")
        print(f"[STATS] {result.get('stats')}")
    else:
        print(f"[ERROR] {response.text[:500]}")

except Exception as e:
    print(f"[EXCEPTION] {type(e).__name__}: {e}")