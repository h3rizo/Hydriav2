"""
Script de nettoyage des tables Planning et PlanningDetail
pour migrer vers PaiementForfaitaire et CoupureEau

Étapes:
1. Vérifier les données existantes
2. Créer/vérifier les activités nécessaires
3. Mettre à jour les Plannings avec les nouvelles activités
4. Supprimer les PlanningDetails avec désignations forfaitaires
"""

import os
import sys
import django
from decimal import Decimal

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.planning.models import Planning, PlanningDetail, Designation, Activite, TypeActivite
from django.db.models import Count, Q


def print_separator():
    print("\n" + "="*80 + "\n")


def etape1_verification():
    """Vérifier les données existantes"""
    print("ÉTAPE 1: Vérification des données existantes")
    print_separator()

    # Désignations concernées
    designations = {
        'paiement': Designation.objects.filter(nom='Paiement forfaitaire').first(),
        'coupure': Designation.objects.filter(nom='Coupure d\'eau').first(),
        'remise': Designation.objects.filter(nom='Remise en eau').first()
    }

    for key, desig in designations.items():
        if desig:
            nb_details = PlanningDetail.objects.filter(designation=desig).count()
            print(f"OK Désignation '{desig.nom}' (ID: {desig.id})")
            print(f"  - {nb_details} PlanningDetails associés")

            # Plannings liés via PlanningDetail
            plannings_ids = PlanningDetail.objects.filter(
                designation=desig
            ).values_list('planning_id', flat=True).distinct()
            nb_plannings = len(plannings_ids)
            print(f"  - {nb_plannings} Plannings contenant cette désignation")
        else:
            print(f"ERREUR Désignation '{key}' non trouvée")

    print_separator()
    return designations


def etape2_activites():
    """Créer ou vérifier les activités nécessaires"""
    print("ÉTAPE 2: Création/vérification des activités")
    print_separator()

    # Type d'activité pour les activités de gestion
    type_gestion = TypeActivite.objects.filter(nomtype__icontains='gestion').first()
    if not type_gestion:
        # Créer un type si nécessaire
        type_gestion = TypeActivite.objects.create(nomtype='Gestion')
        print(f"OK Type d'activité 'Gestion' créé (ID: {type_gestion.id})")
    else:
        print(f"OK Type d'activité '{type_gestion.nomtype}' existant (ID: {type_gestion.id})")

    activites = {}
    noms_activites = {
        'collecte': 'Collecte paiement',
        'coupure': 'Coupure d\'eau',
        'remise': 'Remise en eau'
    }

    for key, nom in noms_activites.items():
        activite = Activite.objects.filter(nom=nom).first()
        if not activite:
            activite = Activite.objects.create(
                nom=nom,
                typeactivite=type_gestion
            )
            print(f"OK Activité '{nom}' créée (ID: {activite.id})")
        else:
            print(f"OK Activité '{nom}' existante (ID: {activite.id})")
        activites[key] = activite

    print_separator()
    return activites


def etape3_update_plannings(designations, activites):
    """Mettre à jour les Plannings avec les nouvelles activités"""
    print("ÉTAPE 3: Mise à jour des Plannings")
    print_separator()

    updates = {
        'paiement': ('paiement', 'collecte'),
        'coupure': ('coupure', 'coupure'),
        'remise': ('remise', 'remise')
    }

    total_updated = 0

    for key, (desig_key, activite_key) in updates.items():
        designation = designations.get(desig_key)
        activite = activites.get(activite_key)

        if not designation or not activite:
            print(f"ERREUR Impossible de mettre à jour pour '{key}' (données manquantes)")
            continue

        # Récupérer les Plannings contenant des PlanningDetails avec cette désignation
        plannings_ids = PlanningDetail.objects.filter(
            designation=designation
        ).values_list('planning_id', flat=True).distinct()

        plannings = Planning.objects.filter(id__in=plannings_ids)
        nb_plannings = plannings.count()

        if nb_plannings > 0:
            # Mettre à jour l'activité
            nb_updated = plannings.update(activite=activite)
            print(f"OK {nb_updated} Plannings mis a jour: '{designation.nom}' -> activite '{activite.nom}'")
            total_updated += nb_updated
        else:
            print(f"INFO Aucun Planning à mettre à jour pour '{designation.nom}'")

    print(f"\nTotal: {total_updated} Plannings mis à jour")
    print_separator()
    return total_updated


