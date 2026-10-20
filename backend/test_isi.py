from apps.accounting.models import BaseDiameX, DiameXTemporaire
from django.db.models import Q

# Chercher dans BaseDiameX
isi_base = BaseDiameX.objects.filter(
    Q(description__istartswith='ISI_') | Q(description__istartswith='_ISI')
)
print(f"Transactions ISI dans BaseDiameX: {isi_base.count()}")

if isi_base.count() > 0:
    exemple = isi_base.first()
    print(f"Exemple BaseDiameX:")
    print(f"  Description: {exemple.description}")
    print(f"  Activ: {exemple.activ if hasattr(exemple, 'activ') else 'N/A'}")
    print(f"  Date: {exemple.date_m if hasattr(exemple, 'date_m') else 'N/A'}")
    print(f"  Montant OUT: {exemple.montant_out if hasattr(exemple, 'montant_out') else 'N/A'}")
    print()

    # Afficher les 5 premiers
    print("5 premiers exemples:")
    for i, t in enumerate(isi_base[:5], 1):
        print(f"{i}. {t.description} - Activ: {getattr(t, 'activ', 'N/A')} - Date: {getattr(t, 'date_m', 'N/A')}")

# Chercher dans DiameXTemporaire
isi_temp = DiameXTemporaire.objects.filter(
    Q(description__istartswith='ISI_') | Q(description__istartswith='_ISI')
)
print(f"\nTransactions ISI dans DiameXTemporaire: {isi_temp.count()}")

if isi_temp.count() > 0:
    exemple = isi_temp.first()
    print(f"Exemple DiameXTemporaire:")
    print(f"  Description: {exemple.description}")
    print(f"  Activ: {exemple.activ if hasattr(exemple, 'activ') else 'N/A'}")
