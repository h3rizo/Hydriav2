import re

file_path = 'apps/employees/views_cnaps_fmfp.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Ajouter un print debug juste après le try
old_code = '''def generer_facture_cnaps_fmfp(request, paiement_id):
    """Génère la facture Excel CNaPS/FMFP selon le modèle"""
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import Font, Alignment, Border, Side
        from django.conf import settings

        paiement = PaiementCNaPSFMFP.objects.select_related('organisation').get(id=paiement_id)'''

new_code = '''def generer_facture_cnaps_fmfp(request, paiement_id):
    """Génère la facture Excel CNaPS/FMFP selon le modèle"""
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import Font, Alignment, Border, Side
        from django.conf import settings

        # DEBUG
        print(f"[DEBUG generer_facture] paiement_id recu: {paiement_id} (type: {type(paiement_id)})")
        
        paiement = PaiementCNaPSFMFP.objects.select_related('organisation').get(id=paiement_id)
        print(f"[DEBUG generer_facture] Paiement trouve: {paiement}")'''

content = content.replace(old_code, new_code)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Debug prints ajoutes dans generer_facture_cnaps_fmfp")
