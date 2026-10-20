#!/usr/bin/env python
"""
Script pour compiler les fichiers .po en .mo avec polib
"""

import polib
from pathlib import Path

# Répertoire de base
BASE_DIR = Path(__file__).resolve().parent
locale_dir = BASE_DIR / 'locale'

# Trouver tous les fichiers .po
po_files = list(locale_dir.rglob('*.po'))

print(f"[INFO] Trouve {len(po_files)} fichier(s) .po")

for po_file in po_files:
    mo_file = po_file.with_suffix('.mo')

    try:
        # Charger le fichier .po
        po = polib.pofile(str(po_file))

        # Compiler en .mo
        po.save_as_mofile(str(mo_file))

        print(f"[OK] {po_file.relative_to(BASE_DIR)} -> {mo_file.name}")

    except Exception as e:
        print(f"[ERROR] Erreur pour {po_file.name}: {e}")

print(f"\n[OK] Compilation terminee ({len(po_files)} fichiers)")
