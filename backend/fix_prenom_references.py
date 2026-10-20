#!/usr/bin/env python
"""
Script pour remplacer toutes les références à employe.prenom par employe.surnom avec fallback sur employe.nom
"""
import os
import re
from pathlib import Path

def fix_prenom_in_file(filepath):
    """Corrige les références à .prenom dans un fichier template"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    changes_made = []

    # Pattern 1: employe.surnom|default:employe.prenom > employe.surnom|default:employe.nom
    pattern1 = r'employe\.surnom\|default:employe\.prenom'
    replacement1 = r'employe.surnom|default:employe.nom'
    if re.search(pattern1, content):
        content = re.sub(pattern1, replacement1, content)
        count = len(re.findall(pattern1, original_content))
        changes_made.append(f"  - {count}x: employe.surnom|default:prenom > surnom|default:nom")

    # Pattern 2: employe.prenom seul (sans default avant) > employe.surnom|default:employe.nom
    pattern2 = r'(?<!default:)employe\.prenom(?!\|)'
    replacement2 = r'employe.surnom|default:employe.nom'
    if re.search(pattern2, content):
        content = re.sub(pattern2, replacement2, content)
        count = len(re.findall(pattern2, original_content))
        changes_made.append(f"  - {count}x: employe.prenom > employe.surnom|default:nom")

    # Pattern 3: Gerer les cas user.employe.prenom
    pattern3 = r'user\.employe\.surnom\|default:user\.employe\.prenom'
    replacement3 = r'user.employe.surnom|default:user.employe.nom|default:user.username'
    if re.search(pattern3, content):
        content = re.sub(pattern3, replacement3, content)
        count = len(re.findall(pattern3, original_content))
        changes_made.append(f"  - {count}x: user.employe.surnom|default:prenom > surnom|default:nom|default:username")

    pattern4 = r'(?<!default:)user\.employe\.prenom(?!\|)'
    replacement4 = r'user.employe.surnom|default:user.employe.nom|default:user.username'
    if re.search(pattern4, content):
        content = re.sub(pattern4, replacement4, content)
        count = len(re.findall(pattern4, original_content))
        changes_made.append(f"  - {count}x: user.employe.prenom > user.employe.surnom|default:nom|default:username")

    # Pattern 5: Proteger les acces a employe.nom dans les templates (acces direct qui peut etre None)
    # Rechercher employe.nom qui n'est pas dans un contexte {% if employe %}
    pattern5 = r'\.employe\.nom(?!\|)(?!}})'
    if re.search(pattern5, content):
        # Ce pattern necessite une correction manuelle car il faut verifier le contexte
        changes_made.append(f"  - WARNING: Acces direct a .employe.nom detecte - verification manuelle requise")

    # Sauvegarder si des changements ont été faits
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return changes_made

    return None

def main():
    templates_dir = Path('templates')
    files_changed = 0
    total_changes = 0

    print("Recherche et correction des references a .prenom...")
    print("=" * 70)

    for html_file in templates_dir.rglob('*.html'):
        changes = fix_prenom_in_file(html_file)
        if changes:
            files_changed += 1
            total_changes += len(changes)
            print(f"\n[OK] {html_file}")
            for change in changes:
                print(change)

    print("\n" + "=" * 70)
    print(f"Resume: {files_changed} fichier(s) modifie(s), {total_changes} type(s) de changement(s)")

if __name__ == '__main__':
    main()
