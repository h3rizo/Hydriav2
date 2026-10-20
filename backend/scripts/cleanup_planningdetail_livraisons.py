"""
Script de nettoyage : Supprimer les bons de livraison de PlanningDetail
après migration vers BonLivraison

Ce script supprime les lignes PlanningDetail qui ont type_avance_caissiere = 'Bon de livraison'
car elles ont été migrées vers la table BonLivraison.

IMPORTANT: Exécuter seulement APRÈS avoir vérifié que la migration est réussie.
"""

import os
import sys
import django

# Configuration Django
project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from django.db import transaction
from apps.planning.models import PlanningDetail, BonLivraison


def cleanup_planningdetail_livraisons():
    """Supprimer les bons de livraison de PlanningDetail"""

    print("=" * 80)
    print("NETTOYAGE DES BONS DE LIVRAISON DANS PLANNINGDETAIL")
    print("=" * 80)
    print()

    # Étape 1 : Vérification
    print("Étape 1 : Analyse des données à supprimer")
    print("-" * 80)

    # Compter les bons de livraison dans PlanningDetail
    livraisons_pd = PlanningDetail.objects.filter(
        designation__type_avance_caissiere='Bon de livraison'
    ).select_related('designation', 'planning')

    total_pd = livraisons_pd.count()
    print(f"Total bons de livraison dans PlanningDetail : {total_pd}")

    if total_pd == 0:
        print("✓ Aucun bon de livraison à supprimer dans PlanningDetail.")
        print("  La base de données est déjà propre.")
        return

    # Compter les bons de livraison dans BonLivraison
    total_bl = BonLivraison.objects.count()
    print(f"Total bons de livraison dans BonLivraison : {total_bl}")
    print()

    # Statistiques détaillées
    utilises = livraisons_pd.filter(utilise=True).count()
    retournes = livraisons_pd.filter(retour=True).count()
    avec_numero = livraisons_pd.exclude(numero_bon_livraison__isnull=True).exclude(numero_bon_livraison='').count()

    print("Détails des lignes à supprimer :")
    print(f"  - Utilisés : {utilises}")
    print(f"  - Retournés : {retournes}")
    print(f"  - Avec numéro de bon : {avec_numero}")
    print()

    # Vérifier que le nombre est cohérent
    if total_pd > total_bl:
        print("ATTENTION : Il y a PLUS de bons dans PlanningDetail que dans BonLivraison !")
        print(f"   PlanningDetail : {total_pd}")
        print(f"   BonLivraison : {total_bl}")
        print(f"   Différence : {total_pd - total_bl}")
        print()
        print("   Cela peut indiquer que la migration n'est pas complete.")
        print("   Veuillez verifier avant de continuer.")
        print()

    # Étape 2 : Confirmation
    print("Etape 2 : Confirmation")
    print("-" * 80)
    print(f"ATTENTION : Cette operation va SUPPRIMER {total_pd} lignes de PlanningDetail")
    print("   Cette action est IRREVERSIBLE.")
    print()
    print("   Assurez-vous que :")
    print("   1. La migration vers BonLivraison est complète et vérifiée")
    print("   2. Vous avez une sauvegarde de la base de données")
    print("   3. Les bons de livraison sont accessibles via la table BonLivraison")
    print()

    reponse = input("Voulez-vous continuer avec la suppression ? (oui/non) : ")
    if reponse.lower() not in ['oui', 'o', 'y', 'yes']:
        print("Nettoyage annulé par l'utilisateur.")
        return
    print()

    # Double confirmation
    reponse2 = input("Êtes-vous VRAIMENT sûr ? Tapez 'SUPPRIMER' en majuscules pour confirmer : ")
    if reponse2 != 'SUPPRIMER':
        print("Nettoyage annulé par l'utilisateur.")
        return
    print()

    # Étape 3 : Suppression
    print("Étape 3 : Suppression des données")
    print("-" * 80)

    try:
        with transaction.atomic():
            # Supprimer les bons de livraison de PlanningDetail
            nb_supprimes, details = livraisons_pd.delete()

            print(f"OK - {nb_supprimes} objet(s) supprime(s) avec succes")
            print()
            print("Details de la suppression :")
            for model, count in details.items():
                if count > 0:
                    print(f"  - {model}: {count}")
            print()

    except Exception as e:
        print(f"ERREUR lors de la suppression : {e}")
        print("  La transaction a été annulée (rollback).")
        print("  Aucune donnée n'a été supprimée.")
        return

    # Étape 4 : Vérification finale
    print("Étape 4 : Vérification finale")
    print("-" * 80)

    # Recompter
    remaining_pd = PlanningDetail.objects.filter(
        designation__type_avance_caissiere='Bon de livraison'
    ).count()

    total_bl_after = BonLivraison.objects.count()

    print(f"Bons de livraison restants dans PlanningDetail : {remaining_pd}")
    print(f"Bons de livraison dans BonLivraison : {total_bl_after}")
    print()

    if remaining_pd == 0:
        print("OK - Nettoyage reussi !")
        print("  Toutes les donnees ont ete supprimees de PlanningDetail.")
        print("  Les bons de livraison sont maintenant uniquement dans BonLivraison.")
    else:
        print("ATTENTION : Il reste encore des bons de livraison dans PlanningDetail.")
        print("   Veuillez verifier manuellement.")

    print()
    print("=" * 80)
    print("NETTOYAGE TERMINE")
    print("=" * 80)


if __name__ == '__main__':
    cleanup_planningdetail_livraisons()
