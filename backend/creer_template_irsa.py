"""
Script pour créer un template Excel propre pour les factures IRSA
À exécuter : python creer_template_irsa.py
"""
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

# Créer un nouveau classeur
wb = Workbook()

# Supprimer la feuille par défaut
wb.remove(wb.active)

# ========================================
# ONGLET 1 : DIAME IRSA
# ========================================
ws1 = wb.create_sheet("DIAME IRSA")

# En-tête ligne 1
ws1['A1'] = "Nom de l'organisation"
ws1['B1'] = "[NOM_ORGANISATION]"  # À remplir par le code
ws1['C1'] = "Payé en"
ws1['D1'] = "[DATE_PAIEMENT]"  # À remplir par le code

# En-tête ligne 2 avec bordure épaisse étendue jusqu'à D
ws1['A2'] = "IRSA"
ws1.merge_cells('B2:D2')
ws1['B2'] = "Concernant les salaires du mois : [MOIS_ANNEE]"

# Bordure épaisse (1) pour la cellule B2:D2
thick_border = Border(
    left=Side(style='thick', color='000000'),
    right=Side(style='thick', color='000000'),
    top=Side(style='thick', color='000000'),
    bottom=Side(style='thick', color='000000')
)
ws1['B2'].border = thick_border
ws1['C2'].border = thick_border
ws1['D2'].border = thick_border

# Ligne vide 3
# Ligne d'en-têtes de colonnes 4 (5 colonnes au lieu de 6, sans Date de paiement)
ws1['A4'] = "Noms et prénoms"
ws1['B4'] = "Salaire brut total"
ws1['C4'] = "Base imposable"
ws1['D4'] = "IRSA"

# Style des en-têtes avec bordures
header_font = Font(bold=True)
header_fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
thin_border = Border(
    left=Side(style='thin', color='000000'),
    right=Side(style='thin', color='000000'),
    top=Side(style='thin', color='000000'),
    bottom=Side(style='thin', color='000000')
)

for cell in ['A4', 'B4', 'C4', 'D4']:
    ws1[cell].font = header_font
    ws1[cell].fill = header_fill
    ws1[cell].border = thin_border
    ws1[cell].alignment = Alignment(horizontal='center', vertical='center')

# Les données seront insérées à partir de la ligne 5 par le code Python

# Ajuster les largeurs de colonnes
ws1.column_dimensions['A'].width = 45
ws1.column_dimensions['B'].width = 20
ws1.column_dimensions['C'].width = 20
ws1.column_dimensions['D'].width = 15

# ========================================
# ONGLET 2 : D.N IRSA
# ========================================
ws2 = wb.create_sheet("D.N IRSA")

# Titre ligne 1
ws2.merge_cells('A1:I1')
ws2['A1'] = "DECLARATION NOMINATIVE DES IMPOTS SUR LES REVENUS SALARIAUX ET ASSIMILES"
ws2['A1'].font = Font(bold=True, size=14)
ws2['A1'].alignment = Alignment(horizontal='center')

# Ligne 2 vide (effacée comme demandé)

# Ligne 3 (en-têtes de colonnes - ligne 4 supprimée)
ws2['A3'] = "Noms et prénoms"
ws2['B3'] = "Date d'embauche"
ws2['C3'] = "Date de débauchage"
ws2['D3'] = "Fonction"
ws2['E3'] = "Progr."
ws2['F3'] = "Classif. Prof."
ws2['G3'] = "Salaire brut total"
ws2['H3'] = "Base imposable"
ws2['I3'] = "IRSA"

# Style des en-têtes (seulement ligne 3 maintenant)
for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']:
    cell = f"{col}3"
    ws2[cell].font = header_font
    ws2[cell].fill = header_fill
    ws2[cell].border = thin_border
    ws2[cell].alignment = Alignment(horizontal='center', vertical='center')

# Les données seront insérées à partir de la ligne 4 par le code Python (ligne 4 supprimée)

# Ajuster les largeurs de colonnes
ws2.column_dimensions['A'].width = 35
ws2.column_dimensions['B'].width = 18  # Élargi pour "Date d'embauche" + DD/MM/YYYY
ws2.column_dimensions['C'].width = 18  # Élargi pour "Date de débauchage" + DD/MM/YYYY
ws2.column_dimensions['D'].width = 40
ws2.column_dimensions['E'].width = 15  # Élargi pour "Progr."
ws2.column_dimensions['F'].width = 12
ws2.column_dimensions['G'].width = 18
ws2.column_dimensions['H'].width = 18
ws2.column_dimensions['I'].width = 15

