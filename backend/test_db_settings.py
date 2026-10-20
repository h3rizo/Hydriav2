"""
Test pour vérifier les paramètres de connexion à la base de données
"""
import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from django.db import connection, transaction
from django.conf import settings

print("=" * 60)
print("VÉRIFICATION DES PARAMÈTRES DE BASE DE DONNÉES")
print("=" * 60)

# Afficher les paramètres de la base de données
print(f"\n[DATABASE] Config:")
print(f"  - ENGINE: {settings.DATABASES['default']['ENGINE']}")
print(f"  - NAME: {settings.DATABASES['default']['NAME']}")
print(f"  - AUTOCOMMIT: {connection.get_autocommit()}")
print(f"  - IN_ATOMIC_BLOCK: {connection.in_atomic_block}")

# Test simple d'insertion et vérification
from apps.accounting.models import BaseDiameX
from apps.employees.models import Employe

print(f"\n[BEFORE] BaseDiameX count: {BaseDiameX.objects.count()}")

try:
    print("\n[TEST] Test avec transaction.atomic()...")
    with transaction.atomic():
        employe = Employe.objects.filter(surnom='HERIZO').first()
        print(f"  - Employé: {employe}")

        entry = BaseDiameX.objects.create(
            fichier_source='TEST_DB_SETTINGS',
            id_access=88888,
            description='Test DB Settings',
            montant_in=9999.0,
            montant_out=0.0,
            compte_code='TEST',
            prog='TDB',
            imported_by=employe
        )
        print(f"  - Entry créée avec ID: {entry.id}")

        # Vérifier DANS le bloc transaction
        count_in_transaction = BaseDiameX.objects.filter(id_access=88888).count()
        print(f"  - Count DANS transaction: {count_in_transaction}")

    # Vérifier APRÈS le bloc transaction
    print("\n[AFTER] Vérification APRÈS transaction.atomic():")
    count_after_transaction = BaseDiameX.objects.filter(id_access=88888).count()
    print(f"  - Count APRÈS transaction: {count_after_transaction}")

    if count_after_transaction > 0:
        print("  - ✅ SUCCESS: Data persiste après transaction!")

        # Nettoyer
        BaseDiameX.objects.filter(id_access=88888).delete()
        print(f"  - Entry supprimée")
    else:
        print("  - ❌ ERREUR: Data ne persiste PAS après transaction!")

except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print(f"\n[FINAL] BaseDiameX count: {BaseDiameX.objects.count()}")
print("\n" + "=" * 60)