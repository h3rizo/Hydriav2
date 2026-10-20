#!/usr/bin/env python
"""
Script pour tester l'API suivi_conges et identifier l'erreur NoneType
"""
import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import Employe
from apps.employees.views import api_employes
from django.test import RequestFactory
from django.contrib.auth.models import User
import traceback

print("[LOG] Début du test API employes...")

# Créer une fausse requête avec per_page=1000
factory = RequestFactory()
user = User.objects.first()

# Test 1: Sans pagination
print("\n[TEST 1] Appel /api/employes/ (sans pagination)")
try:
    request = factory.get('/api/employes/')
    request.user = user
    response = api_employes(request)
    print(f"  [OK] Status: {response.status_code}")
    if response.status_code != 200:
        print(f"  [ERROR] Response: {response.content}")
except Exception as e:
    print(f"  [ERROR] {type(e).__name__}: {e}")
    traceback.print_exc()

# Test 2: Avec per_page=1000
print("\n[TEST 2] Appel /api/employes/?per_page=1000")
try:
    request = factory.get('/api/employes/?per_page=1000')
    request.user = user
    response = api_employes(request)
    print(f"  [OK] Status: {response.status_code}")

    # Parser la réponse JSON
    import json
    data = json.loads(response.content)
    print(f"  [INFO] Nombre d'employés retournés: {len(data.get('employes', []))}")

    # Vérifier chaque employé
    for idx, emp in enumerate(data.get('employes', [])):
        if emp.get('id') is None:
            print(f"  [WARNING] Employé #{idx} a id=None: {emp}")
        if not emp.get('nom') and not emp.get('prenom') and not emp.get('surnom'):
            print(f"  [WARNING] Employé #{idx} sans nom: {emp}")

except Exception as e:
    print(f"  [ERROR] {type(e).__name__}: {e}")
    traceback.print_exc()

# Test 3: Vérifier directement dans la BDD
print("\n[TEST 3] Vérification BDD - employés avec anomalies")
try:
    # Employés sans nom ET sans prénom ET sans surnom
    employes_sans_nom = Employe.objects.filter(
        nom__isnull=True,
        prenom__isnull=True,
        surnom__isnull=True
    )
    print(f"  [INFO] Employés sans aucun nom: {employes_sans_nom.count()}")

    # Employés avec ID None (normalement impossible)
    employes_all = Employe.objects.all()
    for emp in employes_all:
        if emp.id is None:
            print(f"  [WARNING] Employé avec ID None trouvé: {emp}")

except Exception as e:
    print(f"  [ERROR] {type(e).__name__}: {e}")
    traceback.print_exc()

print("\n[LOG] Fin des tests")
