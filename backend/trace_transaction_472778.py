"""
Script pour tracer le parcours de la transaction 472778 dans la logique de calcul des taxes
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
from decimal import Decimal

print("\n=== TRACE TRANSACTION 472778 DANS LOGIQUE TAXES COMMUNALES ===\n")

# Récupérer la transaction spécifique
try:
    transaction = BaseDiameX.objects.get(id=472778)
    print(f"[OK] Transaction trouvée: ID={transaction.id}")
    print(f"    Description: {transaction.description}")
    print(f"    Date: {transaction.date_rec}")
    print(f"    Compte: {transaction.compte_code}")
    print(f"    Montant IN: {transaction.montant_in}")
    print(f"    Montant OUT: {transaction.montant_out}")
except BaseDiameX.DoesNotExist:
    print("[ERROR] Transaction 472778 introuvable!")
    sys.exit(1)

print("\n--- ÉTAPE 1: Vérification montant > 0 ---")
montant = float(transaction.montant_in or 0)
print(f"Montant calculé: {montant}")
if montant <= 0:
    print("[FAIL] Transaction échouée: montant <= 0")
    sys.exit(0)
else:
    print("[PASS] Montant > 0")

print("\n--- ÉTAPE 2: Vérification compte 761000 ---")
if transaction.compte_code != '761000':
    print(f"[SKIP] Compte {transaction.compte_code} n'est pas 761000")
else:
    print("[PASS] Compte est 761000")

print("\n--- ÉTAPE 3: Vérification mot-clé 'réclamation' ---")
description_lower = (transaction.description or '').lower()
print(f"Description en minuscules: {description_lower}")

if 'réclamation' in description_lower:
    print("[PASS] Contient 'réclamation' (avec accent)")
elif 'reclamation' in description_lower:
    print("[PASS] Contient 'reclamation' (sans accent)")
else:
    print("[FAIL] Ne contient ni 'réclamation' ni 'reclamation'")
    sys.exit(0)

print("\n--- ÉTAPE 4: Extraction de l'ouvrage depuis la description ---")
# Simuler la logique d'extraction (simplifié)
ouvrages = Ouvrage.objects.all()
ouvrage_trouve = None

for ouvrage in ouvrages:
    if ouvrage.nom_ouvrage and ouvrage.nom_ouvrage in transaction.description:
        ouvrage_trouve = ouvrage
        print(f"[PASS] Ouvrage trouvé: {ouvrage.nom_ouvrage} (ID: {ouvrage.id})")
        break

if not ouvrage_trouve:
    print("[FAIL] Aucun ouvrage trouvé dans la description")
    sys.exit(0)

print("\n--- ÉTAPE 5: Résolution de la commune ---")
# Utiliser la même logique que get_commune_from_ouvrage_or_pe
point_eau = PointEau.objects.filter(ouvrage=ouvrage_trouve).first()

if not point_eau:
    print("[FAIL] Aucun point d'eau trouvé pour cet ouvrage")
    sys.exit(0)
else:
    print(f"[OK] Point d'eau trouvé: {point_eau.code_point_eau}")

if not point_eau.parcelle:
    print("[FAIL] Point d'eau n'a pas de parcelle")
    sys.exit(0)
else:
    print(f"[OK] Parcelle trouvée")

parcelle = point_eau.parcelle

if not parcelle.village:
    print("[FAIL] Parcelle n'a pas de village")
    sys.exit(0)
else:
    print(f"[OK] Village trouvé: {parcelle.village.nom_village}")

if not parcelle.village.fokontany:
    print("[FAIL] Village n'a pas de fokontany")
    sys.exit(0)
else:
    print(f"[OK] Fokontany trouvé: {parcelle.village.fokontany.nom_fokontany}")

if not parcelle.village.fokontany.commune:
    print("[FAIL] Fokontany n'a pas de commune")
    sys.exit(0)
else:
    commune = parcelle.village.fokontany.commune
    print(f"[OK] Commune trouvée: {commune.nom_commune} (ID: {commune.id})")

print("\n--- ÉTAPE 6: Vérification filtre commune (si applicable) ---")
commune_cible_id = '1eafffe3-190c-491d-b1f7-6647cb994576'

if str(commune.id) == commune_cible_id:
    print(f"[PASS] Commune correspond au filtre: {commune.nom_commune}")
else:
    print(f"[INFO] Commune différente: {commune.id} != {commune_cible_id}")
    print(f"       Cela peut expliquer pourquoi elle n'apparaît pas si filtre actif")

print("\n--- ÉTAPE 7: Calcul de la taxe ---")
taux = 0.50  # 50% pour compte 761000
taxe = Decimal(str(montant)) * Decimal(str(taux))
print(f"Montant: {montant} Ar")
print(f"Taux: {taux * 100}%")
print(f"Taxe calculée: {taxe} Ar")

print("\n--- ÉTAPE 8: Vérification requête initiale de la vue ---")
print("La vue utilise cette requête:")
print("  BaseDiameX.objects.filter(")
print("      compte_code__in=['707401', '748411', '761000'],")
print("      date_rec__year=annee")
print("  ).order_by('date_rec')")

# Vérifier si la transaction serait incluse dans cette requête pour 2025
transactions_2025 = BaseDiameX.objects.filter(
    compte_code__in=['707401', '748411', '761000'],
    date_rec__year=2025
)

if transaction in transactions_2025:
    print(f"[PASS] Transaction 472778 est bien incluse dans la requête initiale (année 2025)")
    print(f"       Total de transactions récupérées: {transactions_2025.count()}")
else:
    print("[FAIL] Transaction 472778 n'est PAS dans la requête initiale")

print("\n=== RÉSUMÉ ===")
print(f"Transaction 472778:")
print(f"  ✓ Montant: {montant} Ar (> 0)")
print(f"  ✓ Compte: 761000")
print(f"  ✓ Contient 'réclamation'")
print(f"  ✓ Ouvrage: {ouvrage_trouve.nom_ouvrage if ouvrage_trouve else 'Non trouvé'}")
print(f"  ✓ Commune: {commune.nom_commune if commune else 'Non trouvée'}")
print(f"  ✓ Taxe calculée: {taxe} Ar")
print("\nCette transaction DEVRAIT apparaître dans le calcul des taxes.")
print("Si elle n'apparaît pas, il y a probablement un problème de filtrage géographique")
print("ou un problème dans l'extraction de l'ouvrage depuis la description.")

print("\n=== FIN DE LA TRACE ===\n")
