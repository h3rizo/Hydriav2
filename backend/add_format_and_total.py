import re

file_path = 'apps/employees/views_cnaps_fmfp.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Trouver la section après la boucle for detail in details et avant ONGLET 2
old_code = '''            current_row += 1

        # ========================================
        # ONGLET 2 : EMPLOYEUR
        # ========================================'''

new_code = '''            # Appliquer format nombre avec séparateurs de milliers
            for col in [3, 4, 5, 6, 7, 8, 9, 10]:
                cell = ws_diame.cell(row=current_row, column=col)
                cell.number_format = '#,##0.00'
            
            current_row += 1

        # Ajouter ligne TOTAL GÉNÉRAL
        total_row = current_row
        ws_diame.cell(row=total_row, column=1, value='TOTAL GÉNÉRAL')
        ws_diame.cell(row=total_row, column=1).font = Font(bold=True, size=12)
        ws_diame.cell(row=total_row, column=2, value='')
        
        # Formules pour totaux (somme de toutes les lignes employés)
        first_row = 3
        last_row = current_row - 1
        
        # Totaux par mois
        ws_diame.cell(row=total_row, column=3, value=f'=SUM(C{first_row}:C{last_row})')  # M1 CNaPS
        ws_diame.cell(row=total_row, column=4, value=f'=SUM(D{first_row}:D{last_row})')  # M1 FMFP
        ws_diame.cell(row=total_row, column=5, value=f'=SUM(E{first_row}:E{last_row})')  # M2 CNaPS
        ws_diame.cell(row=total_row, column=6, value=f'=SUM(F{first_row}:F{last_row})')  # M2 FMFP
        ws_diame.cell(row=total_row, column=7, value=f'=SUM(G{first_row}:G{last_row})')  # M3 CNaPS
        ws_diame.cell(row=total_row, column=8, value=f'=SUM(H{first_row}:H{last_row})')  # M3 FMFP
        ws_diame.cell(row=total_row, column=9, value=f'=SUM(I{first_row}:I{last_row})')  # Total CNaPS
        ws_diame.cell(row=total_row, column=10, value=f'=SUM(J{first_row}:J{last_row})') # Total FMFP
        
        # Appliquer format et style à la ligne total
        for col in [3, 4, 5, 6, 7, 8, 9, 10]:
            cell = ws_diame.cell(row=total_row, column=col)
            cell.font = Font(bold=True, size=11)
            cell.number_format = '#,##0.00'

        # ========================================
        # ONGLET 2 : EMPLOYEUR
        # ========================================'''

content = content.replace(old_code, new_code)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Ajout separateurs milliers + ligne TOTAL GENERAL dans DIAME CNAPS")
