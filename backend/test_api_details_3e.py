import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import BaseDiameX
from apps.employees.models import EmployeBaseDiameX
from apps.billing.models import Releve
from datetime import datetime
from dateutil.relativedelta import relativedelta

print("=== TEST API DETAILS 3E - JANVIER 2025 ===\n")

# 1. Vérifier les transactions DiameX pour janvier 2025
print("1. Transactions DiameX 707401 - Janvier 2025:")
diamex_jan = BaseDiameX.objects.filter(
    compte_code='707401',
    date_rec__year=2025,
    date_rec__month=1
)
print(f"   Nombre: {diamex_jan.count()}")

if diamex_jan.count() > 0:
    print("\n   Première transaction avec scan:")
    for entry in diamex_jan:
        if entry.scan:
            print(f"   - Date: {entry.date_rec}")
            print(f"     Description: {entry.description[:80] if entry.description else 'N/A'}")
            print(f"     Montant IN: {entry.montant_in}")
            print(f"     Prog: {entry.prog}")
            print(f"     Scan relatif: {entry.scan}")

            # Récupérer le chemin_base
            employe_base = EmployeBaseDiameX.objects.filter(base_diamex=entry.prog).first()
            if employe_base:
                chemin_base = employe_base.chemin_base_diamex or ''
                print(f"     Chemin base: {chemin_base}")

                # Nettoyer le scan
                scan_clean = entry.scan
                if scan_clean.startswith('./') or scan_clean.startswith('.\\'):
                    scan_clean = scan_clean[2:]
                elif scan_clean.startswith('.'):
                    scan_clean = scan_clean[1:]

                print(f"     Scan nettoyé: {scan_clean}")

                # Construire le chemin complet
                if not chemin_base.endswith(os.sep):
                    scan_path = chemin_base + os.sep + scan_clean
                else:
                    scan_path = chemin_base + scan_clean

                print(f"     Chemin complet: {scan_path}")
                print(f"     Fichier existe: {os.path.exists(scan_path)}")
            else:
                print(f"     EmployeBaseDiameX non trouvé pour prog={entry.prog}")

            print()
            break  # Afficher seulement la première

# 2. Vérifier les relevés de DÉCEMBRE 2024 (car janvier 2025 = décembre 2024 + 1 mois)
print("\n2. Relevés avec montant - Décembre 2024 (pour facturation janvier 2025):")

# Simuler la logique de l'API
annee = 2025
mois = 1
date_facturation = datetime(annee, mois, 1)
date_releve = date_facturation - relativedelta(months=1)

print(f"   Date facturation: {date_facturation.strftime('%Y-%m-%d')}")
print(f"   Date relevé recherchée: {date_releve.strftime('%Y-%m-%d')}")

releves_dec = Releve.objects.filter(
    montant__isnull=False,
    montant__gt=0,
    point_eau__ouvrage__isnull=False,
    datereleve__year=date_releve.year,
    datereleve__month=date_releve.month
).select_related('point_eau', 'point_eau__ouvrage')

print(f"   Nombre de relevés trouvés: {releves_dec.count()}")

if releves_dec.count() > 0:
    print("\n   Premier relevé:")
    r = releves_dec.first()
    print(f"   - Date relevé: {r.datereleve}")
    print(f"     Ouvrage: {r.point_eau.ouvrage.nom_ouvrage if r.point_eau and r.point_eau.ouvrage else 'N/A'}")
    print(f"     Montant: {r.montant}")
