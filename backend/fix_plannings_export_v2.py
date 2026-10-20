#!/usr/bin/env python3
# Script pour corriger l'indentation et la logique dans views.py

with open('apps/planning/views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Ligne 1994 : doit être indentée à 4 espaces (même niveau que les lignes 2001-2005)
if len(lines) >= 1994:
    line_1994 = lines[1993]  # Index 1993 pour ligne 1994
    if line_1994.strip().startswith('for planning in plannings_display:'):
        # Ajouter 4 espaces d'indentation
        lines[1993] = '    ' + line_1994.lstrip()
        print("Ligne 1994 corrigée : indentation ajoutée (4 espaces)")

# Écrire le fichier corrigé
with open('apps/planning/views.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fichier corrigé avec succès")
