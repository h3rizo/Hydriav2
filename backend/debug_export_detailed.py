"""
Script de diagnostic détaillé pour comprendre pourquoi 0 transaction exportée
"""
import os
import django

os.chdir(r'c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import DiameXTemporaire

print("=" * 80)
print("DIAGNOSTIC EXPORT TRANSACTIONS")
print("=" * 80)

# 1. Compter TOUTES les transactions
total = DiameXTemporaire.objects.count()
print(f"\n1. Total transactions dans la base: {total}")

# 2. Par statut
print("\n2. Répartition par statut:")
for statut in ['en_attente', 'valide', 'exporte', 'erreur']:
    count = DiameXTemporaire.objects.filter(statut=statut).count()
    print(f"   - {statut}: {count}")

# 3. Transactions sans compte
sans_compte_null = DiameXTemporaire.objects.filter(compte_code__isnull=True).count()
sans_compte_vide = DiameXTemporaire.objects.filter(compte_code='').count()
print(f"\n3. Transactions sans compte:")
print(f"   - compte_code NULL: {sans_compte_null}")
print(f"   - compte_code vide (''): {sans_compte_vide}")

# 4. Transactions exportables (selon les filtres actuels)
exportables = DiameXTemporaire.objects.filter(
    statut__in=['en_attente', 'valide']
).exclude(
    statut='exporte'
).exclude(
    compte_code__isnull=True
).exclude(
    compte_code=''
)
print(f"\n4. Transactions EXPORTABLES (selon filtres): {exportables.count()}")

# 5. Détails des 5 premières exportables
if exportables.exists():
    print(f"\n5. Détails des premières transactions exportables:")
    for t in exportables[:5]:
        print(f"\n   Transaction ID: {t.id}")
        print(f"   - Description: {t.description}")
        print(f"   - Statut: {t.statut}")
        print(f"   - Compte: '{t.compte_code}'")
        print(f"   - Journal: '{t.journal_code}'")
        print(f"   - DateRec: {t.date_rec}")
        print(f"   - DateM: {t.date_m}")
        print(f"   - Montant IN: {t.montant_in}")
        print(f"   - Montant OUT: {t.montant_out}")
        print(f"   - Type: {t.type_transaction}")
        print(f"   - Prog: '{t.prog}'")
        print(f"   - ACTIV: '{t.activ}'")

# 6. Transactions en_attente détaillées
en_attente = DiameXTemporaire.objects.filter(statut='en_attente')
print(f"\n6. Transactions en_attente: {en_attente.count()}")
if en_attente.exists():
    for t in en_attente[:3]:
        print(f"\n   ID: {t.id}")
        print(f"   - Description: {t.description}")
        print(f"   - Compte code: '{t.compte_code}' (None={t.compte_code is None}, Vide={t.compte_code == ''})")
        print(f"   - Journal: '{t.journal_code}'")

# 7. Simuler l'export avec IDs spécifiques (comme le ferait le frontend)
print(f"\n7. Simulation export avec IDs (comme le frontend):")
if exportables.exists():
    test_ids = [str(t.id) for t in exportables[:2]]
    print(f"   - IDs testés: {test_ids}")

    test_query = DiameXTemporaire.objects.filter(
        id__in=test_ids,
        statut__in=['en_attente', 'valide']
    ).exclude(
        statut='exporte'
    ).exclude(
        compte_code__isnull=True
    ).exclude(
        compte_code=''
    )
    print(f"   - Résultat requête: {test_query.count()} transactions")

print("\n" + "=" * 80)
