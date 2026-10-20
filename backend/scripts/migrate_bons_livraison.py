"""
Script de migration des bons de livraison depuis PlanningDetail vers BonLivraison

Ce script :
1. Récupère tous les PlanningDetail avec type_avance_caissiere = 'Bon de livraison'
2. Crée les enregistrements correspondants dans BonLivraison
3. Conserve les PlanningDetail originaux (pas de suppression)
4. Affiche des statistiques de migration

Exécution :
    cd backend
    python scripts/migrate_bons_livraison.py
"""

import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.planning.models import PlanningDetail, BonLivraison
from django.db import transaction


def migrate_bons_livraison():
    """Migrer tous les bons de livraison de PlanningDetail vers BonLivraison"""

    print("=" * 80)
    print("MIGRATION DES BONS DE LIVRAISON")
    print("=" * 80)
    print()

    # Étape 1 : Vérification
    print("Étape 1 : Analyse des données à migrer")
    print("-" * 80)

    livraisons_source = PlanningDetail.objects.filter(
        designation__type_avance_caissiere='Bon de livraison'
    ).select_related(
        'planning', 'designation', 'point_eau', 'equipement_constitutif', 'photo_justificatif'
    )

    total_livraisons = livraisons_source.count()
    print(f"Total bons de livraison trouvés dans PlanningDetail : {total_livraisons}")

    if total_livraisons == 0:
        print("Aucun bon de livraison à migrer.")
        return

    # Statistiques détaillées
    avec_planning = livraisons_source.filter(planning__isnull=False).count()
    avec_point_eau = livraisons_source.filter(point_eau__isnull=False).count()
    avec_equipement = livraisons_source.filter(equipement_constitutif__isnull=False).count()
    avec_magasin = livraisons_source.exclude(magasin__isnull=True).exclude(magasin='').count()
    utilises = livraisons_source.filter(utilise=True).count()
    retournes = livraisons_source.filter(retour=True).count()
    avec_numero_bon = livraisons_source.exclude(numero_bon_livraison__isnull=True).exclude(numero_bon_livraison='').count()

    print(f"  - Avec planning: {avec_planning}")
    print(f"  - Avec point d'eau: {avec_point_eau}")
    print(f"  - Avec équipement: {avec_equipement}")
    print(f"  - Avec magasin: {avec_magasin}")
    print(f"  - Utilisés (livrés): {utilises}")
    print(f"  - Retournés: {retournes}")
    print(f"  - Avec numéro de bon: {avec_numero_bon}")
    print()

    # Étape 2 : Confirmation
    print("Étape 2 : Confirmation")
    print("-" * 80)
    reponse = input(f"Voulez-vous migrer {total_livraisons} bons de livraison ? (oui/non) : ")
    if reponse.lower() not in ['oui', 'o', 'y', 'yes']:
        print("Migration annulée par l'utilisateur.")
        return
    print()

    # Étape 3 : Migration
    print("Étape 3 : Migration des données")
    print("-" * 80)

    nb_migres = 0
    nb_erreurs = 0
    erreurs = []

    with transaction.atomic():
        for detail in livraisons_source:
            try:
                # Créer le BonLivraison
                bon = BonLivraison.objects.create(
                    planning=detail.planning,
                    point_eau=detail.point_eau,
                    equipement=detail.equipement_constitutif,
                    designation=detail.designation,
                    quantite=detail.quantity,
                    magasin=detail.magasin,
                    utilise=detail.utilise,
                    date_utilisation=detail.date_utilisation,
                    retour=detail.retour,
                    date_retour=detail.date_retour,
                    numero_bon=detail.numero_bon_livraison,
                    photo_justificatif=detail.photo_justificatif,
                    created_at=detail.created_at,
                    updated_at=detail.updated_at
                )

                nb_migres += 1

                # Afficher la progression tous les 100 enregistrements
                if nb_migres % 100 == 0:
                    print(f"  Progression : {nb_migres}/{total_livraisons} ({int(nb_migres/total_livraisons*100)}%)")

            except Exception as e:
                nb_erreurs += 1
                erreur_msg = f"Erreur PlanningDetail {detail.id}: {str(e)}"
                erreurs.append(erreur_msg)
                print(f"  ❌ {erreur_msg}")

    print()
    print("=" * 80)
    print("RÉSULTAT DE LA MIGRATION")
    print("=" * 80)
    print(f"Total migrés : {nb_migres}/{total_livraisons}")
    print(f"Erreurs : {nb_erreurs}")
    print()

    if nb_erreurs > 0:
        print("Détails des erreurs :")
        for err in erreurs[:10]:  # Afficher max 10 erreurs
            print(f"  - {err}")
        if len(erreurs) > 10:
            print(f"  ... et {len(erreurs) - 10} autres erreurs")

    # Étape 4 : Vérification finale
    print()
    print("Étape 4 : Vérification finale")
    print("-" * 80)

    total_bons_livraison = BonLivraison.objects.count()
    print(f"Total BonLivraison en base : {total_bons_livraison}")

    # Statistiques finales
    avec_planning_final = BonLivraison.objects.filter(planning__isnull=False).count()
    avec_magasin_final = BonLivraison.objects.exclude(magasin__isnull=True).exclude(magasin='').count()
    utilises_final = BonLivraison.objects.filter(utilise=True).count()

    print(f"  - Avec planning: {avec_planning_final}")
    print(f"  - Avec magasin: {avec_magasin_final}")
    print(f"  - Utilisés (livrés): {utilises_final}")
    print()

    print("✅ Migration terminée avec succès !")
    print()
    print("IMPORTANT :")
    print("  - Les données originales dans PlanningDetail sont CONSERVÉES")
    print("  - Vérifiez les données migrées avant de supprimer le champ magasin de PlanningDetail")
    print("  - Mettez à jour les vues et templates pour utiliser BonLivraison")
    print()


if __name__ == '__main__':
    migrate_bons_livraison()
