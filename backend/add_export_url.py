import re

file_path = 'apps/employees/urls.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Ajouter l'import du nouveau fichier après views_cnaps_fmfp
if 'views_cnaps_fmfp_export' not in content:
    old_import = 'from . import views_cnaps_fmfp'
    new_import = '''from . import views_cnaps_fmfp
from . import views_cnaps_fmfp_export'''
    content = content.replace(old_import, new_import)

# Ajouter la route après la route de génération de facture
if 'api_marquer_cnaps_fmfp_imprime' not in content:
    old_route = "path('paiement-cnaps-fmfp/<uuid:paiement_id>/facture/', views_cnaps_fmfp.generer_facture_cnaps_fmfp, name='generer_facture_cnaps_fmfp'),"
    new_route = '''path('paiement-cnaps-fmfp/<uuid:paiement_id>/facture/', views_cnaps_fmfp.generer_facture_cnaps_fmfp, name='generer_facture_cnaps_fmfp'),
    path('api/paiement-cnaps-fmfp/<uuid:paiement_id>/marquer-imprime/', views_cnaps_fmfp_export.api_marquer_cnaps_fmfp_imprime, name='api_marquer_cnaps_fmfp_imprime'),'''
    content = content.replace(old_route, new_route)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Import et route ajoutés pour l'export CNaPS/FMFP")
