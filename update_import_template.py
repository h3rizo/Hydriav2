#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour modifier le template import_diamex.html et ajouter Google Drive support
"""

# Lire le template actuel
with open('/home/soakoja/hydria/backend/templates/accounting/import_diamex.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Trouver les lignes à modifier
new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)

    # Ajouter le bouton Google Drive après le bouton Access (ligne ~18)
    if 'Importer depuis Access' in line and '<button onclick="openImportModal()"' in line:
        new_lines.append('            <button onclick="openGoogleDriveModal()" class="btn btn-success">\n')
        new_lines.append('                <i class="fab fa-google-drive mr-2"></i>Importer depuis Google Drive\n')
        new_lines.append('            </button>\n')

    # Ajouter le modal Google Drive et le script avant {% endblock %}
    if line.strip() == '{% endblock %}' and i > 400:  # Dernier endblock
        # Ajouter le modal Google Drive
        with open('/tmp/google_drive_modal.html', 'r', encoding='utf-8') as modal_file:
            new_lines.append('\n')
            new_lines.extend(modal_file.readlines())
            new_lines.append('\n')

        # Ajouter le script
        new_lines.append('<script src="{% static \'js/google_drive_import.js\' %}"></script>\n')
        new_lines.append('\n')

# Écrire le fichier modifié
with open('/home/soakoja/hydria/backend/templates/accounting/import_diamex.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Template modifié avec succès")
print(f"Nombre de lignes original : {len(lines)}")
print(f"Nombre de lignes modifié : {len(new_lines)}")