"""
Script temporaire pour ajouter les routes IRI facture
"""
import os

urls_file = r'c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\apps\employees\urls.py'

# Lire le contenu
with open(urls_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Ajouter l'import
if 'from . import views_iri_facture' not in content:
    content = content.replace(
        'from . import views_iri\n',
        'from . import views_iri\nfrom . import views_iri_facture\n'
    )

# Ajouter les routes
routes_to_add = """    path('api/paiement-iri/<uuid:paiement_id>/generer-facture/', views_iri_facture.generer_facture_iri, name='api_generer_facture_iri'),
    path('api/paiement-iri/<uuid:paiement_id>/telecharger-facture/', views_iri_facture.telecharger_facture_iri, name='telecharger_facture_iri'),
"""

if 'api_generer_facture_iri' not in content:
    # Trouver la ligne avec api_supprimer_paiement_iri
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        new_lines.append(line)
        if "path('api/paiement-iri/<uuid:paiement_id>/supprimer/'" in line and 'api_supprimer_paiement_iri' in line:
            # Ajouter les nouvelles routes après cette ligne
            new_lines.append(routes_to_add.rstrip())

    content = '\n'.join(new_lines)

# Écrire le contenu modifié
with open(urls_file, 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] Routes IRI facture ajoutées')
