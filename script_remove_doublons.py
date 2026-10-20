
from apps.planning.models import PlanningDetail
duplicates = PlanningDetail.objects.filter(designation__nom__icontains='Paiement forfaitaire')
count = duplicates.count()
if count > 0:
    duplicates.delete()
    print(f"✅ {count} paiements forfaitaires en doublon ont été supprimés de PlanningDetail avec succès.")
else:
    print("✅ Aucun paiement forfaitaire en doublon trouvé dans PlanningDetail.")
