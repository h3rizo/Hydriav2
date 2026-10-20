#!/usr/bin/env python
"""
Script pour corriger automatiquement les URLs hardcodées dans home_launcher.html
en les remplaçant par des tags Django {% url 'app:name' %}
"""
import re
from pathlib import Path

# Mapping des URLs hardcodées vers leurs routes Django correspondantes
URL_MAPPINGS = {
    # Plannings
    r'href="/plannings/"': r'href="{% url \'planning:list\' %}"',
    r'href="/plannings/calendrier/"': r'href="{% url \'planning:planning_calendar\' %}"',
    r'href="/plannings/consolide/"': r'href="{% url \'planning:planning_consolide\' %}"',

    # Inspections
    r'href="/inspections/"': r'href="{% url \'inspections:equipment_selection\' %}"',

    # Employés
    r'href="/employes/list/"': r'href="{% url \'employees:list\' %}"',
    r'href="/employes/paiements-cnaps-fmfp/"': r'href="{% url \'employees:paiements_cnaps_fmfp_list\' %}"',

    # Comptabilité
    r'href="/comptabilite/verification/"': r'href="{% url \'accounting:verification\' %}"',
    r'href="/comptabilite/import-diamex/"': r'href="{% url \'accounting:import_diamex\' %}"',
    r'href="/comptabilite/comptes/"': r'href="{% url \'accounting:comptes_list\' %}"',
    r'href="/accounting/ecritures/"': r'href="{% url \'accounting:ecritures_list\' %}"',
    r'href="/accounting/transactions-temp/"': r'href="{% url \'accounting:transactions_temp_list\' %}"',
    r'href="/accounting/export-paie/"': r'href="{% url \'accounting:export_paie\' %}"',
    r'href="/accounting/diagnostic-soldes/"': r'href="{% url \'accounting:diagnostic_soldes\' %}"',
    r'href="/accounting/comparaison-soldes/"': r'href="{% url \'accounting:comparaison_soldes\' %}"',
    r'href="/accounting/soldes-reels/"': r'href="{% url \'accounting:soldes_reels_list\' %}"',
    r'href="/accounting/controle-conversion/"': r'href="{% url \'accounting:controle_conversion\' %}"',
    r'href="/accounting/conversion-double/"': r'href="{% url \'accounting:conversion_double\' %}"',

    # Recherche
    r'href="/recherche/"': r'href="{% url \'core:search\' %}"',
}

def fix_urls_in_file(filepath):
    """Corrige les URLs hardcodées dans un fichier"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    changes_made = []

    for pattern, replacement in URL_MAPPINGS.items():
        if re.search(pattern, content):
            count = len(re.findall(pattern, content))
            content = re.sub(pattern, replacement, content)
            changes_made.append(f"  - {count}x: {pattern} > {replacement}")

    # Sauvegarder si des changements ont été faits
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return changes_made

    return None

def main():
    filepath = Path('templates/home_launcher.html')

    print("Correction des URLs hardcodees dans home_launcher.html...")
    print("=" * 70)

    changes = fix_urls_in_file(filepath)
    if changes:
        print(f"\n[OK] {filepath}")
        for change in changes:
            print(change)
        print(f"\nTotal: {len(changes)} type(s) de changement(s)")
    else:
        print("\nAucune URL hardcodee trouvee.")

if __name__ == '__main__':
    main()
