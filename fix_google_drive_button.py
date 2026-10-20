#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script corrigé pour ajouter le bouton Google Drive au bon endroit
"""

# Lire le template actuel
with open('/home/soakoja/hydria/backend/templates/accounting/import_diamex.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Trouver la ligne avec le bouton Access et insérer après
new_lines = []
button_inserted = False

for i, line in enumerate(lines):
    new_lines.append(line)

    # Chercher la ligne qui ferme le bouton Access (ligne 19)
    # On détecte: ligne qui contient "</button>" ET la ligne précédente contient "Importer depuis Access"
    if '</button>' in line and not button_inserted:
        # Vérifier si la ligne précédente contient "Importer depuis Access"
        if i > 0 and 'Importer depuis Access' in lines[i-1]:
            # Insérer le bouton Google Drive juste après
            new_lines.append('            <button onclick="openGoogleDriveModal()" class="btn btn-success">\n')
            new_lines.append('                <i class="fab fa-google-drive mr-2"></i>Importer depuis Google Drive\n')
            new_lines.append('            </button>\n')
            button_inserted = True
            print(f"✓ Bouton Google Drive inséré après la ligne {i+1}")

# Écrire le fichier modifié
with open('/home/soakoja/hydria/backend/templates/accounting/import_diamex.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

if button_inserted:
    print("✓ Template modifié avec succès")
    print(f"Nombre de lignes: {len(lines)} → {len(new_lines)}")
else:
    print("✗ ERREUR: Bouton non inséré - pattern non trouvé")