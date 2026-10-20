#!/usr/bin/env python
"""
Script de test pour vérifier le filtrage timezone dans le PDF
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

import pytz
from django.utils import timezone as dj_timezone
from apps.planning.models import Planning
from apps.employees.models import Employe

# Timezone Madagascar
tz_madagascar = pytz.timezone('Indian/Antananarivo')

# Choisir un employé (premier trouvé)
employe = Employe.objects.first()
if not employe:
    print("Aucun employé trouvé dans la base")
    exit(1)

print(f"Employé: {employe.surnom or employe.prenom} {employe.nom}")
print(f"ID: {employe.id}")

# Test pour septembre 2025
year = 2025
month = 9

print(f"\n=== Test pour {month}/{year} ===\n")

# Méthode 1 : Filtre SQL (MAUVAIS)
print("1. FILTRE SQL (ANCIEN - MAUVAIS)")
plannings_sql = Planning.objects.filter(
    employe_id=employe.id,
    estvalide=True,
    date__year=year,
    date__month=month
).order_by('date')[:5]  # Limiter à 5 pour tester

print(f"   Nombre trouvé: {plannings_sql.count()}")
for p in plannings_sql:
    print(f"   - {p.date} (UTC)")

# Méthode 2 : Filtre Python (BON)
print("\n2. FILTRE PYTHON (NOUVEAU - BON)")
all_plannings = Planning.objects.filter(
    employe_id=employe.id,
    estvalide=True
).order_by('date')

plannings_python = []
for planning in all_plannings:
    if planning.date:
        # Convertir en timezone Madagascar
        date_aware = planning.date if planning.date.tzinfo else dj_timezone.make_aware(planning.date)
        date_madagascar = date_aware.astimezone(tz_madagascar)
        date_obj = date_madagascar.date()

        # Filtrer par année et mois
        if date_obj.year == year and date_obj.month == month:
            plannings_python.append((planning, date_madagascar))
            if len(plannings_python) >= 5:  # Limiter à 5
                break

print(f"   Nombre trouvé: {len(plannings_python)}")
for p, date_mg in plannings_python:
    print(f"   - {date_mg} (Madagascar) = {p.date} (UTC)")

# Comparer
print("\n=== COMPARAISON ===")
print(f"SQL: {plannings_sql.count()} plannings")
print(f"Python: {len(plannings_python)} plannings")

if plannings_sql.count() != len(plannings_python):
    print("\n⚠️ DIFFÉRENCE DÉTECTÉE !")
    print("Le filtre SQL donne des résultats incorrects.")
else:
    print("\n✓ Même nombre de résultats")

print("\n=== PREMIÈRE DATE DE CHAQUE MÉTHODE ===")
if plannings_sql.exists():
    first_sql = plannings_sql.first()
    print(f"SQL: {first_sql.date} (UTC)")
    date_aware = first_sql.date if first_sql.date.tzinfo else dj_timezone.make_aware(first_sql.date)
    date_mg = date_aware.astimezone(tz_madagascar)
    print(f"     Converti en Madagascar: {date_mg.strftime('%d/%m/%Y %H:%M:%S')}")

if plannings_python:
    first_python, first_date_mg = plannings_python[0]
    print(f"\nPython: {first_python.date} (UTC)")
    print(f"        Converti en Madagascar: {first_date_mg.strftime('%d/%m/%Y %H:%M:%S')}")
