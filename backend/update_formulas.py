import re

file_path = 'apps/employees/views_cnaps_fmfp.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Remplacer les totaux en dur par des formules Excel
old_totaux = r'''            # Totaux
            ws_diame\.cell\(row=current_row, column=9, value=float\(detail\.total_cnaps\)\)
            ws_diame\.cell\(row=current_row, column=10, value=float\(detail\.total_fmfp\)\)'''

new_totaux = '''            # Totaux - Utiliser des formules Excel au lieu de valeurs en dur
            # Colonne I (Total CNaPS) = C + E + G
            ws_diame.cell(row=current_row, column=9, value=f'=C{current_row}+E{current_row}+G{current_row}')
            # Colonne J (Total FMFP) = D + F + H
            ws_diame.cell(row=current_row, column=10, value=f'=D{current_row}+F{current_row}+H{current_row}')'''

content = re.sub(old_totaux, new_totaux, content, flags=re.MULTILINE)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Formules Excel ajoutees pour les totaux")
