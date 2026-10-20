"""
Script de vérification : PlanningDetail mis à jour après export DiameX
"""
import os
import django

os.chdir(r'c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import DiameXTemporaire
from apps.planning.models import PlanningDetail

print("=" * 80)
print("VÉRIFICATION MISE À JOUR PLANNINGDETAIL APRÈS EXPORT")
print("=" * 80)

# 1. Récupérer les transactions exportées
transactions_exportees = DiameXTemporaire.objects.filter(
    statut='exporte'
).select_related('planning_detail')

print(f"\n1. Transactions exportées: {transactions_exportees.count()}")

if not transactions_exportees.exists():
    print("   Aucune transaction exportée trouvée.")
    print("\n" + "=" * 80)
    exit(0)

# 2. Vérifier chaque transaction
print(f"\n2. Vérification détaillée:")

for transaction in transactions_exportees:
    print(f"\n{'-' * 80}")
    print(f"Transaction ID: {transaction.id}")
    print(f"  Type: {transaction.type_transaction}")
    print(f"  Description: {transaction.description}")
    print(f"  Statut: {transaction.statut}")
    print(f"  Export batch: {transaction.export_batch}")

    if transaction.planning_detail:
        pd = transaction.planning_detail
        print(f"\n  PlanningDetail ID: {pd.id}")

        if transaction.type_transaction == 'avance':
            print(f"    numeroDiameXAvance: {pd.numeroDiameXAvance}")
            print(f"    BaseDiameXAvance: {pd.BaseDiameXAvance}")

            if pd.numeroDiameXAvance and pd.BaseDiameXAvance:
                print(f"    OK Avance mise a jour correctement")
            else:
                print(f"    ERREUR Avance NON mise a jour")
        else:
            print(f"    numeroDiameX: {pd.numeroDiameX}")
            print(f"    BaseDiameX: {pd.BaseDiameX}")

            if pd.numeroDiameX and pd.BaseDiameX:
                print(f"    OK Recette/Depense mise a jour correctement")
            else:
                print(f"    ERREUR Recette/Depense NON mise a jour")
    else:
        print(f"\n  ATTENTION Pas de PlanningDetail lie a cette transaction")

# 3. Statistiques globales
print(f"\n{'=' * 80}")
print("3. STATISTIQUES GLOBALES:")

total_exportes = transactions_exportees.count()
avec_planning_detail = transactions_exportees.filter(planning_detail__isnull=False).count()
sans_planning_detail = total_exportes - avec_planning_detail

print(f"\n  Total exportées: {total_exportes}")
print(f"  Avec PlanningDetail: {avec_planning_detail}")
print(f"  Sans PlanningDetail: {sans_planning_detail}")

# Avances mises à jour
avances = transactions_exportees.filter(
    type_transaction='avance',
    planning_detail__isnull=False
)
avances_updated = avances.filter(
    planning_detail__numeroDiameXAvance__isnull=False,
    planning_detail__BaseDiameXAvance__isnull=False
)

print(f"\n  Avances exportées: {avances.count()}")
print(f"  Avances mises à jour: {avances_updated.count()}")

# Recettes/Dépenses mises à jour
autres = transactions_exportees.filter(
    planning_detail__isnull=False
).exclude(type_transaction='avance')

autres_updated = autres.filter(
    planning_detail__numeroDiameX__isnull=False,
    planning_detail__BaseDiameX__isnull=False
)

print(f"\n  Recettes/Dépenses exportées: {autres.count()}")
print(f"  Recettes/Dépenses mises à jour: {autres_updated.count()}")

# 4. Exemples de PlanningDetail mis à jour
print(f"\n{'=' * 80}")
print("4. EXEMPLES DE PLANNINGDETAIL MIS A JOUR:")

exemples = PlanningDetail.objects.filter(
    numeroDiameXAvance__isnull=False
) | PlanningDetail.objects.filter(
    numeroDiameX__isnull=False
)

if exemples.exists():
    for pd in exemples[:5]:
        print(f"\n  PlanningDetail ID: {pd.id}")
        if pd.numeroDiameXAvance:
            print(f"    Avance: numeroDiameXAvance={pd.numeroDiameXAvance}, BaseDiameXAvance={pd.BaseDiameXAvance}")
        if pd.numeroDiameX:
            print(f"    Recette: numeroDiameX={pd.numeroDiameX}, BaseDiameX={pd.BaseDiameX}")
else:
    print("\n  Aucun PlanningDetail avec numeroDiameX trouvé.")

print("\n" + "=" * 80)
