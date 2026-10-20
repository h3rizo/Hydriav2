import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import BaseDiameX
from apps.employees.models import EmployeBaseDiameX

# Récupérer une entrée avec scan
entry = BaseDiameX.objects.filter(scan__icontains='EHA-Soakoja-Fenerive').first()
print(f'Scan original: {entry.scan}')
print(f'Prog: {entry.prog}')

# Récupérer le chemin_base
employe_base = EmployeBaseDiameX.objects.filter(base_diamex=entry.prog).first()
if employe_base:
    chemin_base = employe_base.chemin_base_diamex or ''
    print(f'Chemin base: {chemin_base}')

    # Nettoyer le scan
    scan_clean = entry.scan
    if scan_clean.startswith('./') or scan_clean.startswith('.\'):
        scan_clean = scan_clean[2:]
    elif scan_clean.startswith('.'):
        scan_clean = scan_clean[1:]

    print(f'Scan nettoye: {scan_clean}')

    # Construire le chemin complet
    if not chemin_base.endswith(os.sep):
        scan_path = chemin_base + os.sep + scan_clean
    else:
        scan_path = chemin_base + scan_clean

    print(f'Chemin complet: {scan_path}')
    print(f'Fichier existe: {os.path.exists(scan_path)}')
else:
    print('EmployeBaseDiameX non trouve')
