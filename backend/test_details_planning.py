#!/usr/bin/env python
"""Script de test pour l'API de détails de planning"""

import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import Employe
from apps.planning.models import Planning, Activite
from apps.organization.models import Ouvrage
import pytz
from datetime import datetime

# Récupérer un employé
employe = Employe.objects.first()
if not employe:
    print("Aucun employé trouvé")
    exit(1)

# Récupérer ou créer une activité
activite, _ = Activite.objects.get_or_create(
    nom='Réparation fuite',
    defaults={'description': 'Réparation de fuite'}
)

# Récupérer un ouvrage
ouvrage = Ouvrage.objects.first()

# Créer un planning de test
tz_madagascar = pytz.timezone('Indian/Antananarivo')
date_test = tz_madagascar.localize(datetime(2025, 1, 20, 0, 0))

planning, created = Planning.objects.get_or_create(
    employe=employe,
    date=date_test,
    defaults={
        'activite': activite,
        'ouvrage': ouvrage,
        'remarques': 'Test pour vérification API',
        'estvalide': True
    }
)

if created:
    print(f"Planning créé:")
else:
    print(f"Planning existant:")

print(f"  - Employé: {employe.surnom or employe.nom}")
print(f"  - Date: {planning.date}")
print(f"  - Activité: {planning.activite.nom if planning.activite else '-'}")
print(f"  - Ouvrage: {planning.ouvrage.nom_ouvrage if planning.ouvrage else '-'}")
print(f"  - Remarques: {planning.remarques or '-'}")
print(f"  - Validé: {planning.estvalide}")

print(f"\nPour tester l'API, utilisez:")
print(f"GET /employes/api/details-planning/{employe.id}/2025-01-20/")
