import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.inspections.models import Inspection
from apps.infrastructure.models import EquipementConstitutif
from apps.billing.models import PointEau
from django.contrib.auth.models import User
from django.utils import timezone
import random

# Récupérer des données existantes
equipements = list(EquipementConstitutif.objects.all()[:3])
points_eau = list(PointEau.objects.all()[:3])
users = list(User.objects.all()[:2])

if not equipements and not points_eau:
    print("Aucun équipement ou point d'eau trouvé dans la base de données")
    exit(1)

if not users:
    print("Aucun utilisateur trouvé dans la base de données")
    # Créer un utilisateur test
    user = User.objects.create_user(username='inspecteur_test', password='test123')
    users = [user]
    print(f"Utilisateur test créé: {user.username}")

statuts = ['en_cours', 'terminee', 'validee']
observations_list = [
    "Pression normale, débit stable. RAS.",
    "Fuite détectée au niveau du robinet principal. Réparation nécessaire.",
    "Système de filtration obstrué. Nettoyage effectué sur place.",
    "Pompe électrique fonctionne correctement. Niveau d'eau satisfaisant.",
    "Qualité de l'eau à vérifier. Échantillon prélevé pour analyse."
]

# Créer 5 inspections test
from datetime import timedelta
count = 0
now = timezone.now()
# Générer un timestamp unique pour éviter les collisions
timestamp_suffix = now.strftime('%Y%m%d%H%M%S')

for i in range(5):
    # Alterner entre équipement et point d'eau
    if i % 2 == 0 and equipements:
        obj_inspecte = random.choice(equipements)
        nom_objet = f"Équipement {obj_inspecte.id}"
        inspection = Inspection.objects.create(
            numero_inspection=f"INS-TEST-{timestamp_suffix}-{i+1:03d}",
            equipement=obj_inspecte,
            date_inspection=now - timedelta(days=random.randint(1, 7)),
            inspecteur=random.choice(users),
            statut=random.choice(statuts),
            observations_generales=observations_list[i],
            temperature=round(random.uniform(20.0, 30.0), 2)
        )
    elif points_eau:
        obj_inspecte = random.choice(points_eau)
        nom_objet = f"Point d'eau {obj_inspecte.id}"
        inspection = Inspection.objects.create(
            numero_inspection=f"INS-TEST-{timestamp_suffix}-{i+1:03d}",
            point_eau=obj_inspecte,
            date_inspection=now - timedelta(days=random.randint(1, 7)),
            inspecteur=random.choice(users),
            statut=random.choice(statuts),
            observations_generales=observations_list[i],
            temperature=round(random.uniform(20.0, 30.0), 2)
        )
    else:
        continue

    count += 1
    print(f"Inspection créée: {inspection.numero_inspection} - {nom_objet} - {inspection.statut} - {inspection.date_inspection.strftime('%d/%m/%Y')}")

print(f"\n[OK] {count} inspections de test créées")
print(f"[OK] {Inspection.objects.count()} inspections au total dans la base de données")
