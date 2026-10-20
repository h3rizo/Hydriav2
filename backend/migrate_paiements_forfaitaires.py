"""
Script de migration des paiements forfaitaires depuis planning_details vers paiements_forfaitaires

Ce script récupère tous les PlanningDetail avec une désignation "Paiement forfaitaire"
et les copie dans la nouvelle table PaiementForfaitaire.

Usage:
    python manage.py shell < migrate_paiements_forfaitaires.py
"""

import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.planning.models import PlanningDetail, Planning, Designation
from apps.billing.models import PaiementForfaitaire, PointEau
from django.db.models import Q
import pytz
from datetime import datetime

# Timezone Madagascar
tz_madagascar = pytz.timezone('Indian/Antananarivo')

def migrate_paiements_forfaitaires():
    """Migration des paiements forfaitaires depuis planning_details"""

    print("=" * 80)
    print("MIGRATION DES PAIEMENTS FORFAITAIRES")
    print("=" * 80)

    # 1. Trouver la désignation "Paiement forfaitaire"
    try:
        designation_forfait = Designation.objects.filter(
            Q(nom__icontains='paiement') & Q(nom__icontains='forfait')
        ).first()

        if not designation_forfait:
            print("[ERREUR] Aucune designation 'Paiement forfaitaire' trouvee")
            print("\nDesignations disponibles contenant 'forfait':")
            for d in Designation.objects.filter(nom__icontains='forfait'):
                print(f"  - {d.nom} (ID: {d.id})")
            return

        print(f"[OK] Designation trouvee: {designation_forfait.nom} (ID: {designation_forfait.id})")

    except Exception as e:
        print(f"[ERREUR] Erreur lors de la recherche de la designation: {e}")
        return

    # 2. Récupérer tous les PlanningDetail avec cette désignation
    planning_details = PlanningDetail.objects.filter(
        designation=designation_forfait
    ).select_related('planning', 'point_eau').order_by('planning__date')

    total = planning_details.count()
    print(f"\nNombre de PlanningDetail a migrer: {total}")

    if total == 0:
        print("[INFO] Aucune donnee a migrer")
        return

    # 3. Statistiques avant migration
    print("\nStatistiques:")
    with_point_eau = planning_details.filter(point_eau__isnull=False).count()
    with_planning = planning_details.filter(planning__isnull=False).count()
    with_numeroDiameX = planning_details.filter(numeroDiameX__isnull=False).count()

    print(f"  - Avec Point d'eau: {with_point_eau}/{total}")
    print(f"  - Avec Planning: {with_planning}/{total}")
    print(f"  - Avec numero DiameX: {with_numeroDiameX}/{total}")

    # 4. Vérifier les paiements déjà migrés
    existing_count = PaiementForfaitaire.objects.count()
    print(f"\nPaiements forfaitaires deja dans la nouvelle table: {existing_count}")

    # 5. Demander confirmation
    print("\n" + "=" * 80)
    confirm = input("Continuer la migration ? (oui/non): ")
    if confirm.lower() not in ['oui', 'o', 'yes', 'y']:
        print("[ANNULE] Migration annulee")
        return

    # 6. Migration
    print("\nDebut de la migration...")
    migres = 0
    erreurs = []
    skipped = 0

    for detail in planning_details:
        try:
            # Vérifier que le point d'eau existe
            if not detail.point_eau:
                erreurs.append(f"PlanningDetail {detail.id}: Pas de point d'eau")
                skipped += 1
                continue

            # Vérifier que le planning existe
            if not detail.planning:
                erreurs.append(f"PlanningDetail {detail.id}: Pas de planning")
                skipped += 1
                continue

            # Date facture (date du planning)
            date_facture = detail.planning.date
            if date_facture.tzinfo:
                date_facture_mg = date_facture.astimezone(tz_madagascar).date()
            else:
                date_facture_mg = tz_madagascar.localize(date_facture).date()

            # Vérifier si déjà migré (même point_eau + même date)
            existe = PaiementForfaitaire.objects.filter(
                point_eau=detail.point_eau,
                date_facture=date_facture_mg
            ).exists()

            if existe:
                skipped += 1
                continue

            # Créer le paiement forfaitaire
            paiement = PaiementForfaitaire(
                point_eau=detail.point_eau,
                date_facture=date_facture_mg,
                quantite=int(detail.quantity) if detail.quantity else 1,
                prix_unitaire=detail.pu,
                montant=detail.montant,
                paye=bool(detail.numeroDiameX),
                numeroDiameX=str(detail.numeroDiameX) if detail.numeroDiameX else None,
                baseDiameX=detail.BaseDiameX if detail.BaseDiameX else None,
            )

            # Si payé, définir date_paiement = date_facture
            if paiement.paye:
                paiement.date_paiement = date_facture_mg

            paiement.save()
            migres += 1

            if migres % 100 == 0:
                print(f"  -> {migres} paiements migres...")

        except Exception as e:
            erreurs.append(f"PlanningDetail {detail.id}: {str(e)}")

    # 7. Résumé
    print("\n" + "=" * 80)
    print("RESUME DE LA MIGRATION")
    print("=" * 80)
    print(f"[OK] Paiements migres avec succes: {migres}")
    print(f"[SKIP] Paiements ignores (deja migres ou en doublon): {skipped}")
    print(f"[ERREUR] Erreurs: {len(erreurs)}")

    if erreurs:
        print("\nDetail des erreurs (10 premieres):")
        for err in erreurs[:10]:
            print(f"  - {err}")
        if len(erreurs) > 10:
            print(f"  ... et {len(erreurs) - 10} autres erreurs")

    # 8. Vérification finale
    final_count = PaiementForfaitaire.objects.count()
    print(f"\nTotal de paiements forfaitaires dans la nouvelle table: {final_count}")
    print(f"   (Avant migration: {existing_count}, Nouveaux: {migres})")

    print("\n[OK] Migration terminee!")

if __name__ == '__main__':
    migrate_paiements_forfaitaires()
