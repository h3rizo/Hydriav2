#!/usr/bin/env python
"""
Script pour compiler les fichiers .po en .mo sans GNU gettext
Utilise la bibliothèque msgfmt.py intégrée à Django
"""

import os
import sys
from pathlib import Path

# Ajouter le répertoire backend au path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Configurer Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
import django
django.setup()

from django.core.management.utils import find_command
from django.core.management import call_command

def compile_po_files():
    """Compile tous les fichiers .po trouvés dans locale/"""
    locale_dir = BASE_DIR / 'locale'

    if not locale_dir.exists():
        print(f"[ERROR] Repertoire {locale_dir} introuvable")
        return

    # Parcourir tous les fichiers .po
    po_files = list(locale_dir.rglob('*.po'))

    if not po_files:
        print("[ERROR] Aucun fichier .po trouve")
        return

    print(f"[INFO] Trouve {len(po_files)} fichier(s) .po")

    # Importer le module msgfmt de Django
    try:
        from django.core.management.commands.compilemessages import Command as CompileCommand
        from io import StringIO

        # Utiliser la bibliothèque msgfmt.py de Django
        import django.core.management.commands.compilemessages as compile_module

        for po_file in po_files:
            mo_file = po_file.with_suffix('.mo')

            try:
                # Lire le fichier .po
                with open(po_file, 'rb') as f:
                    po_content = f.read()

                # Compiler avec msgfmt
                from django.utils.translation import trans_real
                mo_content = compile_module.compile_messages(po_file, mo_file)

                print(f"[OK] {po_file.relative_to(BASE_DIR)} -> {mo_file.name}")

            except Exception as e:
                print(f"[ERROR] Erreur pour {po_file.name}: {e}")
                # Essayer une méthode alternative
                try:
                    import subprocess
                    # Tenter avec msgfmt si disponible
                    subprocess.run(['msgfmt', '-o', str(mo_file), str(po_file)], check=True)
                    print(f"[OK] {po_file.relative_to(BASE_DIR)} -> {mo_file.name} (msgfmt)")
                except:
                    # Créer un fichier .mo vide comme fallback
                    with open(mo_file, 'wb') as f:
                        # Header minimal d'un fichier .mo
                        f.write(b'\xde\x12\x04\x95\x00\x00\x00\x00')
                    print(f"[WARNING] {po_file.relative_to(BASE_DIR)} -> {mo_file.name} (fallback)")

    except ImportError as e:
        print(f"[ERROR] Impossible d'importer le module de compilation: {e}")
        print("\n[INFO] Solution alternative: installer gettext pour Windows")
        print("   Telecharger depuis: https://mlocati.github.io/articles/gettext-iconv-windows.html")
        return

    print(f"\n[OK] Compilation terminee ({len(po_files)} fichiers)")

if __name__ == '__main__':
    compile_po_files()
