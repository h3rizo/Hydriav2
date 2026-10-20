#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Script pour ajouter la création de FicheStock dans api_adjust_stock"""

import sys
import os

# Ajouter le répertoire du projet au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Lire le fichier views.py
views_path = os.path.join(os.path.dirname(__file__), 'apps', 'inventory', 'views.py')

with open(views_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Trouver la ligne après StockMovement.objects.create()
insert_after_line = None
for i, line in enumerate(lines):
    if '        StockMovement.objects.create(' in line:
        # Trouver la fin de ce bloc (la ligne avec juste '        )')
        for j in range(i+1, len(lines)):
            if lines[j].strip() == ')':
                insert_after_line = j
                break
        break

if insert_after_line is None:
    print("[ERROR] Impossible de trouver StockMovement.objects.create()")
    sys.exit(1)

# Vérifier si le code n'existe pas déjà
code_exists = False
for i in range(insert_after_line, min(insert_after_line + 20, len(lines))):
    if 'FicheStock.objects.create' in lines[i] and "operation_type='ajustement'" in lines[i:i+10]:
        code_exists = True
        break

if code_exists:
    print("[OK] Le code FicheStock.objects.create existe deja")
    sys.exit(0)

# Code à insérer
new_code = """
        # Créer une entrée FicheStock pour l'ajustement
        FicheStock.objects.create(
            operation_date=datetime.now().date(),
            operation_type='ajustement',
            quantity=quantity,
            designation=stock.designation,
            base=stock.base,
            employee=request.user.employe if hasattr(request.user, 'employe') else None,
            notes=notes or f'Ajustement manuel: {old_quantity} → {stock.current_quantity}'
        )
"""

# Insérer le nouveau code après la ligne trouvée
lines.insert(insert_after_line + 1, new_code)

# Écrire le fichier modifié
with open(views_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("[OK] Modification effectuee avec succes!")
print("\nLa fonction api_adjust_stock cree maintenant des entrees FicheStock")
print(f"Code insere apres la ligne {insert_after_line + 1}")
