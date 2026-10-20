"""
Script pour ajouter facture_generee dans l'API
"""
import os

views_file = r'c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\apps\employees\views_iri.py'

# Lire le contenu
with open(views_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Rechercher la ligne avec 'statut': p.statut, dans api_paiements_iri_list
old_block = """            'statut': p.statut,
        })"""

new_block = """            'statut': p.statut,
            'facture_generee': p.facture_generee,
        })"""

if old_block in content and "'facture_generee'" not in content:
    content = content.replace(old_block, new_block)
    print('[OK] Champ facture_generee ajouté à l\'API')
else:
    print('[INFO] Déjà à jour ou pattern non trouvé')

# Écrire le contenu modifié
with open(views_file, 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] views_iri.py mis à jour')
