"""
Script de test pour reproduire l'erreur de création de planning
"""
import os
import django
import sys

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.planning.models import Planning, Activite
from apps.organization.models import Ouvrage
from apps.employees.models import Employe
from datetime import datetime
import pytz

# Test de création de planning
try:
    print("=== Test de création de planning ===")

    # 1. Récupérer une activité de réparation
    activite = Activite.objects.filter(est_corrective=True).select_related('type_activite').first()
    if not activite:
        print("[ERREUR] Aucune activite corrective trouvee")
        sys.exit(1)

    print(f"[OK] Activite trouvee: {activite.nom}")
    print(f"  Type activite: {activite.type_activite}")
    print(f"  Type activite ID: {activite.type_activite.id if activite.type_activite else None}")

    # 2. Récupérer un ouvrage
    ouvrage = Ouvrage.objects.first()
    if not ouvrage:
        print("[ERREUR] Aucun ouvrage trouve")
        sys.exit(1)

    print(f"[OK] Ouvrage trouve: {ouvrage.nom_ouvrage}")

    # 3. Récupérer un employé (optionnel)
    employe = Employe.objects.filter(salarie=True).select_related('poste').first()
    if employe:
        print(f"[OK] Employe trouve: {employe.surnom}")
        if hasattr(employe, 'poste') and employe.poste:
            print(f"  Poste: {employe.poste.nom_poste}")

    # 4. Date
    tz_madagascar = pytz.timezone('Indian/Antananarivo')
    date_obj = tz_madagascar.localize(datetime(2025, 11, 25, 10, 0))
    print(f"[OK] Date: {date_obj}")

    # 5. Créer le planning
    print("\n=== Création du planning ===")
    print(f"  ouvrage: {ouvrage}")
    print(f"  activite: {activite}")
    print(f"  type_activite_id: {activite.type_activite.id if activite.type_activite else None}")
    print(f"  date: {date_obj}")
    print(f"  employe: {employe}")

    planning = Planning.objects.create(
        ouvrage=ouvrage,
        activite=activite,
        type_activite_id=activite.type_activite.id if activite.type_activite else None,
        date=date_obj,
        employe=employe,
        remarque='Test de création depuis script',
        suiteadonner='À faire',
        estvalide=False
    )

    print(f"\n[SUCCES] Planning cree avec succes!")
    print(f"  ID: {planning.id}")
    print(f"  Date: {planning.date}")
    print(f"  Activite: {planning.activite.nom}")

except Exception as e:
    import traceback
    print(f"\n[ERREUR]: {str(e)}")
    print("\n=== TRACEBACK COMPLET ===")
    print(traceback.format_exc())
    sys.exit(1)
