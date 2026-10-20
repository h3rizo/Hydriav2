#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Script de test pour le module Non-Conformites"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.inspections.models import NonConformite

print("="*60)
print("TEST MODULE NON-CONFORMITES")
print("="*60)

# Test 1: Modele existe
print("\n[TEST 1] Modele NonConformite")
print("  - Table:", NonConformite._meta.db_table)
print("  - Nombre en base:", NonConformite.objects.count())

# Test 2: Choix disponibles
print("\n[TEST 2] Choix disponibles")
print("  - Priorites:", len(NonConformite.PRIORITE_CHOICES), "options")
print("  - Niveaux:", len(NonConformite.NIVEAU_SOLUTION_CHOICES), "options")
print("  - Echeances:", len(NonConformite.ECHEANCE_CHOICES), "options")

# Test 3: Methode generer_action_corrective
print("\n[TEST 3] Methode generer_action_corrective")
if hasattr(NonConformite, 'generer_action_corrective'):
    print("  - Methode existe: OUI")
else:
    print("  - Methode existe: NON")

# Test 4: Fichiers frontend
print("\n[TEST 4] Fichiers frontend")
fichiers = [
    'static/js/non_conformites.js',
    'templates/inspections/equipment_selection.html',
    'docs/NON_CONFORMITES_WORKFLOW.md'
]
for f in fichiers:
    chemin = os.path.join(os.path.dirname(__file__), f)
    existe = "OUI" if os.path.exists(chemin) else "NON"
    print(f"  - {f}: {existe}")

print("\n" + "="*60)
print("TOUS LES TESTS SONT TERMINES")
print("="*60)

print("\nProchaines etapes:")
print("  1. python manage.py runserver")
print("  2. Acceder a /inspections/equipment-selection/?planning_id=...")
print("  3. Marquer un point comme 'Non conforme'")
print("  4. Cliquer sur 'Detailler la non-conformite'")
