import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import BaseDiameX
from apps.employees.models import EmployeBaseDiameX

print("=== TEST PARTIAL MATCH ===\n")

# Tester la logique de recherche partielle
prog = "EHA-Soakoja-Tana"
print(f"1. Prog value: {prog}")

prog_parts = prog.split('-')
print(f"   Parts: {prog_parts}")

if len(prog_parts) >= 2:
    search_term = prog_parts[-1].strip()
    print(f"   Search term: {search_term}")

    # Chercher avec __icontains
    employes = EmployeBaseDiameX.objects.filter(
        base_diamex__icontains=search_term
    )
    print(f"   Found {employes.count()} match(es)")

    if employes.count() > 0:
        for emp in employes:
            print(f"\n   Match:")
            print(f"   - base_diamex: {emp.base_diamex}")
            print(f"   - chemin_base: {emp.chemin_base_diamex or 'VIDE'}")

# Tester avec toutes les valeurs de prog
print("\n\n2. Test avec toutes les valeurs de prog:")
progs = BaseDiameX.objects.filter(
    compte_code='707401',
    date_rec__year=2025,
    date_rec__month=1
).values_list('prog', flat=True).distinct()

for p in progs:
    if p:
        parts = p.split('-')
        if len(parts) >= 2:
            term = parts[-1].strip()
            matches = EmployeBaseDiameX.objects.filter(base_diamex__icontains=term).count()
            print(f"   {p} -> search='{term}' -> {matches} match(es)")
