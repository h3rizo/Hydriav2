"""
Script de test du workflow Achat -> FicheStock
================================================

Ce script teste que les signaux créent correctement des FicheStock
lorsqu'un achat est marqué comme livré.

Étapes:
1. Créer un achat avec statut 'commande'
2. Marquer l'achat comme 'livre'
3. Vérifier qu'une FicheStock a été créée automatiquement
"""

import os
import sys
import django

# Configuration Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from decimal import Decimal
from datetime import date
from apps.inventory.models import Purchase, PurchaseItem, FicheStock
from apps.organization.models import Magasin, Base
from apps.employees.models import Employe
from apps.planning.models import Designation
from apps.billing.models import Fournisseur

def test_workflow():
    print("\n" + "="*70)
    print("TEST WORKFLOW: Achat -> FicheStock")
    print("="*70)

    # 1. Récupérer les données nécessaires
    print("\n[ETAPE 1] Récupération des données de test...")

    try:
        # Trouver un magasin avec sa base
        magasin = Magasin.objects.select_related('base').first()
        if not magasin:
            print("[ERREUR] Aucun magasin trouvé dans la BDD")
            return
        print(f"[OK] Magasin: {magasin.nom_magasin}")

        base = magasin.base
        if not base:
            print("[ERREUR] Le magasin n'a pas de base associée")
            return
        print(f"[OK] Base: {base.nom_base}")

        employe = Employe.objects.filter(date_debauchage__isnull=True).first()
        if not employe:
            print("[ERREUR] Aucun employé actif trouvé")
            return
        print(f"[OK] Employé: {employe.nom_complet}")

        designation = Designation.objects.filter(actif=True).first()
        if not designation:
            print("[ERREUR] Aucune désignation active trouvée")
            return
        print(f"[OK] Designation: {designation.nom}")

        fournisseur = Fournisseur.objects.first()
        if not fournisseur:
            print("[WARNING] Aucun fournisseur trouvé - création optionnelle")
        else:
            print(f"[OK] Fournisseur: {fournisseur.nom_fournisseur}")

    except Exception as e:
        print(f"[ERREUR] {str(e)}")
        return

    # 2. Créer un achat avec statut 'commande'
    print("\n[ETAPE 2] Création d'un achat en statut 'commande'...")

    try:
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        purchase = Purchase.objects.create(
            purchase_number=f"TEST-{timestamp}",
            purchase_date=date.today(),
            order_date=date.today(),
            purchase_status='commande',
            magasin=magasin,
            ordered_by=employe,
            fournisseur=fournisseur,
            total_amount=Decimal('50000.00')
        )
        print(f"[OK] Achat créé: {purchase.purchase_number}")

        purchase_item = PurchaseItem.objects.create(
            purchase=purchase,
            designation=designation,
            quantity_ordered=Decimal('10.00'),
            unit_price=Decimal('5000.00')
        )
        print(f"[OK] Item créé: {designation.nom} x 10")

    except Exception as e:
        print(f"[ERREUR] {str(e)}")
        return

    # 3. Vérifier qu'aucune FicheStock n'existe encore
    print("\n[ETAPE 3] Vérification: pas de FicheStock pour un achat en 'commande'...")

    fiche_count_before = FicheStock.objects.filter(
        purchase_id=str(purchase.id),
        designation=designation
    ).count()
    print(f"[OK] Nombre de FicheStock avant livraison: {fiche_count_before}")

    if fiche_count_before > 0:
        print("[WARNING] Des FicheStock existent déjà! (ne devrait pas arriver)")

    # 4. Marquer l'achat comme 'livre'
    print("\n[ETAPE 4] Marquage de l'achat comme 'livre'...")

    try:
        purchase.purchase_status = 'livre'
        purchase.actual_delivery_date = date.today()
        purchase_item.quantity_received = Decimal('10.00')
        purchase_item.save()
        purchase.save()  # Ceci devrait déclencher le signal post_save

        print(f"[OK] Achat {purchase.purchase_number} marqué comme livré")

    except Exception as e:
        print(f"[ERREUR] {str(e)}")
        return

    # 5. Vérifier qu'une FicheStock a été créée
    print("\n[ETAPE 5] Vérification de la création de FicheStock...")

    fiches = FicheStock.objects.filter(
        purchase_id=str(purchase.id),
        designation=designation
    )

    print(f"\n[RESULTAT] Nombre de FicheStock après livraison: {fiches.count()}")

    if fiches.count() == 0:
        print("[ECHEC] Aucune FicheStock créée!")
        print("\nCauses possibles:")
        print("1. Le signal post_save n'a pas été déclenché")
        print("2. La condition 'purchase_status == livre' n'est pas remplie")
        print("3. Une erreur silencieuse dans le signal")
        print("4. La base du magasin est None")

        print(f"\nDébogage:")
        print(f"  - purchase_status: {purchase.purchase_status}")
        print(f"  - magasin.base: {purchase.magasin.base}")
        print(f"  - designation: {designation}")

    else:
        print("[SUCCESS] FicheStock créée avec succès!")
        for fiche in fiches:
            print(f"\nDétails de la FicheStock:")
            print(f"  - ID: {fiche.id}")
            print(f"  - Date opération: {fiche.operation_date}")
            print(f"  - Type: {fiche.operation_type}")
            print(f"  - Quantité: {fiche.quantity}")
            print(f"  - Prix unitaire: {fiche.unit_price}")
            print(f"  - Designation: {fiche.designation.nom if fiche.designation else 'None'}")
            print(f"  - Base: {fiche.base.nom_base if fiche.base else 'None'}")
            print(f"  - Employé: {fiche.employee.nom_complet if fiche.employee else 'None'}")
            print(f"  - Référence: {fiche.reference}")
            print(f"  - Notes: {fiche.notes}")

    # 6. Nettoyage
    print("\n[ETAPE 6] Nettoyage des données de test...")

    response = input("\nSupprimer les données de test? (o/n): ")

    if response.lower() == 'o':
        fiches.delete()
        purchase_item.delete()
        purchase.delete()
        print("[OK] Données de test supprimées")
    else:
        print(f"[INFO] Données conservées:")
        print(f"  - Achat: {purchase.purchase_number}")
        print(f"  - FicheStock(s): {fiches.count()}")

    print("\n" + "="*70)
    print("FIN DU TEST")
    print("="*70 + "\n")

if __name__ == '__main__':
    test_workflow()
