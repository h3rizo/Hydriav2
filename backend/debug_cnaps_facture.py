import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import PaiementCNaPSFMFP, PaiementCNaPSFMFPDetail

# Récupérer le dernier paiement
paiement = PaiementCNaPSFMFP.objects.order_by('-created_at').first()

if paiement:
    print(f"Paiement ID: {paiement.id}")
    print(f"Organisation: {paiement.organisation.nom_organisation}")
    print(f"Trimestre: {paiement.trimestre} - Annee: {paiement.annee}")
    print(f"Statut: {paiement.statut}")
    print(f"Date paiement: {paiement.date_paiement}")
    print(f"\nNombre de details dans la DB: {paiement.details.count()}")
    print(f"Montant total CNaPS: {paiement.montant_total_cnaps}")
    print(f"Montant total FMFP: {paiement.montant_total_fmfp}")
    
    print("\n=== Details ===")
    for detail in paiement.details.all():
        print(f"- {detail.employe_nom_complet} ({detail.employe_fonction})")
        print(f"  M1: CNaPS={detail.mois_1_cnaps} FMFP={detail.mois_1_fmfp}")
        print(f"  M2: CNaPS={detail.mois_2_cnaps} FMFP={detail.mois_2_fmfp}")
        print(f"  M3: CNaPS={detail.mois_3_cnaps} FMFP={detail.mois_3_fmfp}")
        print(f"  Total: CNaPS={detail.total_cnaps} FMFP={detail.total_fmfp}")
else:
    print("Aucun paiement CNaPS/FMFP trouve")
