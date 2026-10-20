from apps.inventory.models import FicheStock, Stock
from apps.organization.models import Magasin
from apps.planning.models import Designation


designation_qs = Designation.objects.filter(nom__icontains="Collier de prise 25")
magasin_qs = Magasin.objects.filter(nom_magasin__icontains="Vohilengo")

print("DESIGNATIONS")
for row in designation_qs.values_list("id", "nom")[:10]:
    print(row)

print("MAGASINS")
for row in magasin_qs.values_list("id", "nom_magasin", "base__nom_base")[:10]:
    print(row)

print("STOCKS")
stocks = Stock.objects.filter(
    designation__in=designation_qs,
    base__in=magasin_qs.values("base_id"),
).select_related("designation", "base")
for stock in stocks:
    print(
        {
            "stock_id": str(stock.id),
            "designation": stock.designation.nom,
            "base": stock.base.nom_base,
            "current_quantity": str(stock.current_quantity),
            "available_quantity": str(stock.available_quantity),
            "inventory_date": str(stock.inventory_date),
            "rapproche": stock.rapproche,
        }
    )

print("FICHES")
fiches = (
    FicheStock.objects.filter(
        designation__in=designation_qs,
        base__in=magasin_qs.values("base_id"),
    )
    .order_by("-operation_date", "-created_at")[:20]
)
for fiche in fiches:
    print(
        {
            "operation_type": fiche.operation_type,
            "quantity": str(fiche.quantity),
            "operation_date": str(fiche.operation_date),
            "created_at": str(fiche.created_at),
            "notes": (fiche.notes or "")[:220],
        }
    )
