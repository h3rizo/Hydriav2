"""
Script pour vérifier les transactions 761000 avec "réclamation"
"""
import os
import sys
import django

# Configuration Django
sys.path.insert(0, '/home/soakoja/hydria/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import BaseDiameX
from apps.organization.models import Ouvrage
from apps.billing.models import PointEau
from apps.geography.models import Village, Fokontany, Commune

# Rechercher les transactions 761000 avec "réclamation" pour l'année 2025
print("\n=== RECHERCHE TRANSACTIONS 761000 AVEC 'réclamation' (ANNÉE 2025) ===\n")

transactions = BaseDiameX.objects.filter(
    compte_code='761000',
    date_rec__year=2025
)

print(f"Total transactions 761000 en 2025: {transactions.count()}")

# Filtrer celles avec "réclamation" dans la description
transactions_reclamation = []
for t in transactions:
    description_lower = (t.description or '').lower()
    if 'réclamation' in description_lower or 'reclamation' in description_lower:
        transactions_reclamation.append(t)

print(f"Transactions avec 'réclamation': {len(transactions_reclamation)}\n")

# Analyser chaque transaction
commune_cible_id = '1eafffe3-190c-491d-b1f7-6647cb994576'

for i, transaction in enumerate(transactions_reclamation, 1):
    print(f"--- TRANSACTION {i} ---")
    print(f"ID: {transaction.id}")
    print(f"Description: {transaction.description}")
    print(f"Date: {transaction.date_rec}")
    print(f"Montant IN: {transaction.montant_in}")
    print(f"Montant OUT: {transaction.montant_out}")

    # Vérifier le montant
    montant = float(transaction.montant_in or 0)
    print(f"Montant calculé: {montant}")
    if montant <= 0:
        print("❌ PROBLÈME: Montant <= 0 (transaction ignorée par le filtre)")
    else:
        print("✅ Montant > 0")

    # Essayer de trouver l'ouvrage et la commune associés
    print("\nRecherche commune associée...")

    # La logique de get_commune_from_ouvrage_or_pe n'est pas directement accessible ici
    # On va essayer de trouver via la description si elle contient un nom d'ouvrage

    # Chercher tous les ouvrages pour voir si un nom correspond
    ouvrages = Ouvrage.objects.all()
    ouvrage_trouve = None

    for ouvrage in ouvrages:
        if ouvrage.nom_ouvrage and ouvrage.nom_ouvrage in transaction.description:
            ouvrage_trouve = ouvrage
            print(f"Ouvrage potentiel trouvé: {ouvrage.nom_ouvrage} (ID: {ouvrage.id})")

            # Trouver un point d'eau de cet ouvrage
            point_eau = PointEau.objects.filter(ouvrage=ouvrage).first()
            if point_eau and point_eau.parcelle:
                parcelle = point_eau.parcelle
                if parcelle.village and parcelle.village.fokontany and parcelle.village.fokontany.commune:
                    commune = parcelle.village.fokontany.commune
                    print(f"Commune trouvée: {commune.nom_commune} (ID: {commune.id})")

                    if str(commune.id) == commune_cible_id:
                        print("✅ COMMUNE CORRESPOND AU FILTRE!")
                    else:
                        print(f"❌ PROBLÈME: Commune différente de celle filtrée ({commune_cible_id})")
                else:
                    print("⚠️ Commune non trouvée dans la chaîne de relations")
            else:
                print("⚠️ Point d'eau ou parcelle non trouvé")
            break

    if not ouvrage_trouve:
        print("⚠️ Aucun ouvrage identifié dans la description")

    print()

print("\n=== FIN DE L'ANALYSE ===\n")