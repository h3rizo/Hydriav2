#!/usr/bin/env python
"""Script de test pour le workflow des gardiens"""

import os
import django
from datetime import date, timedelta

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import Employe
from apps.employees.models_gardiens import RotationGardien, HeuresSupplementairesGardien
from apps.employees.views_gardiens import generer_rotation_standard, GARDIENS_IDS


print("\n" + "="*80)
print("TEST WORKFLOW GARDIENS - ROTATIONS ET CONGÉS SPÉCIAUX")
print("="*80 + "\n")

# Étape 1 : Vérifier les gardiens
print("[LOG] Etape 1: Verification des gardiens")
for gardien_id in GARDIENS_IDS:
    employe = Employe.objects.get(id=gardien_id)
    print(f"  - {employe.surnom or employe.nom} (ID: {gardien_id})")

# Étape 2 : Générer une rotation standard pour 7 jours
print("\n[LOG] Etape 2: Generation rotation standard (7 jours)")
date_debut = date.today()
rotations_data = generer_rotation_standard(date_debut, 7)

print(f"  {len(rotations_data)} rotations generees")

# Créer les rotations en base
rotations_creees = 0
for rot_data in rotations_data:
    # Vérifier si existe déjà
    existe = RotationGardien.objects.filter(
        employe_id=rot_data['employe_id'],
        date=rot_data['date']
    ).exists()

    if not existe:
        RotationGardien.objects.create(**rot_data)
        rotations_creees += 1

print(f"  {rotations_creees} nouvelle(s) rotation(s) creee(s) en base")

# Étape 3 : Afficher les rotations par gardien
print("\n[LOG] Etape 3: Rotations par gardien")
for gardien_id in GARDIENS_IDS:
    employe = Employe.objects.get(id=gardien_id)
    rotations = RotationGardien.objects.filter(
        employe_id=gardien_id,
        date__gte=date_debut,
        date__lt=date_debut + timedelta(days=7)
    ).order_by('date')

    print(f"\n  {employe.surnom or employe.nom}:")
    for rot in rotations:
        shift_info = f"{rot.shift_type} ({rot.heure_debut}-{rot.heure_fin})"
        heures = f"{rot.heures_travaillees}h"
        extras = []
        if rot.est_dimanche:
            extras.append("Dimanche")
        if rot.est_jour_ferie:
            extras.append("Ferie")
        if rot.est_extension:
            extras.append("Extension")

        extra_str = f" [{', '.join(extras)}]" if extras else ""
        print(f"    - {rot.date}: {shift_info} - {heures}{extra_str}")

# Étape 4 : Calculer les heures supplémentaires pour le mois courant
print("\n[LOG] Etape 4: Calcul heures supplementaires du mois")
mois_courant = date.today().month
annee_courante = date.today().year

for gardien_id in GARDIENS_IDS:
    employe = Employe.objects.get(id=gardien_id)

    # Calculer les heures
    heures_supp = HeuresSupplementairesGardien.calculer_pour_mois(
        gardien_id, mois_courant, annee_courante
    )

    print(f"\n  {employe.surnom or employe.nom} - {mois_courant}/{annee_courante}:")
    print(f"    - Heures normales: {heures_supp.heures_normales}h")
    print(f"    - Heures supplementaires: {heures_supp.heures_supplementaires}h")
    print(f"    - Heures dimanche: {heures_supp.heures_dimanche}h")
    print(f"    - Heures jours feries: {heures_supp.heures_jours_feries}h")
    print(f"    - Heures extensions: {heures_supp.heures_extensions}h")

# Étape 5 : Statistiques globales
print("\n[LOG] Etape 5: Statistiques globales")
total_rotations = RotationGardien.objects.count()
rotations_dimanche = RotationGardien.objects.filter(est_dimanche=True).count()
rotations_feries = RotationGardien.objects.filter(est_jour_ferie=True).count()
rotations_extensions = RotationGardien.objects.filter(est_extension=True).count()

print(f"  - Total rotations: {total_rotations}")
print(f"  - Rotations dimanche: {rotations_dimanche}")
print(f"  - Rotations jours feries: {rotations_feries}")
print(f"  - Rotations extensions: {rotations_extensions}")

print("\n[OK] Test termine avec succes!")
print("\n" + "="*80)
print("NOTES:")
print("  1. Pour creer un conge avec extension automatique des shifts:")
print("     POST /api/gardiens/creer-conge/")
print("     Body: {employe_id, date_debut, date_fin, motif}")
print("  ")
print("  2. Pour consulter les heures supplementaires:")
print("     GET /api/gardiens/heures-supplementaires/?employe_id=...&mois=...&annee=...")
print("  ")
print("  3. Les shifts etendus (8h-8h) remplacent automatiquement les shifts normaux")
print("     quand un gardien prend un conge.")
print("="*80 + "\n")