def etape4_delete_details(designations):
    """Supprimer les PlanningDetails avec désignations forfaitaires"""
    print("ÉTAPE 4: Suppression des PlanningDetails")
    print_separator()

    total_deleted = 0

    for key, designation in designations.items():
        if not designation:
            continue

        details = PlanningDetail.objects.filter(designation=designation)
        nb_details = details.count()

        if nb_details > 0:
            # Demander confirmation
            print(f"\nATTENTION  {nb_details} PlanningDetails avec désignation '{designation.nom}' seront supprimés")

            # Supprimer
            nb_deleted, _ = details.delete()
            print(f"OK {nb_deleted} PlanningDetails supprimés pour '{designation.nom}'")
            total_deleted += nb_deleted
        else:
            print(f"INFO Aucun PlanningDetail à supprimer pour '{designation.nom}'")

    print(f"\nTotal: {total_deleted} PlanningDetails supprimés")
    print_separator()
    return total_deleted


def etape5_verification_finale():
    """Vérifier l'intégrité après nettoyage"""
    print("ÉTAPE 5: Vérification finale")
    print_separator()

    # Vérifier qu'il ne reste plus de PlanningDetails avec ces désignations
    designations_noms = ['Paiement forfaitaire', 'Coupure d\'eau', 'Remise en eau']
    reste = PlanningDetail.objects.filter(
        designation__nom__in=designations_noms
    ).count()

    if reste == 0:
        print("OK Aucun PlanningDetail avec désignations forfaitaires restant")
    else:
        print(f"ERREUR ATTENTION: {reste} PlanningDetails avec désignations forfaitaires restent!")

    # Statistiques finales
    print(f"\nStatistiques finales:")
    print(f"- Total Plannings: {Planning.objects.count()}")
    print(f"- Total PlanningDetails: {PlanningDetail.objects.count()}")

    # Activités créées
    activites_creees = ['Collecte paiement', 'Coupure d\'eau', 'Remise en eau']
    for nom in activites_creees:
        activite = Activite.objects.filter(nom=nom).first()
        if activite:
            nb_plannings = Planning.objects.filter(activite=activite).count()
            print(f"- Plannings avec activité '{nom}': {nb_plannings}")

    print_separator()


def main():
    """Fonction principale"""
    print("\n" + "="*80)
    print("SCRIPT DE NETTOYAGE - MIGRATION PAIEMENTS FORFAITAIRES")
    print("="*80 + "\n")

    print("Ce script va:")
    print("1. Vérifier les données existantes")
    print("2. Créer/vérifier les activités 'Collecte paiement', 'Coupure d'eau', 'Remise en eau'")
    print("3. Mettre à jour les Plannings avec les nouvelles activités")
    print("4. Supprimer les PlanningDetails avec désignations forfaitaires")
    print("5. Vérifier l'intégrité des données")

    print("\nATTENTION  ATTENTION: Cette opération est IRRÉVERSIBLE!")
    reponse = input("\nContinuer? (oui/non): ")

    if reponse.lower() not in ['oui', 'o', 'yes', 'y']:
        print("\nOpération annulée.")
        return

    # Exécution des étapes
    try:
        designations = etape1_verification()
        activites = etape2_activites()
        nb_updated = etape3_update_plannings(designations, activites)
        nb_deleted = etape4_delete_details(designations)
        etape5_verification_finale()

        print("\n" + "="*80)
        print("OK NETTOYAGE TERMINÉ AVEC SUCCÈS")
        print("="*80)
        print(f"\nRésumé:")
        print(f"- {nb_updated} Plannings mis à jour")
        print(f"- {nb_deleted} PlanningDetails supprimés")
        print("\n")

    except Exception as e:
        print("\n" + "="*80)
        print("ERREUR ERREUR LORS DU NETTOYAGE")
        print("="*80)
        print(f"\n{str(e)}\n")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
