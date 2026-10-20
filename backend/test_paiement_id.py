import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import PaiementCNaPSFMFP

# Récupérer tous les paiements
paiements = PaiementCNaPSFMFP.objects.all()

print(f"Nombre total de paiements CNaPS/FMFP: {paiements.count()}")
print("\n=== Liste des paiements ===")

for p in paiements:
    print(f"ID: {p.id}")
    print(f"  Organisation: {p.organisation.nom_organisation}")
    print(f"  Trimestre {p.trimestre} - {p.annee}")
    print(f"  Statut: {p.statut}")
    print(f"  Nb details: {p.details.count()}")
    print()
