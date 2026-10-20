import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import EmployeBaseDiameX
from apps.accounting.models import BaseDiameX

print("=== TEST EMPLOYE BASE DIAMEX ===\n")

# 1. Lister tous les EmployeBaseDiameX
print("1. Tous les EmployeBaseDiameX:")
employes = EmployeBaseDiameX.objects.all()
print(f"   Nombre total: {employes.count()}")

if employes.count() > 0:
    print("\n   Liste:")
    for emp in employes:
        print(f"   - ID: {emp.id}")
        print(f"     Employé: {emp.employe.nom if emp.employe else 'N/A'} {emp.employe.prenom if emp.employe else ''}")
        print(f"     Base DiameX: {emp.base_diamex}")
        print(f"     Chemin base: {emp.chemin_base_diamex or 'Vide'}")
        print()

# 2. Chercher les valeurs de 'prog' dans BaseDiameX pour janvier 2025
print("\n2. Valeurs uniques de 'prog' dans BaseDiameX (janvier 2025, compte 707401):")
progs = BaseDiameX.objects.filter(
    compte_code='707401',
    date_rec__year=2025,
    date_rec__month=1
).values_list('prog', flat=True).distinct()

print(f"   Nombre de prog uniques: {len(list(progs))}")
for prog in progs:
    print(f"   - {prog}")
    # Vérifier si un EmployeBaseDiameX existe pour ce prog
    emp = EmployeBaseDiameX.objects.filter(base_diamex=prog).first()
    if emp:
        print(f"     ✓ Trouvé dans EmployeBaseDiameX (chemin: {emp.chemin_base_diamex or 'Vide'})")
    else:
        print(f"     ✗ NON TROUVÉ dans EmployeBaseDiameX")
