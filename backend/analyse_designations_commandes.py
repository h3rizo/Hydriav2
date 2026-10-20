"""Analyser les désignations pour le calcul de commandes"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.planning.models import Designation, PlanningDetail
from apps.organization.models import Base
from django.db.models import Sum, Count, Q
from datetime import datetime, timedelta

# Récupérer les désignations avec concerne_livraison=True
designations_livraison = Designation.objects.filter(concerne_livraison=True)

print("=== DESIGNATIONS LIVRAISON ===")
print(f"Total: {designations_livraison.count()}")
if designations_livraison.count() > 0:
    print("\nListe (20 premiers):")
    for d in designations_livraison[:20]:
        print(f"  - {d.nom} (Type: {d.type_designation.nom if d.type_designation else 'N/A'})")
else:
    print("Aucune désignation avec concerne_livraison=True trouvée")

# Analyser les PlanningDetails
print("\n=== PLANNING DETAILS PAR BASE (30 derniers jours) ===")
date_debut = datetime.now() - timedelta(days=30)

bases = Base.objects.all()
for base in bases:
    # Compter les détails non encore livrés (utilise=True mais retour=False ou utilise=False)
    details_base = PlanningDetail.objects.filter(
        Q(designation__concerne_livraison=True),
        Q(magasin=base),
        Q(planning__date__gte=date_debut),
        Q(utilise=False) | Q(retour=False)  # Pas encore utilisé ou pas encore retourné
    )

    if details_base.count() > 0:
        print(f"\nBase: {base.nom_base}")
        print(f"  Lignes non livrées: {details_base.count()}")

        # Grouper par désignation
        stats = details_base.values('designation__nom').annotate(
            total_quantite=Sum('quantite'),
            nb_lignes=Count('id')
        ).order_by('-total_quantite')[:10]

        if stats:
            print("  Top 10 désignations à commander:")
            for stat in stats:
                print(f"    {stat['designation__nom']}: {stat['total_quantite']} unités")

print("\n=== STATISTIQUES GLOBALES ===")
total_non_livres = PlanningDetail.objects.filter(
    designation__concerne_livraison=True,
    planning__date__gte=date_debut
).filter(
    Q(utilise=False) | Q(retour=False)
).count()

print(f"Total lignes non livrées (30 derniers jours): {total_non_livres}")
