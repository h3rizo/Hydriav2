#!/usr/bin/env python
"""
Script pour ajouter automatiquement les traductions du menu aux fichiers .po
"""
from pathlib import Path

# Traductions FR → MG
MENU_TRANSLATIONS = {
    "Applications": "Rindranasa",
    "Recherche": "Tadiavo",
    "Tableaux & Rapports": "Tondrozotra sy Tatitra",
    "Plannings": "Drafitra",
    "Facturation": "Faktiora",
    "Achats/Stocks": "Fividianana/Tahiry",
    "Conversations": "Resaka",
    "Référentiel": "Toby",
    "Vue d'ensemble": "Topimaso",
    "Géographie & Population": "Jeografia sy mponina",
    "Carte interactive": "Sarintany miasa",
    "Paiements forfaitaires": "Fandoavam-bola voafetra",
    "Paiements au volume": "Fandoavam-bola araka ny habetsany",
    "Paiements cartes sociales": "Fandoavam-bola karatra sosialy",
    "Dépenses": "Fandaniana",
    "État des ouvrages": "Toetry ny asa",
    "Rapports & Analyses": "Tatitra sy Famakafakana",
    "Tableau de bord rapports": "Tondrozotra tatitra",
    "Activités par employé": "Asa isaky ny mpiasa",
    "Performance bases": "Fahombiazan'ny toby",
    "Indicateurs DiameX": "Mpanondro DiameX",
    "Analyses consommation": "Famakafakana fanjifana",
    "Analyse consommation": "Famakafakana fanjifana",
    "Analyse par point d'eau": "Famakafakana isaky ny loharano",
    "Tableau points d'eau": "Lisi-dranom-baravarana",
    "Analyse Cartes Sociales": "Famakafakana karatra sosialy",
    "Analyse Météo": "Famakafakana toetrandro",
    "Analyse Pièces de Rechange": "Famakafakana kojakoja",
    "Vue calendrier": "Fisehon-tetiandro",
    "Saisie planning": "Fampidirana drafitra",
    "Suivi réparations": "Fanaraha-maso fanamboarana",
    "Opérations terrain": "Asa an-tany",
    "Livraison": "Fandefasana",
    "Avance": "Vola mialoha",
    "Indemnités Journalières": "Karama isan'andro",
    "Retour": "Fiverenana",
    "Retour Indemnités": "Fiverenan'ny karama",
    "Retour Frais Déplacement": "Fiverenan'ny saram-dalana",
    "Suivi & Contrôle": "Fanaraha-maso sy Fifehezana",
    "Inspections & Maintenance": "Fizohiana sy Fikojakojana",
    "Analyses d'eau": "Famakafakana rano",
    "Réparations & Réhabilitations": "Fanamboarana sy Fanavaozana",
    "Positions GPS Employés": "Toerana GPS mpiasa",
    "Suivi avance": "Fanaraha-maso vola mialoha",
    "Chantiers": "Tetikasa",
    "Demandes Villages": "Fangatahan'ny tanàna",
    "Validation Sources": "Fanamarinana loharano",
    "Kanban Chantiers": "Kanban tetikasa",
    "Tâcherons": "Mpandray anjara",
    "WASH & Enquêtes": "WASH sy Fanadihadiana",
    "Ménages & Enquêtes": "Tokantrano sy Fanadihadiana",
    "Animations WASH": "Fanentanana WASH",
    "Paiements": "Fandoavam-bola",
    "Factures": "Faktiora",
    "Gestion volumétrique": "Fitantanana isaky ny habetsany",
    "Demandes BP": "Fangatahana BP",
    "Relevés & Facturation": "Fandikana sy Faktiora",
    "Liste des relevés": "Lisi-pandikana",
    "Facturation volumétrique": "Faktiora isaky ny habetsany",
    "Suivi paiements forfaitaires": "Fanaraha-maso fandoavam-bola voafetra",
    "Encaissement factures": "Fandraisana faktiora",
    "Compteurs": "Mpandika",
    "Suivi consommation": "Fanaraha-maso fanjifana",
    "Usagers": "Mpampiasa",
    "Représentantes & Avis": "Mpandraharaha sy Hevitra",
    "Cartes sociales": "Karatra sosialy",
    "Émission tickets": "Famoahana tapakila",
    "Encaissement": "Fandraisana",
    "Gestion cartes (old)": "Fitantanana karatra (taloha)",
    "Tableau de bord": "Tondrozotra",
    "Workflow Inventaire": "Fizotran'ny fanisana",
    "Inventaires": "Fanisana",
    "Fiches de Stock": "Taratasy tahiry",
    "Résumé Stocks": "Famintinana tahiry",
    "Calcul Commandes": "Kajy baiko",
    "Bons de Commande": "Tapakila baiko",
    "Autres Opérations": "Asa hafa",
    "Saisie Achats": "Fampidirana fividianana",
    "Transferts": "Fifindrana",
    "Parc Véhicules": "Fiara",
    "Gestion Véhicules": "Fitantanana fiara",
    "Mes conversations": "Ny resako",
    "Nouveau chat": "Resaka vaovao",
    "Nouveau groupe": "Vondrona vaovao",
    "Assistant IA": "Mpanampy IA",
    "Ouvrir l'assistant": "Hanokatra ny mpanampy",
    "Requête rapide": "Fangatahana haingana",
    "Vue d'ensemble comptable": "Topimason'ny kaonty",
    "Base DiameX": "Toby DiameX",
    "Import depuis Access": "Fampidirana avy amin'ny Access",
    "Écritures comptables (DATA)": "Soratra kaonty (DATA)",
    "Transactions temporaires": "Fifanakalozana mandalo",
    "Export Paie & Charges": "Famoahana karama sy sarany",
    "Diagnostic Soldes": "Fizohiana vola sisa",
    "Comparaison soldes": "Fampitahana vola sisa",
    "Soldes Réels": "Vola sisa marina",
    "Contrôle Conversion": "Fifehezana fanovana",
    "Conversion Partie Double": "Fanovana ampahany roa",
    "Budget & Fonds": "Tetibola sy Vola",
    "Budgets annuels": "Tetibola isan-taona",
    "Demandes de fonds": "Fangatahana vola",
    "Vérifications": "Fanamarinana",
    "Vérification Unifiée": "Fanamarinana mitambatra",
    "Vérification scans": "Fanamarinana sary",
    "Vérification Paiements Employés": "Fanamarinana fandoavam-bolan'ny mpiasa",
    "Vérification Fournisseurs": "Fanamarinana mpanome",
    "Vérification avec Ouvrage": "Fanamarinana misy asa",
    "Vérification sans Ouvrage": "Fanamarinana tsy misy asa",
    "Évaluation": "Fanombanana",
    "Évaluation Saisie": "Fanombanana fampidirana",
    "Recoupements": "Fampitahana",
    "Recoupement planning": "Fampitahana drafitra",
    "Recoupement achats": "Fampitahana fividianana",
    "Documentation": "Antontan-taratasy",
    "Saisie documents": "Fampidirana antontan-taratasy",
    "Rapport documents": "Tatitra antontan-taratasy",
    "Déclarations fiscales": "Fanambarana hetra",
    "Déclaration Communication Impôts": "Fanambarana fifandraisana hetra",
    "Configuration Natures": "Fanefena karazana",
    "Interface Admin": "Efitrano fitantanana",
    "Interface Django": "Efitrano Django",
    "Gestion Fichiers": "Fitantanana rakitra",
    "Géographie": "Jeografia",
    "Géographie Consolidée": "Jeografia mitambatra",
    "Capture Données Terrain": "Fandraisan-tsary an-tany",
}

