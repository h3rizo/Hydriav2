import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.billing.models import Releve
from django.db.models import Q

print("=== TEST FILTRE COUPÉ ===\n")

# 1. Compter tous les relevés avec montant pour décembre 2024
print("1. Relevés AVANT le filtre 'coupé' (décembre 2024):")
releves_avant = Releve.objects.filter(
    montant__isnull=False,
    montant__gt=0,
    point_eau__ouvrage__isnull=False,
    datereleve__year=2024,
    datereleve__month=12
)
print(f"   Nombre total: {releves_avant.count()}")

# 2. Compter les relevés avec "coupé" dans la remarque
print("\n2. Relevés avec 'coupé' dans la remarque:")
releves_coupe = releves_avant.filter(remarque__icontains='coupé')
print(f"   Nombre: {releves_coupe.count()}")

if releves_coupe.count() > 0:
    print("\n   Exemples:")
    for r in releves_coupe[:5]:
        print(f"   - IDXLS: {r.point_eau.idxls if r.point_eau else 'N/A'}")
        print(f"     Remarque: {r.remarque[:100] if r.remarque else 'Vide'}")
        print(f"     Montant: {r.montant}")
        print()

# 3. Compter les relevés APRÈS exclusion de "coupé"
print("3. Relevés APRÈS le filtre 'coupé' (décembre 2024):")
releves_apres = releves_avant.exclude(remarque__icontains='coupé')
print(f"   Nombre: {releves_apres.count()}")

# 4. Différence
diff = releves_avant.count() - releves_apres.count()
print(f"\n4. Nombre de relevés exclus: {diff}")

# 5. Vérifier également pour janvier 2025 et plus
print("\n5. Relevés pour 2025 (AVANT exclusion):")
releves_2025_avant = Releve.objects.filter(
    montant__isnull=False,
    montant__gt=0,
    point_eau__ouvrage__isnull=False,
    datereleve__year__gte=2025
)
print(f"   Nombre total: {releves_2025_avant.count()}")

releves_2025_coupe = releves_2025_avant.filter(remarque__icontains='coupé')
print(f"   Avec 'coupé': {releves_2025_coupe.count()}")

releves_2025_apres = releves_2025_avant.exclude(remarque__icontains='coupé')
print(f"   Après exclusion: {releves_2025_apres.count()}")

# 6. Test du filtre complet (comme dans views.py)
print("\n6. Test du filtre complet (décembre 2024 + 2025+):")
releves_complet = Releve.objects.filter(
    montant__isnull=False,
    montant__gt=0,
    point_eau__ouvrage__isnull=False
).filter(
    Q(datereleve__year__gte=2025) |
    Q(datereleve__year=2024, datereleve__month=12)
).exclude(
    remarque__icontains='coupé'
)
print(f"   Nombre total: {releves_complet.count()}")
print(f"   (Devrait être: {releves_apres.count()} + {releves_2025_apres.count()} = {releves_apres.count() + releves_2025_apres.count()})")
