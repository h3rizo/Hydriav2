"""Script pour analyser les désignations de type 'Bon de livraison'"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.planning.models import Designation, TypeDesignation, PlanningDetail
from apps.organization.models import Base
from django.db.models import Sum, Count

# Récupérer le type "Avance caissière"
type_avance = TypeDesignation.objects.filter(nom__icontains='avance').first()
print(f"=== TYPE DESIGNATION ===")
print(f"Type trouvé: {type_avance.nom if type_avance else 'Non trouvé'}")
print()

# Récupérer les désignations "Bon de livraison"
designations_livraison = Designation.objects.filter(
    type_designation=type_avance,
    concerne_livraison=True
).order_by('nom')

print(f"=== DESIGNATIONS BON DE LIVRAISON ===")
print(f"Total: {designations_livraison.count()}")
print()

if designations_livraison.count() > 0:
    print("Liste:")
    for d in designations_livraison[:20]:
        print(f"  - {d.nom} (ID: {d.id})")
    print()

# Analyser les PlanningDetails avec ces désignations
print("=== PLANNING DETAILS PAR BASE ===")
bases = Base.objects.all()

for base in bases:
    # Compter les planningdetails affectés à cette base
    details = PlanningDetail.objects.filter(
        designation__type_designation=type_avance,
        designation__concerne_livraison=True,
        magasin=base
    )

    if details.count() > 0:
        print(f"\nBase: {base.nom_base}")
        print(f"  Total lignes: {details.count()}")

        # Grouper par désignation
        stats = details.values('designation__nom').annotate(
            total_quantite=Sum('quantite'),
            nb_lignes=Count('id')
        ).order_by('-total_quantite')[:10]

        print("  Top 10 désignations:")
        for stat in stats:
            print(f"    {stat['designation__nom']}: {stat['total_quantite']} unités ({stat['nb_lignes']} lignes)")

print("\n=== RESUME ===")
total_details = PlanningDetail.objects.filter(
    designation__type_designation=type_avance,
    designation__concerne_livraison=True
).count()
print(f"Total PlanningDetails 'Bon de livraison': {total_details}")