BASE_DIR = Path(__file__).resolve().parent
LOCALE_DIR = BASE_DIR / 'locale'

def add_translations():
    """Ajoute les nouvelles traductions aux fichiers .po"""

    # Lire le fichier malgache actuel
    mg_po_path = LOCALE_DIR / 'mg' / 'LC_MESSAGES' / 'django.po'
    fr_po_path = LOCALE_DIR / 'fr' / 'LC_MESSAGES' / 'django.po'

    with open(mg_po_path, 'r', encoding='utf-8') as f:
        mg_content = f.read()

    with open(fr_po_path, 'r', encoding='utf-8') as f:
        fr_content = f.read()

    # Extraire les msgid déjà présents pour éviter les doublons
    existing_msgids = set()
    for line in mg_content.split('\n'):
        if line.startswith('msgid "') and line != 'msgid ""':
            msgid = line.replace('msgid "', '').replace('"', '')
            existing_msgids.add(msgid)

    # Préparer les nouvelles entrées
    new_mg_entries = []
    new_fr_entries = []
    added_count = 0

    for fr_text, mg_text in sorted(MENU_TRANSLATIONS.items()):
        if fr_text not in existing_msgids:
            # Malgache
            new_mg_entries.append(f'msgid "{fr_text}"')
            new_mg_entries.append(f'msgstr "{mg_text}"')
            new_mg_entries.append('')

            # Français (même chose)
            new_fr_entries.append(f'msgid "{fr_text}"')
            new_fr_entries.append(f'msgstr "{fr_text}"')
            new_fr_entries.append('')

            added_count += 1
            print(f"[AJOUT] {fr_text} -> {mg_text}")
        else:
            print(f"[SKIP] {fr_text} (deja present)")

    if added_count == 0:
        print("\n[INFO] Aucune nouvelle traduction à ajouter")
        return

    # Ajouter les nouvelles entrées à la fin des fichiers (avant la dernière ligne vide)
    mg_lines = mg_content.rstrip().split('\n')
    fr_lines = fr_content.rstrip().split('\n')

    # Malgache
    mg_lines.extend(new_mg_entries)
    new_mg_content = '\n'.join(mg_lines) + '\n'

    # Français
    fr_lines.extend(new_fr_entries)
    new_fr_content = '\n'.join(fr_lines) + '\n'

    # Sauvegarder
    with open(mg_po_path, 'w', encoding='utf-8') as f:
        f.write(new_mg_content)

    with open(fr_po_path, 'w', encoding='utf-8') as f:
        f.write(new_fr_content)

    print(f"\n[OK] {added_count} nouvelles traductions ajoutées")
    print(f"[OK] Fichiers mis à jour:")
    print(f"  - {mg_po_path}")
    print(f"  - {fr_po_path}")

if __name__ == '__main__':
    add_translations()
