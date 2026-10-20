#!/usr/bin/env python3
"""Script pour remplacer toutes les icônes FontAwesome par des icônes Lucide avec effet 3D"""

# Mapping des icônes FontAwesome vers Lucide
ICON_MAPPING = {
    # Navigation & Dashboard
    'fa-chart-line': 'trending-up',
    'fa-tachometer-alt': 'gauge',
    'fa-chart-area': 'area-chart',
    'fa-chart-bar': 'bar-chart',

    # Calendar & Planning
    'fa-calendar-alt': 'calendar',
    'fa-calendar': 'calendar-days',
    'fa-clipboard-check': 'clipboard-check',
    'fa-clipboard-list': 'clipboard-list',

    # Users & People
    'fa-users': 'users',
    'fa-id-card': 'badge',
    'fa-user-shield': 'shield-check',

    # Files & Documents
    'fa-file-invoice-dollar': 'file-text',
    'fa-file-alt': 'file-text',
    'fa-file-export': 'file-down',
    'fa-file-import': 'file-up',
    'fa-file-upload': 'upload',
    'fa-file-invoice': 'file-text',
    'fa-receipt': 'receipt',

    # Money & Finance
    'fa-calculator': 'calculator',
    'fa-coins': 'coins',
    'fa-hand-holding-usd': 'hand-coins',
    'fa-cash-register': 'banknote',
    'fa-money-check-alt': 'credit-card',
    'fa-balance-scale': 'scale',

    # Commerce & Inventory
    'fa-store': 'store',
    'fa-shopping-cart': 'shopping-cart',
    'fa-warehouse': 'warehouse',

    # Infrastructure & Construction
    'fa-hard-hat': 'hard-hat',
    'fa-wrench': 'wrench',
    'fa-hammer': 'hammer',
    'fa-tools': 'wrench',

    # Water & Environment
    'fa-tint': 'droplet',
    'fa-water': 'waves',
    'fa-flask': 'flask-conical',
    'fa-cloud-sun': 'cloud-sun',

    # Maps & Geography
    'fa-map-marked-alt': 'map-pin',
    'fa-globe-africa': 'globe',
    'fa-building': 'building',
    'fa-route': 'route',

    # Actions & Operations
    'fa-search': 'search',
    'fa-cog': 'settings',
    'fa-cogs': 'settings',
    'fa-sync-alt': 'refresh-cw',
    'fa-exchange-alt': 'arrow-left-right',
    'fa-undo': 'undo',
    'fa-reply': 'reply',
    'fa-random': 'shuffle',

    # Communication & Collaboration
    'fa-inbox': 'inbox',
    'fa-keyboard': 'keyboard',

    # UI Elements
    'fa-th': 'grid',
    'fa-columns': 'columns',
    'fa-list': 'list',
    'fa-table': 'table',
    'fa-sliders-h': 'sliders-horizontal',

    # Status & Verification
    'fa-check-double': 'check-check',
    'fa-shield-alt': 'shield',
    'fa-pen': 'pencil',
    'fa-stethoscope': 'stethoscope',
    'fa-link': 'link',

    # Misc
    'fa-arrow-down': 'arrow-down',
    'fa-truck': 'truck',
    'fa-book': 'book-open',
    'fa-briefcase': 'briefcase',
    'fa-database': 'database',
}

# Mapping des tailles de classe
SIZE_MAPPING = {
    'text-4xl': 'icon-3xl',
    'text-5xl': 'icon-4xl',
    'text-6xl': 'icon-4xl',
    'text-3xl': 'icon-2xl',
}

def replace_icon(line, fa_class, lucide_name):
    """Remplace une icône FontAwesome par une icône Lucide avec effet 3D"""
    import re

    # Pattern pour détecter l'icône FA avec ses classes
    pattern = rf'<i class="fas {fa_class}([^"]*)"[^>]*></i>'

    def replacement(match):
        extra_classes = match.group(1).strip()

        # Extraire la taille
        size_class = 'icon-lg'  # Taille par défaut
        for old_size, new_size in SIZE_MAPPING.items():
            if old_size in extra_classes:
                size_class = new_size
                extra_classes = extra_classes.replace(old_size, '').strip()

        # Construire le remplacement
        return f'<span class="icon-3d{" " + extra_classes if extra_classes else ""}">\n                                <i data-lucide="{lucide_name}" class="{size_class}"></i>\n                            </span>'

    return re.sub(pattern, replacement, line)

def process_file(filename):
    """Traite le fichier et remplace toutes les icônes"""
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remplacer chaque icône
    for fa_class, lucide_name in ICON_MAPPING.items():
        content = replace_icon(content, fa_class, lucide_name)

    # Écrire le résultat
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✓ Fichier {filename} traité avec succès!")
    print(f"  {len(ICON_MAPPING)} types d'icônes remplacés")

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python replace_icons.py <fichier>")
        sys.exit(1)

    process_file(sys.argv[1])