# ========================================
# ONGLET 3 : bordereau IRSA
# ========================================
ws3 = wb.create_sheet("bordereau IRSA")

# Titre ligne 1
ws3.merge_cells('A1:D1')
ws3['A1'] = "REPOBLIKAN'I MADAGASIKARA"
ws3['A1'].font = Font(bold=True, size=12)
ws3['A1'].alignment = Alignment(horizontal='center')

ws3.merge_cells('E1:I1')
ws3['E1'] = "HETRA AMIN'NY KARAMA SY NY TOA AZY"
ws3['E1'].font = Font(bold=True, size=12)
ws3['E1'].alignment = Alignment(horizontal='center')

# Ligne 2
ws3.merge_cells('E2:I2')
ws3['E2'] = "(Andininy faha 01 16 56 amin'ny fehezan-dalana ankapobeny mifehy ny hetra)"
ws3['E2'].alignment = Alignment(horizontal='center')

# Ligne 3
ws3.merge_cells('A3:D3')
ws3['A3'] = "SAMPAN-DRAHARAHA MOMBA NY LAHASA MIKASIKA NY HETRA"
ws3['A3'].alignment = Alignment(horizontal='center')

ws3.merge_cells('E3:I3')
ws3['E3'] = "IMPÔT SUR LES REVENUS SALARIES ET ASSIMILES"
ws3['E3'].font = Font(bold=True)
ws3['E3'].alignment = Alignment(horizontal='center')

# Ligne 4
ws3.merge_cells('E4:I4')
ws3['E4'] = "(Art 01.16.56 du code général des impôts)"
ws3['E4'].alignment = Alignment(horizontal='center')

# Ligne 6
ws3.merge_cells('E6:I6')
ws3['E6'] = "TARATASY FANDROTSAHAM-BOLA"
ws3['E6'].font = Font(bold=True, size=12)
ws3['E6'].alignment = Alignment(horizontal='center')

# Ligne 7
ws3['A7'] = "FARITANY"
ws3.merge_cells('E7:I7')
ws3['E7'] = "Ho fenoin'ny mpampiasa na ny vondrona mpandoa vola"

# Ligne 8
ws3['B8'] = "[PROVINCE]"  # À remplir
ws3.merge_cells('E8:I8')
ws3['E8'] = "BORDEREAU DE VERSEMENT"
ws3['E8'].font = Font(bold=True, size=12)
ws3['E8'].alignment = Alignment(horizontal='center')

# Ligne 9
ws3['A9'] = "FIVONDRONAM-POKONTANY"
ws3.merge_cells('E9:I9')
ws3['E9'] = "A établir en 4 exemplaires par l'employeur"

# Ligne 10
ws3['B10'] = "[DISTRICT]"  # À remplir
ws3['F10'] = "TAONA:"
ws3['G10'] = "[ANNEE]"  # À remplir

# Ligne 12 - En-têtes
ws3['A12'] = "Désignation"
ws3['B12'] = "Base"
ws3['C12'] = "Montant"

for cell in ['A12', 'B12', 'C12']:
    ws3[cell].font = header_font
    ws3[cell].fill = header_fill

# Ligne 13
ws3['A13'] = "IRSA"
ws3['B13'] = "[BASE_IMPOSABLE_TOTALE]"
ws3['C13'] = "[IRSA_TOTAL]"

# Ligne 15
ws3['A15'] = "Total à payer"
ws3['C15'] = "[IRSA_TOTAL]"
ws3['A15'].font = Font(bold=True)
ws3['C15'].font = Font(bold=True)

# Ajuster les largeurs de colonnes
ws3.column_dimensions['A'].width = 30
ws3.column_dimensions['B'].width = 20
ws3.column_dimensions['C'].width = 20

# Sauvegarder le fichier
output_path = "modèle facture IRSA PROPRE.xlsx"
wb.save(output_path)
print(f"[OK] Template cree avec succes : {output_path}")
print("\nStructure des onglets :")
print("1. DIAME IRSA : Liste des employes par fonction")
print("2. D.N IRSA : Declaration nominative detaillee")
print("3. bordereau IRSA : Bordereau de versement")
print("\nLes placeholders a remplir par le code :")
print("- [NOM_ORGANISATION]")
print("- [DATE_PAIEMENT]")
print("- [MOIS_ANNEE]")
print("- [MOIS] (nom du mois)")
print("- [PROVINCE], [DISTRICT], [ANNEE]")
print("- [BASE_IMPOSABLE_TOTALE], [IRSA_TOTAL]")
