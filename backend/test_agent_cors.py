"""
Script de test pour vérifier si l'agent local DiameX répond correctement aux requêtes CORS
"""
import requests

AGENT_URL = 'http://127.0.0.1:8765'
ORIGIN = 'https://www.hydria.mg'

print("=" * 60)
print("TEST AGENT LOCAL DIAMEX - CORS")
print("=" * 60)

# Test 1 : OPTIONS preflight
print("\n1. Test OPTIONS preflight (CORS)...")
try:
    response = requests.options(
        f'{AGENT_URL}/health',
        headers={
            'Origin': ORIGIN,
            'Access-Control-Request-Method': 'GET',
            'Access-Control-Request-Headers': 'content-type'
        },
        timeout=5
    )
    print(f"   Status: {response.status_code}")
    print(f"   Headers CORS:")
    for header in ['Access-Control-Allow-Origin', 'Access-Control-Allow-Methods',
                   'Access-Control-Allow-Headers', 'Access-Control-Allow-Private-Network']:
        value = response.headers.get(header, '(absent)')
        print(f"     {header}: {value}")

    if response.status_code == 204:
        print("   ✓ Preflight OK")
    else:
        print(f"   ✗ Preflight échoué (attendu 204, reçu {response.status_code})")

except Exception as e:
    print(f"   ✗ Exception: {e}")

# Test 2 : GET /health avec Origin
print("\n2. Test GET /health avec Origin...")
try:
    response = requests.get(
        f'{AGENT_URL}/health',
        headers={'Origin': ORIGIN},
        timeout=5
    )
    print(f"   Status: {response.status_code}")
    print(f"   Access-Control-Allow-Origin: {response.headers.get('Access-Control-Allow-Origin', '(absent)')}")

    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Agent répond : {data}")
    else:
        print(f"   ✗ Erreur HTTP {response.status_code}")

except Exception as e:
    print(f"   ✗ Exception: {e}")

# Test 3 : GET /health sans Origin (test basique)
print("\n3. Test GET /health sans Origin (basique)...")
try:
    response = requests.get(f'{AGENT_URL}/health', timeout=5)
    print(f"   Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Réponse : {data}")
    else:
        print(f"   ✗ Erreur HTTP {response.status_code}")

except Exception as e:
    print(f"   ✗ Exception: {e}")

print("\n" + "=" * 60)
print("RÉSUMÉ")
print("=" * 60)
print("""
Si tous les tests passent (✓), l'agent fonctionne correctement.

Si le problème persiste dans le navigateur :
1. Vérifier la console navigateur (F12) pour l'erreur exacte
2. Tester depuis http://localhost:8000 au lieu de https://www.hydria.mg
3. Le navigateur peut bloquer HTTPS → HTTP même avec CORS correct
""")