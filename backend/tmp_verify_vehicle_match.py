import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.views_verification_fournisseurs import extraire_infos_carburant, _normalize_matricule
from apps.inventory.models_vehicles import Vehicule
from apps.accounting.models import BaseDiameX

# Fetch vehicles map
vehicules_map = {
    _normalize_matricule(v.immatriculation): v.immatriculation
    for v in Vehicule.objects.all().only('immatriculation')
    if v.immatriculation
}
print(f"Total vehicles in DB with plate: {len(vehicules_map)}")

# Get some recent fuel transactions
entries = BaseDiameX.objects.filter(compte_code__in=['606100', '606107']).order_by('-date_rec')[:50]
matched = 0
total = 0
for entry in entries:
    info = extraire_infos_carburant(entry.description, entry.detail)
    mat_extracted = info.get('matricule_vehicule')
    if mat_extracted:
        total += 1
        mat_norm = _normalize_matricule(mat_extracted)
        if mat_norm in vehicules_map:
            matched += 1
        else:
            print(f"Found plate {mat_norm} but not in DB! Description: {entry.description}")

print(f"Matched {matched}/{total} plates!")
