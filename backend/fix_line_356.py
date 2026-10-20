"""
Script pour corriger la syntaxe JavaScript ligne 356
"""
import re

template_file = r'c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\templates\employees\paiements_iri_liste.html'

# Lire le contenu
with open(template_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern incorrect: onclick="viewDetail(' + p.id + ')"
# Correction: onclick="viewDetail('${p.id}')"

# Rechercher et remplacer
old_pattern = r'onclick="viewDetail\(\' \+ p\.id \+ \'\)"'
new_pattern = r'onclick="viewDetail(\'${p.id}\')"'

if re.search(old_pattern, content):
    content = re.sub(old_pattern, new_pattern, content)
    print('[OK] Pattern trouvé et corrigé')
else:
    print('[INFO] Pattern exact non trouvé, tentative avec recherche plus large...')

    # Recherche plus large
    if "viewDetail(' + p.id + ')" in content:
        content = content.replace("viewDetail(' + p.id + ')", "viewDetail('${p.id}')")
        print('[OK] Correction appliquée avec recherche large')
    else:
        print('[ERROR] Pattern introuvable dans le fichier')
        # Afficher les lignes contenant viewDetail pour diagnostic
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if 'viewDetail' in line and i >= 350 and i <= 360:
                print(f'Ligne {i}: {line[:100]}...')

# Écrire le contenu corrigé
with open(template_file, 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] Fichier mis à jour')
