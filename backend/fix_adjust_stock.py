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
    content = f.read()

# Trouver la section à modifier
search_text = """        # Créer un mouvement de stock
        StockMovement.objects.create(
            designation=stock.designation,
            base=stock.base,
            movement_type=movement_type,
            quantity=quantity,
            movement_date=datetime.now(),
            reference=reference,
            notes=notes or f'Ajustement manuel: {old_quantity} → {stock.current_quantity}'
        )

        return JsonResponse({"""

replacement_text = """        # Créer un mouvement de stock
        StockMovement.objects.create(
            designation=stock.designation,
            base=stock.base,
            movement_type=movement_type,
            quantity=quantity,
            movement_date=datetime.now(),
            reference=reference,
            notes=notes or f'Ajustement manuel: {old_quantity} → {stock.current_quantity}'
        )

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

        return JsonResponse({"""

# Vérifier si le texte existe
if search_text in content:
    print("[OK] Texte trouve, remplacement en cours...")
    content = content.replace(search_text, replacement_text)

    # Écrire le fichier modifié
    with open(views_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print("[OK] Modification effectuee avec succes!")
    print("\nLa fonction api_adjust_stock cree maintenant des entrees FicheStock")
else:
    print("[ERROR] Texte non trouve dans le fichier")
    print("\nVerification si la modification existe deja...")
    if "FicheStock.objects.create" in content and "operation_type='ajustement'" in content:
        print("[OK] La modification semble deja presente dans le fichier")
    else:
        print("[ERROR] Impossible de localiser la section a modifier")
