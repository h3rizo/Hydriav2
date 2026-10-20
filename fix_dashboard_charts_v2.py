#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de modification dashboard_paiements_volume.html
1. Ajouter boutons pliage/depliage aux 2 graphiques (plies par defaut)
2. Mettre les stats pointages a la ligne (flex-col)
"""

import re

FILE_PATH = '/home/soakoja/hydria/backend/templates/accounting/dashboard_paiements_volume.html'

with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================
# 1. MODIFICATION GRAPHIQUE 1 : Comparaison par Commune
# ============================================================

# Remplacer le h2.card-title du graphique 1
OLD_H2_CHART1 = '''                <h2 class="card-title">
                    <i class="fas fa-map-marked-alt text-primary mr-2"></i>
                    Comparaison par Commune {{ annee }}
                </h2>
                <div class="chart-container">
                    <canvas id="chartComparaisonCommunes"></canvas>
                </div>'''

NEW_H2_CHART1 = '''                <div class="flex items-center justify-between">
                    <h2 class="card-title">
                        <i class="fas fa-map-marked-alt text-primary mr-2"></i>
                        Comparaison par Commune {{ annee }}
                    </h2>
                    <button class="btn btn-xs btn-ghost" onclick="toggleChart(\'chartComparaisonCommunes\')" id="btn-toggle-chartComparaisonCommunes">
                        <i class="fas fa-chevron-down"></i>
                    </button>
                </div>
                <div id="container-chartComparaisonCommunes" class="hidden">
                    <div class="chart-container">
                        <canvas id="chartComparaisonCommunes"></canvas>
                    </div>
                </div>'''

if OLD_H2_CHART1 in content:
    content = content.replace(OLD_H2_CHART1, NEW_H2_CHART1)
    print('[OK] Graphique 1 (Comparaison par Commune) modifie')
else:
    print('[WARNING] Graphique 1 non trouve - tentative avec regex')
    # Tentative avec regex plus souple
    pattern1 = r'(<h2 class="card-title">\s*<i class="fas fa-map-marked-alt[^"]*"[^>]*></i>\s*Comparaison par Commune \{\{ annee \}\}\s*</h2>\s*<div class="chart-container">\s*<canvas id="chartComparaisonCommunes"></canvas>\s*</div>)'
    match1 = re.search(pattern1, content, re.DOTALL)
    if match1:
        replacement1 = '''<div class="flex items-center justify-between">
                    <h2 class="card-title">
                        <i class="fas fa-map-marked-alt text-primary mr-2"></i>
                        Comparaison par Commune {{ annee }}
                    </h2>
                    <button class="btn btn-xs btn-ghost" onclick="toggleChart(\'chartComparaisonCommunes\')" id="btn-toggle-chartComparaisonCommunes">
                        <i class="fas fa-chevron-down"></i>
                    </button>
                </div>
                <div id="container-chartComparaisonCommunes" class="hidden">
                    <div class="chart-container">
                        <canvas id="chartComparaisonCommunes"></canvas>
                    </div>
                </div>'''
        content = content[:match1.start()] + replacement1 + content[match1.end():]
        print('[OK] Graphique 1 modifie via regex')
    else:
        print('[ERROR] Graphique 1 introuvable meme avec regex')

# ============================================================
# 2. MODIFICATION GRAPHIQUE 2 : Analyse Delais de Paiement
# ============================================================

OLD_H2_CHART2 = '''                <h2 class="card-title">
                    <i class="fas fa-clock text-warning mr-2"></i>
                    Analyse Délais de Paiement
                </h2>
                <div class="chart-container">
                    <canvas id="chartDelaisPaiement"></canvas>
                </div>'''

NEW_H2_CHART2 = '''                <div class="flex items-center justify-between">
                    <h2 class="card-title">
                        <i class="fas fa-clock text-warning mr-2"></i>
                        Analyse Délais de Paiement
                    </h2>
                    <button class="btn btn-xs btn-ghost" onclick="toggleChart(\'chartDelaisPaiement\')" id="btn-toggle-chartDelaisPaiement">
                        <i class="fas fa-chevron-down"></i>
                    </button>
                </div>
                <div id="container-chartDelaisPaiement" class="hidden">
                    <div class="chart-container">
                        <canvas id="chartDelaisPaiement"></canvas>
                    </div>
                </div>'''

if OLD_H2_CHART2 in content:
    content = content.replace(OLD_H2_CHART2, NEW_H2_CHART2)
    print('[OK] Graphique 2 (Analyse Delais) modifie')
else:
    print('[WARNING] Graphique 2 non trouve - tentative avec regex')
    pattern2 = r'(<h2 class="card-title">\s*<i class="fas fa-clock[^"]*"[^>]*></i>\s*Analyse Délais de Paiement\s*</h2>\s*<div class="chart-container">\s*<canvas id="chartDelaisPaiement"></canvas>\s*</div>)'
    match2 = re.search(pattern2, content, re.DOTALL)
    if match2:
        replacement2 = '''<div class="flex items-center justify-between">
                    <h2 class="card-title">
                        <i class="fas fa-clock text-warning mr-2"></i>
                        Analyse Délais de Paiement
                    </h2>
                    <button class="btn btn-xs btn-ghost" onclick="toggleChart(\'chartDelaisPaiement\')" id="btn-toggle-chartDelaisPaiement">
                        <i class="fas fa-chevron-down"></i>
                    </button>
                </div>
                <div id="container-chartDelaisPaiement" class="hidden">
                    <div class="chart-container">
                        <canvas id="chartDelaisPaiement"></canvas>
                    </div>
                </div>'''
        content = content[:match2.start()] + replacement2 + content[match2.end():]
        print('[OK] Graphique 2 modifie via regex')
    else:
        print('[ERROR] Graphique 2 introuvable meme avec regex')

# ============================================================
# 3. STATS POINTAGES : flex-wrap -> flex-col
# ============================================================

OLD_POINTAGE_FLEX = '<div class="flex flex-wrap items-center gap-3">'
NEW_POINTAGE_FLEX = '<div class="flex flex-col gap-2">'

# On cible specifiquement le div DANS modal-pointage-panel
# Remplacer uniquement la premiere occurrence apres modal-pointage-panel
panel_idx = content.find('<div id="modal-pointage-panel"')
if panel_idx != -1:
    # Chercher le flex div dans les 500 chars suivants
    section = content[panel_idx:panel_idx + 500]
    if OLD_POINTAGE_FLEX in section:
        new_section = section.replace(OLD_POINTAGE_FLEX, NEW_POINTAGE_FLEX, 1)
        content = content[:panel_idx] + new_section + content[panel_idx + 500:]
        print('[OK] Stats pointages mis a la ligne (flex-col)')
    else:
        print('[WARNING] Pattern flex non trouve dans modal-pointage-panel')
        # Afficher ce qu'on trouve
        print('[DEBUG] Contenu du panel:', section[:300])
else:
    print('[ERROR] modal-pointage-panel introuvable')

# ============================================================
# 4. AJOUTER JAVASCRIPT : toggleChart() et chartInstances
# ============================================================

# Chercher les initialisations des charts pour les rendre globales
# Chart 1: const chartComparaisonCommunes = new Chart(...)
# Chart 2: const chartDelaisPaiement = new Chart(...)

# Ajouter window.chartInstances apres chaque chart creation
# Chercher: "const chartComparaisonCommunes = new Chart("
OLD_CHART1_VAR = 'const chartComparaisonCommunes = new Chart('
NEW_CHART1_VAR = 'window.chartInstances = window.chartInstances || {};\n    window.chartInstances["chartComparaisonCommunes"] = new Chart('

if OLD_CHART1_VAR in content:
    content = content.replace(OLD_CHART1_VAR, NEW_CHART1_VAR, 1)
    print('[OK] Chart 1 rendu global (window.chartInstances)')
else:
    print('[WARNING] Initialisation chart 1 non trouvee pour globalisation')

OLD_CHART2_VAR = 'const chartDelaisPaiement = new Chart('
NEW_CHART2_VAR = 'window.chartInstances = window.chartInstances || {};\n    window.chartInstances["chartDelaisPaiement"] = new Chart('

if OLD_CHART2_VAR in content:
    content = content.replace(OLD_CHART2_VAR, NEW_CHART2_VAR, 1)
    print('[OK] Chart 2 rendu global (window.chartInstances)')
else:
    print('[WARNING] Initialisation chart 2 non trouvee pour globalisation')

# Ajouter la fonction toggleChart() avant </script>
TOGGLE_JS = '''
    // ====================================================
    // PLIAGE/DEPLIAGE DES GRAPHIQUES
    // ====================================================
    function toggleChart(chartId) {
        const container = document.getElementById('container-' + chartId);
        const btn = document.getElementById('btn-toggle-' + chartId);
        const icon = btn ? btn.querySelector('i') : null;

        if (!container) return;

        const isHidden = container.classList.contains('hidden');

        if (isHidden) {
            // Afficher le graphique
            container.classList.remove('hidden');
            if (icon) {
                icon.classList.remove('fa-chevron-down');
                icon.classList.add('fa-chevron-up');
            }
            // Forcer le resize du chart apres affichage
            setTimeout(function() {
                if (window.chartInstances && window.chartInstances[chartId]) {
                    window.chartInstances[chartId].resize();
                }
            }, 50);
        } else {
            // Masquer le graphique
            container.classList.add('hidden');
            if (icon) {
                icon.classList.remove('fa-chevron-up');
                icon.classList.add('fa-chevron-down');
            }
        }
    }

'''

# Inserer avant la derniere balise </script>
last_script_end = content.rfind('</script>')
if last_script_end != -1:
    content = content[:last_script_end] + TOGGLE_JS + content[last_script_end:]
    print('[OK] Fonction toggleChart() ajoutee')
else:
    print('[ERROR] Balise </script> non trouvee')

# ============================================================
# 5. SAUVEGARDER
# ============================================================

with open(FILE_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print('')
print('[DONE] Modifications sauvegardees dans', FILE_PATH)
print('       - Graphique 1 pliable (plié par defaut)')
print('       - Graphique 2 pliable (plié par defaut)')
print('       - Stats pointages en colonne')
print('       - Fonction toggleChart() ajoutee')