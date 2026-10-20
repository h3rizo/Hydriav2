import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import BaseDiameX

print("=== TEST CHEMIN_BASE DIRECT ===\n")

# Vérifier les transactions DiameX pour janvier 2025
print("1. Transactions DiameX 707401 - Janvier 2025 avec scan:")
diamex_jan = BaseDiameX.objects.filter(
    compte_code='707401',
    date_rec__year=2025,
    date_rec__month=1
).exclude(scan__isnull=True).exclude(scan='')

print(f"   Nombre avec scan: {diamex_jan.count()}")

if diamex_jan.count() > 0:
    print("\n   Premiere transaction:")
    entry = diamex_jan.first()
    print(f"   - Date: {entry.date_rec}")
    print(f"     Description: {entry.description[:80] if entry.description else 'N/A'}")
    print(f"     Prog: {entry.prog}")
    print(f"     Scan relatif: {entry.scan}")
    print(f"     Chemin base: {entry.chemin_base or 'VIDE'}")

    if entry.chemin_base:
        # Construire le chemin complet
        scan_clean = entry.scan
        if scan_clean.startswith('./') or scan_clean.startswith('.\\\\'):
            scan_clean = scan_clean[2:]
        elif scan_clean.startswith('.'):
            scan_clean = scan_clean[1:]

        chemin_base = entry.chemin_base
        if not chemin_base.endswith(os.sep):
            scan_path = chemin_base + os.sep + scan_clean
        else:
            scan_path = chemin_base + scan_clean

        print(f"     Scan nettoye: {scan_clean}")
        print(f"     Chemin complet: {scan_path}")
        print(f"     Fichier existe: {os.path.exists(scan_path)}")
    else:
        print("     [WARNING] chemin_base est vide, impossible de construire le chemin complet")
