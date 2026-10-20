"""
Chercher des correspondances exactes entre DiameX et PlanningDetails
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.planning.models import PlanningDetail
from apps.accounting.models import BaseDiameX
from apps.organization.models import CompteTable

print("Recherche de correspondances exactes...")
print("=" * 80)

# Récupérer les comptes autorisés
comptes_autorises = CompteTable.objects.filter(
    nom_table='plannings_details',
    actif=True
).values_list('compte__compte', flat=True)

# Récupérer les lignes DiameX
diamex_lines = BaseDiameX.objects.filter(
    compte_code__in=list(comptes_autorises)
).order_by('-date_m')[:100]  # Les 100 plus récentes

print(f"Vérification de {diamex_lines.count()} lignes DiameX récentes...\n")

matches_found = 0
no_matches = 0

for entry in diamex_lines:
    # Chercher correspondance
    matches = PlanningDetail.objects.filter(
        numeroDiameX=entry.id_access,
        BaseDiameX=entry.prog
    )

    if matches.exists():
        matches_found += 1
        print(f"✓ CORRESPONDANCE TROUVEE:")
        print(f"  DiameX: ID={entry.id_access}, Prog={entry.prog}")
        print(f"  Date: {entry.date_m}, Description: {entry.description[:50]}")
        print(f"  Montant DiameX: IN={entry.montant_in}, OUT={entry.montant_out}")
        print(f"  → {matches.count()} PlanningDetail(s):")
        for pd in matches[:3]:
            print(f"    - {pd.designation.nom if pd.designation else 'Sans désignation'}: {pd.montant} Ar")
        print()
    else:
        no_matches += 1

print("=" * 80)
print(f"RÉSULTATS SUR LES 100 LIGNES LES PLUS RÉCENTES:")
print(f"  Correspondances trouvées: {matches_found}")
print(f"  Sans correspondance: {no_matches}")
print("=" * 80)

if matches_found == 0:
    print("\nAUCUNE CORRESPONDANCE TROUVÉE")
    print("\nVérification des PlanningDetails disponibles:")

    # Prendre quelques PlanningDetails avec numeroDiameX
    sample_pd = PlanningDetail.objects.filter(
        numeroDiameX__isnull=False,
        BaseDiameX__isnull=False
    )[:5]

    print(f"\nExemples de PlanningDetails (5 premiers):")
    for pd in sample_pd:
        print(f"  numeroDiameX={pd.numeroDiameX}, BaseDiameX={pd.BaseDiameX}")

        # Chercher si un DiameX correspond
        diamex_match = BaseDiameX.objects.filter(
            id_access=pd.numeroDiameX,
            prog=pd.BaseDiameX
        ).first()

        if diamex_match:
            print(f"    → MATCH TROUVÉ dans DiameX!")
        else:
            print(f"    → Pas de ligne DiameX correspondante")
            # Chercher par ID uniquement
            by_id_only = BaseDiameX.objects.filter(id_access=pd.numeroDiameX).first()
            if by_id_only:
                print(f"       (DiameX ID {pd.numeroDiameX} existe mais avec prog '{by_id_only.prog}')")
