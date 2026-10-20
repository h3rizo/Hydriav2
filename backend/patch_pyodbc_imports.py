#!/usr/bin/env python3
"""
Script pour rendre les imports pyodbc optionnels
"""
import os
import re

files_to_patch = [
    'apps/accounting/views_verification_autres.py',
    'apps/employees/views_verification_paiements.py',
    'apps/accounting/views_verification_fournisseurs.py',
    'apps/accounting/views_export_access.py',
]

old_pattern = r'^import pyodbc$'
new_code = """try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    pyodbc = None"""

for filepath in files_to_patch:
    full_path = filepath
    if not os.path.exists(full_path):
        print(f"[ERROR] Fichier non trouvé : {full_path}")
        continue

    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Vérifier si déjà patché
    if 'PYODBC_AVAILABLE' in content:
        print(f"[OK] Déjà patché : {filepath}")
        continue

    # Remplacer l'import
    new_content = re.sub(old_pattern, new_code, content, flags=re.MULTILINE)

    if new_content != content:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[OK] Patché : {filepath}")
    else:
        print(f"[WARNING] Aucun changement : {filepath}")

print("\n[OK] Patch terminé !")
