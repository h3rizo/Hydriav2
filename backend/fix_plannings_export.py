#!/usr/bin/env python3
# Script pour corriger l'indentation dans views.py

with open('apps/planning/views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# La ligne 1994 doit être désindentée (retirer 4 espaces au début)
# Ligne 1994 : "    for planning in plannings_display:" -> "for planning in plannings_display:"
if len(lines) >= 1994:
    line_1994 = lines[1993]  # Index 1993 pour ligne 1994
    if line_1994.startswith('    for planning in plannings_display:'):
        # Désindenter en retirant 4 espaces
        lines[1993] = line_1994[4:]
        print("Ligne 1994 corrigée : indentation réduite")
    else:
        print(f"Ligne 1994 actuelle : {repr(line_1994)}")

# Écrire le fichier corrigé
with open('apps/planning/views.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fichier corrigé avec succès")
