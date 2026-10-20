import sys

file_path = r'C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\apps\accounting\views_taxe_communale.py'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Trouver le début du doublon
start_marker = '# Ligne supprimee pour eviter duplication'
start_index = -1
for i, line in enumerate(lines):
    if start_marker in line:
        start_index = i
        break

if start_index == -1:
    print("Start marker not found")
    sys.exit(1)

# Trouver la fin du doublon (juste avant def etat_impot_synthetique)
end_marker = 'def etat_impot_synthetique'
end_index = -1
for i in range(start_index, len(lines)):
    if end_marker in lines[i]:
        end_index = i
        break

if end_index == -1:
    print("End marker not found")
    sys.exit(1)

# Trouver le décorateur login_required juste avant la fin
while end_index > start_index and '@login_required' not in lines[end_index]:
    end_index -= 1

# Garder les lignes avant start_index (en reculant un peu pour enlever l'espace vide avant le marker)
# et les lignes après end_index (exclu)
# On veut garder le bloc contextuel avant le marker
final_lines = lines[:start_index-1] # Le contexte finit par 'chart_ouvrages'

# Ajouter les lignes de fin de fonction manquantes (si elles ont été mangées)
# On a besoin de :
#     if request.GET.get('print'):
#         return render(request, 'accounting/facture_taxe_communale_print.html', context)
#         
#     return render(request, 'accounting/etat_taxe_communale.html', context)

final_lines.append("\n")
final_lines.append("    if request.GET.get('print'):\n")
final_lines.append("        return render(request, 'accounting/facture_taxe_communale_print.html', context)\n")
final_lines.append("        \n")
final_lines.append("    return render(request, 'accounting/etat_taxe_communale.html', context)\n")
final_lines.append("\n")
final_lines.append("\n")

# Ajouter la suite du fichier
final_lines.extend(lines[end_index:])

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(final_lines)

print(f"Successfully cleaned up. Removed lines from {start_index} to {end_index}")
