"""
Script de migration pour convertir les FicheStock de product vers designation
Ce script migre les anciennes fiches de stock qui utilisaient le champ product
vers le nouveau système basé sur designation.
"""

import os
import sys
import django

# Configuration Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.inventory.models import FicheStock, PurchaseItem, TransfertItem
from apps.planning.models import Designation
from django.db import transaction
from decimal import Decimal


def migrate_fichestock_achats():
    """Migrer les FicheStock d'achats de product vers designation"""
    print("\n=== Migration des FicheStock Achats ===")

    # Récupérer toutes les fiches d'achats avec product mais sans designation
    fiches_achats = FicheStock.objects.filter(
        operation_type='achat',
        product__isnull=False,
        designation__isnull=True
    ).select_related('product')

    total = fiches_achats.count()
    print(f"Trouvé {total} fiche(s) d'achat à migrer")

    if total == 0:
        print("Aucune fiche d'achat à migrer.")
        return 0

    migrated = 0
    errors = 0

    for fiche in fiches_achats:
        try:
            with transaction.atomic():
                # Récupérer l'item d'achat correspondant
                if fiche.purchase_id:
                    purchase_item = PurchaseItem.objects.filter(
                        purchase_id=fiche.purchase_id,
                        designation__isnull=False
                    ).select_related('designation', 'purchase').first()

                    if purchase_item and purchase_item.designation:
                        # Mettre à jour la fiche
                        fiche.designation = purchase_item.designation

                        # Si la référence est vide, ajouter le numéro d'achat
                        if not fiche.reference and purchase_item.purchase:
                            fiche.reference = purchase_item.purchase.purchase_number

                        fiche.save()
                        migrated += 1
                        print(f"[OK] Migre fiche {fiche.id} - {purchase_item.designation.nom}")
                    else:
                        print(f"[ERREUR] Impossible de trouver la designation pour la fiche {fiche.id} (purchase: {fiche.purchase_id})")
                        errors += 1
                else:
                    print(f"[ERREUR] Fiche {fiche.id} sans purchase_id")
                    errors += 1

        except Exception as e:
            print(f"[ERREUR] Erreur lors de la migration de la fiche {fiche.id}: {str(e)}")
            errors += 1

    print(f"\nRésumé Achats: {migrated} migrées, {errors} erreurs")
    return migrated


def migrate_fichestock_transferts():
    """Migrer les FicheStock de transferts de product vers designation"""
    print("\n=== Migration des FicheStock Transferts ===")

    # Récupérer toutes les fiches de transferts avec product mais sans designation
    fiches_transferts = FicheStock.objects.filter(
        operation_type__in=['transfert_entree', 'transfert_sortie'],
        product__isnull=False,
        designation__isnull=True
    ).select_related('product')

    total = fiches_transferts.count()
    print(f"Trouvé {total} fiche(s) de transfert à migrer")

    if total == 0:
        print("Aucune fiche de transfert à migrer.")
        return 0

    migrated = 0
    errors = 0

    for fiche in fiches_transferts:
        try:
            with transaction.atomic():
                # Récupérer l'item de transfert correspondant
                if fiche.transfert_id:
                    transfert_item = TransfertItem.objects.filter(
                        transfert_id=fiche.transfert_id,
                        designation__isnull=False
                    ).select_related('designation', 'transfert').first()

                    if transfert_item and transfert_item.designation:
                        # Mettre à jour la fiche
                        fiche.designation = transfert_item.designation

                        # Si la référence est vide, ajouter le numéro de transfert
                        if not fiche.reference and transfert_item.transfert:
                            fiche.reference = transfert_item.transfert.transfer_number

                        fiche.save()
                        migrated += 1
                        print(f"[OK] Migre fiche {fiche.id} - {transfert_item.designation.nom} ({fiche.operation_type})")
                    else:
                        print(f"[ERREUR] Impossible de trouver la designation pour la fiche {fiche.id} (transfert: {fiche.transfert_id})")
                        errors += 1
                else:
                    print(f"[ERREUR] Fiche {fiche.id} sans transfert_id")
                    errors += 1

        except Exception as e:
            print(f"[ERREUR] Erreur lors de la migration de la fiche {fiche.id}: {str(e)}")
            errors += 1

    print(f"\nRésumé Transferts: {migrated} migrées, {errors} erreurs")
    return migrated


def verify_migration():
    """Vérifier le résultat de la migration"""
    print("\n=== Vérification de la migration ===")

    # Compter les fiches avec product mais sans designation
    remaining_achats = FicheStock.objects.filter(
        operation_type='achat',
        product__isnull=False,
        designation__isnull=True
    ).count()

    remaining_transferts = FicheStock.objects.filter(
        operation_type__in=['transfert_entree', 'transfert_sortie'],
        product__isnull=False,
        designation__isnull=True
    ).count()

    # Compter les fiches migrées avec succès
    migrated_achats = FicheStock.objects.filter(
        operation_type='achat',
        designation__isnull=False
    ).count()

    migrated_transferts = FicheStock.objects.filter(
        operation_type__in=['transfert_entree', 'transfert_sortie'],
        designation__isnull=False
    ).count()

    print(f"\nAchats:")
    print(f"  - Avec designation: {migrated_achats}")
    print(f"  - Restant à migrer: {remaining_achats}")

    print(f"\nTransferts:")
    print(f"  - Avec designation: {migrated_transferts}")
    print(f"  - Restant à migrer: {remaining_transferts}")

    if remaining_achats == 0 and remaining_transferts == 0:
        print("\n[SUCCESS] Migration complete! Toutes les fiches ont ete migrees.")
    else:
        print(f"\n[WARNING] Il reste {remaining_achats + remaining_transferts} fiche(s) a verifier manuellement.")


def main():
    """Fonction principale"""
    print("="*60)
    print("Script de migration FicheStock: product -> designation")
    print("="*60)

    # Demander confirmation
    response = input("\nVoulez-vous lancer la migration? (oui/non): ")
    if response.lower() not in ['oui', 'o', 'yes', 'y']:
        print("Migration annulée.")
        return

    # Exécuter les migrations
    total_achats = migrate_fichestock_achats()
    total_transferts = migrate_fichestock_transferts()

    # Vérifier le résultat
    verify_migration()

    # Résumé final
    print("\n" + "="*60)
    print(f"Migration terminée: {total_achats + total_transferts} fiche(s) migrée(s)")
    print("="*60)


if __name__ == "__main__":
    main()
