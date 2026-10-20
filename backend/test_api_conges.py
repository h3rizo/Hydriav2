#!/usr/bin/env python
"""Script de test pour l'API de modification des congés"""

import os
import django
import json
from datetime import datetime

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import Employe
from apps.planning.models import Planning, Activite
import pytz

# Récupérer un employé pour test
employe = Employe.objects.first()
if not employe:
    print("Aucun employé trouvé dans la base")
    exit(1)

print(f"Test avec employé: {employe.nom} (ID: {employe.id})")

# Simuler la requête
data = {
    'employe_id': str(employe.id),
    'date_debut': '2025-01-15',
    'date_fin': '2025-01-17',
    'type_conge': 'conge',
    'motif': 'Test modification'
}

print(f"\nDonnées envoyées: {json.dumps(data, indent=2)}")

# Tenter l'opération
try:
    tz_madagascar = pytz.timezone('Indian/Antananarivo')
    date_debut_obj = datetime.strptime(data['date_debut'], '%Y-%m-%d').date()
    date_fin_obj = datetime.strptime(data['date_fin'], '%Y-%m-%d').date()

    print(f"\nDate début: {date_debut_obj}")
    print(f"Date fin: {date_fin_obj}")

    # Récupérer l'activité
    activite_nom = 'Congé'
    try:
        activite = Activite.objects.get(nom=activite_nom)
        print(f"Activité trouvée: {activite.nom} (ID: {activite.id})")
    except Activite.DoesNotExist:
        print(f"Activité '{activite_nom}' non trouvée, création...")
        activite = Activite.objects.create(
            nom=activite_nom,
            description=f'Activité {activite_nom}'
        )
        print(f"Activité créée: {activite.nom} (ID: {activite.id})")

    # Supprimer les anciens plannings
    date_start_aware = tz_madagascar.localize(datetime.combine(date_debut_obj, datetime.min.time()))
    date_end_aware = tz_madagascar.localize(datetime.combine(date_fin_obj, datetime.max.time()))

    print(f"\nSuppression plannings entre {date_start_aware} et {date_end_aware}")

    deleted_count = Planning.objects.filter(
        employe=employe,
        date__gte=date_start_aware,
        date__lte=date_end_aware,
        activite__nom__in=['Congé', 'Permission (demi-journée)', 'Récupération', 'Repos']
    ).delete()

    print(f"Plannings supprimés: {deleted_count}")

    # Créer les nouveaux plannings
    from datetime import timedelta
    current_date = date_debut_obj
    plannings_crees = []

    while current_date <= date_fin_obj:
        date_planning = tz_madagascar.localize(datetime.combine(current_date, datetime.min.time()))

        planning = Planning.objects.create(
            employe=employe,
            date=date_planning,
            activite=activite,
            estvalide=False
        )

        plannings_crees.append(str(current_date))
        print(f"Planning créé: {planning.date} - {planning.activite.nom}")

        current_date += timedelta(days=1)

    print(f"\n[OK] Succes! {len(plannings_crees)} planning(s) cree(s)")

except Exception as e:
    import traceback
    print(f"\n[ERROR] Erreur:")
    traceback.print_exc()
