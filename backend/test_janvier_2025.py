import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import BaseDiameX
from apps.billing.models import Releve
from datetime import datetime

print("=== TEST JANVIER 2025 ===\n")

# 1. Vérifier transactions DiameX janvier 2025
print("1. Transactions DiameX compte 707401 - Janvier 2025:")
diamex_jan = BaseDiameX.objects.filter(
    compte_code='707401',
    date_rec__year=2025,
    date_rec__month=1
)
print(f"   Nombre: {diamex_jan.count()}")

if diamex_jan.count() > 0:
    print("\n   Premières entrées:")
    for e in diamex_jan[:3]:
        print(f"   - Date: {e.date_rec}")
        print(f"     Montant IN: {e.montant_in}")
        print(f"     Description: {e.description[:80] if e.description else 'N/A'}")
        print(f"     Prog: {e.prog}")
        print(f"     Scan: {e.scan or 'Vide'}")
        print()

# 2. Vérifier relevés de DÉCEMBRE 2024 (car janvier 2025 = décembre 2024 + 1 mois)
print("\n2. Relevés avec montant - Décembre 2024:")
releves_dec = Releve.objects.filter(
    montant__isnull=False,
    montant__gt=0,
    datereleve__year=2024,
    datereleve__month=12
)
print(f"   Nombre: {releves_dec.count()}")

if releves_dec.count() > 0:
    print("\n   Premiers relevés:")
    for r in releves_dec[:3]:
        ouvrage_nom = r.point_eau.ouvrage.nom if r.point_eau and r.point_eau.ouvrage else "N/A"
        print(f"   - Date relevé: {r.datereleve}")
        print(f"     Ouvrage: {ouvrage_nom}")
        print(f"     Montant: {r.montant}")
        print()

# 3. Vérifier aussi les années disponibles dans DiameX 707401
print("\n3. Années disponibles dans DiameX 707401:")
annees = BaseDiameX.objects.filter(compte_code='707401').values_list('date_rec__year', flat=True).distinct().order_by('date_rec__year')
print(f"   Années: {list(annees)}")

# 4. Vérifier les mois de 2025 disponibles
print("\n4. Mois de 2025 disponibles dans DiameX 707401:")
mois_2025 = BaseDiameX.objects.filter(
    compte_code='707401',
    date_rec__year=2025
).values_list('date_rec__month', flat=True).distinct().order_by('date_rec__month')
print(f"   Mois: {list(mois_2025)}")
