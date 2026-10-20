"""
Script Python à exécuter SUR LE VPS pour créer les 2 fichiers longs.

Utilisation:
1. Copier ce fichier sur le VPS (via copy/paste dans un éditeur comme nano)
2. Le rendre exécutable: chmod +x create_long_files.py
3. L'exécuter: python create_long_files.py

Le script créera:
- import_diamex_portable.py (309 lignes)
- README_IMPORT_DIAMEX.txt (220 lignes)
"""

import os

# Contenu du fichier import_diamex_portable.py
IMPORT_DIAMEX_CONTENT = '''"""
Script Python portable pour lire un fichier Access LOCAL (Windows)
et envoyer les données vers Django via API.

Version portable : Lit la configuration depuis config_import.ini

Usage:
    python import_diamex_portable.py

Le script :
1. Lit le fichier config_import.ini
2. Récupère la liste des fichiers Access depuis l'API Django
3. Extrait les tables DATA et SoldesReels
4. Envoie en JSON vers /comptabilite/api/import-from-access/
"""
import pyodbc
import json
import requests
import sys
import os
from decimal import Decimal
from configparser import ConfigParser

# Charger la configuration depuis le fichier INI
config = ConfigParser()
config_file = 'config_import.ini'

if not os.path.exists(config_file):
    print(f"[ERROR] Fichier de configuration '{config_file}' introuvable")
    print(f"[INFO] Assurez-vous que {config_file} est dans le même dossier que ce script")
    sys.exit(1)

config.read(config_file, encoding='utf-8')

# Lire les paramètres de configuration
try:
    DJANGO_URL = config.get('SERVEUR', 'DJANGO_URL')
    TIMEOUT = config.getint('OPTIONS', 'TIMEOUT', fallback=300)
    VERBOSE = config.getboolean('OPTIONS', 'VERBOSE', fallback=True)
except Exception as e:
    print(f"[ERROR] Erreur lors de la lecture de la configuration: {e}")
    sys.exit(1)

def log_progress(message):
    """Affiche un message de progression si VERBOSE est activé"""
    if VERBOSE:
        print(message)

def lire_access_local(file_path):
    """
    Lit un fichier Access LOCAL et retourne les données des tables DATA et SoldesReels.

    Args:
        file_path: Chemin complet vers le fichier .accde (ex: G:/.../file.accde)

    Returns:
        dict: {'data_rows': [...], 'soldes_rows': [...]}
    """
    log_progress(f"[READ] Lecture du fichier Access: {file_path}")

    # Vérifier que le fichier existe
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Fichier introuvable: {file_path}")

    # Connexion au fichier Access
    conn_str = (
        r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
        f'DBQ={file_path};'
    )

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # ========== TABLE DATA ==========
        log_progress("[READ] Lecture table DATA...")
        cursor.execute("SELECT * FROM DATA")
        columns_data = [column[0] for column in cursor.description]

        data_rows = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns_data, row))
            # Convertir les objets datetime et Decimal en types JSON
            for key, value in row_dict.items():
                if hasattr(value, 'isoformat'):  # datetime or date object
                    # CRITICAL: Django DateField attend AAAA-MM-JJ (pas de timestamp)
                    # Extraire uniquement la date (pas l'heure)
                    if hasattr(value, 'date'):
                        # datetime object - extraire la date
                        row_dict[key] = value.date().isoformat()
                    else:
                        # date object - format ISO direct
                        row_dict[key] = value.isoformat()
                elif isinstance(value, Decimal):  # Decimal object
                    row_dict[key] = float(value)
                elif isinstance(value, str):
                    # Nettoyer les espaces insécables et autres caractères invisibles
                    row_dict[key] = value.replace('\\xa0', ' ').strip()
            data_rows.append(row_dict)

        log_progress(f"[OK] {len(data_rows)} lignes DATA lues")

        # ========== TABLE SoldesReels ==========
        soldes_rows = []
        try:
            log_progress("[READ] Lecture table SoldesReels...")
            cursor.execute("SELECT * FROM SoldesReels")
            columns_soldes = [column[0] for column in cursor.description]

            for row in cursor.fetchall():
                row_dict = dict(zip(columns_soldes, row))
                # Convertir datetime et Decimal en types JSON
                for key, value in row_dict.items():
                    if hasattr(value, 'isoformat'):  # datetime or date object
                        # CRITICAL: Django DateField attend AAAA-MM-JJ (pas de timestamp)
                        # Extraire uniquement la date (pas l'heure)
                        if hasattr(value, 'date'):
                            # datetime object - extraire la date
                            row_dict[key] = value.date().isoformat()
                        else:
                            # date object - format ISO direct
                            row_dict[key] = value.isoformat()
                    elif isinstance(value, Decimal):
                        row_dict[key] = float(value)
                    elif isinstance(value, str):
                        # Nettoyer les espaces insécables et autres caractères invisibles
                        row_dict[key] = value.replace('\\xa0', ' ').strip()
                soldes_rows.append(row_dict)

            log_progress(f"[OK] {len(soldes_rows)} lignes SoldesReels lues")
        except pyodbc.Error:
            log_progress("[WARNING] Table SoldesReels introuvable (ignorée)")

        conn.close()

        return {
            'data_rows': data_rows,
            'soldes_rows': soldes_rows
        }

    except pyodbc.Error as e:
        print(f"[ERROR] Erreur pyodbc: {e}")
        raise

def envoyer_vers_django(file_path, fichier_nom, data, employe_surnom):
    """
    Envoie les données vers Django via POST.

    Args:
        file_path: Chemin du fichier (pour info uniquement)
        fichier_nom: Nom du fichier (sera utilisé comme fichier_source)
        data: Dict avec data_rows et soldes_rows
        employe_surnom: Surnom de l'employé qui effectue l'import
    """
    log_progress(f"[SEND] Envoi vers Django: {DJANGO_URL}/comptabilite/api/import-from-access/")
    log_progress(f"[INFO] Employé: {employe_surnom}")

    # Préparer les données POST
    post_data = {
        'file_path': file_path,  # Info uniquement
        'fichier_nom': fichier_nom,
        'data_rows': json.dumps(data['data_rows']),
        'soldes_rows': json.dumps(data['soldes_rows']),
        'employe_surnom': employe_surnom  # ← Identifier l'employé par son surnom pour imported_by
    }

    # Session pour gérer les cookies (si authentification)
    session = requests.Session()

    try:
        response = session.post(
            f'{DJANGO_URL}/comptabilite/api/import-from-access/',
            data=post_data,
            timeout=TIMEOUT
        )

        log_progress(f"[OK] Réponse HTTP {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                log_progress(f"[SUCCESS] {result.get('message')}")
                log_progress(f"Stats: {result.get('stats')}")
                # Afficher les erreurs s'il y en a
                errors = result.get('errors', [])
                if errors:
                    log_progress(f"[WARNING] {len(errors)} erreur(s) détectée(s):")
                    for i, error in enumerate(errors, 1):
                        log_progress(f"  {i}. {error}")
                return True
            else:
                print(f"[ERROR] {result.get('error')}")
                return False
        else:
            print(f"[ERROR] HTTP {response.status_code}: {response.text[:500]}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Erreur réseau: {e}")
        return False

def recuperer_fichiers_depuis_api():
    """
    Récupère la liste des fichiers Access à importer depuis l'API Django.
    Permet de paramétrer les chemins pour chaque employé.

    Returns:
        list: Liste de dict avec 'path', 'nom' et 'employe_surnom'
    """
    log_progress("[API] Récupération de la liste des fichiers depuis Django...")

    try:
        # Session pour gérer les cookies (si authentification)
        session = requests.Session()

        # Appel API pour obtenir la liste des bases DiameX
        response = session.get(
            f'{DJANGO_URL}/api/bases-diamex/',
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                fichiers = data.get('fichiers', [])
                log_progress(f"[OK] {len(fichiers)} fichier(s) récupéré(s) depuis l'API")

                # Afficher la liste
                for idx, fichier in enumerate(fichiers, 1):
                    log_progress(f"   {idx}. {fichier['nom']}")

                return fichiers
            else:
                print(f"[ERROR] Erreur API: {data.get('error')}")
                return []
        else:
            print(f"[ERROR] HTTP {response.status_code}: {response.text[:200]}")
            return []

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Erreur réseau lors de la récupération des fichiers: {e}")
        return []


def main():
    """Point d'entrée principal."""
    print("=" * 60)
    print("IMPORT DIAMEX LOCAL → DJANGO")
    print("=" * 60)
    print(f"Serveur: {DJANGO_URL}")
    print(f"Timeout: {TIMEOUT}s")
    print("=" * 60)

    # Si un argument est fourni, utiliser ce fichier spécifique
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        fichier_nom = os.path.basename(file_path)
        # En mode fichier unique, demander le surnom de l'employé
        employe_surnom = input("Entrez le surnom de l'employé (ex: HERIZO): ").strip()
        if not employe_surnom:
            print("[ERROR] Le surnom de l'employé est requis.")
            sys.exit(1)
        fichiers = [{'path': file_path, 'nom': fichier_nom, 'employe_surnom': employe_surnom}]
        print(f"\\n[INFO] Mode fichier unique: {fichier_nom}")
    else:
        # Récupérer la liste des fichiers depuis l'API Django
        fichiers = recuperer_fichiers_depuis_api()

        if not fichiers:
            print("\\n[ERROR] Aucun fichier à importer. Vérifiez la configuration dans Django.")
            print("[INFO] Vous pouvez aussi spécifier un fichier en argument:")
            print('       python import_diamex_portable.py "C:\\\\chemin\\\\vers\\\\fichier.accde"')
            sys.exit(1)

    # Traiter chaque fichier
    for fichier in fichiers:
        print(f"\\n{'='*60}")
        print(f"Fichier: {fichier['nom']}")
        print(f"{'='*60}")

        try:
            # 1. Lire Access localement
            data = lire_access_local(fichier['path'])

            # 2. Envoyer vers Django avec le surnom de l'employé
            employe_surnom = fichier.get('employe_surnom', 'INCONNU')
            success = envoyer_vers_django(
                fichier['path'],
                fichier['nom'],
                data,
                employe_surnom
            )

            if success:
                print(f"[✓] Import réussi pour {fichier['nom']}")
            else:
                print(f"[✗] Échec import pour {fichier['nom']}")

        except Exception as e:
            print(f"[ERROR] Exception: {e}")
            import traceback
            traceback.print_exc()

    print("\\n" + "="*60)
    print("TERMINÉ")
    print("="*60)

if __name__ == '__main__':
    main()
'''

# Contenu du fichier README_IMPORT_DIAMEX.txt
README_CONTENT = '''================================================================================
                    IMPORT DIAMEX LOCAL - GUIDE D'INSTALLATION
================================================================================

📋 DESCRIPTION

Ce package permet d'importer les données des fichiers DiameX (Access) depuis
n'importe quel ordinateur Windows vers le système Hydria.

Les données sont lues localement depuis les fichiers .accde et envoyées
automatiquement vers le serveur Django via l'API REST.


📦 CONTENU DU PACKAGE

1. INSTALLER_IMPORT_DIAMEX.bat    - Script d'installation (à exécuter UNE FOIS)
2. LANCER_IMPORT.bat              - Script de lancement (à exécuter pour importer)
3. import_diamex_portable.py      - Script Python portable
4. config_import.ini              - Fichier de configuration
5. README_IMPORT_DIAMEX.txt       - Ce fichier


🔧 PRÉREQUIS

1. ✅ Système d'exploitation : Windows 7 ou supérieur

2. ✅ Python 3.6 ou supérieur installé
   - Télécharger depuis : https://www.python.org/downloads/
   - IMPORTANT : Cocher "Add Python to PATH" lors de l'installation

3. ✅ Microsoft Access Database Engine (driver ODBC)
   - Automatiquement installé si vous avez Microsoft Office
   - Sinon, télécharger "Microsoft Access Database Engine 2016 Redistributable"
     https://www.microsoft.com/en-us/download/details.aspx?id=54920
   - Choisir la version selon votre système :
     * 32-bit (x86) pour Windows 32-bit OU Office 32-bit
     * 64-bit (x64) pour Windows 64-bit ET Office 64-bit

4. ✅ Accès réseau au serveur Django (https://www.hydria.mg)


📥 INSTALLATION (PREMIÈRE FOIS UNIQUEMENT)

Étape 1 : Créer un dossier pour l'import
-------------------------------------------
1. Créer un nouveau dossier, par exemple :
   C:\\ImportDiameX

2. Copier TOUS les fichiers du package dans ce dossier


Étape 2 : Exécuter l'installation
-----------------------------------
1. Double-cliquer sur INSTALLER_IMPORT_DIAMEX.bat

2. Le script va :
   ✓ Vérifier que Python est installé
   ✓ Installer les dépendances Python (pyodbc, requests)
   ✓ Vérifier la disponibilité du driver Access

3. Si tout est OK, vous verrez :
   [OK] Python détecté
   [OK] Dépendances installées avec succès
   [OK] Driver Access disponible

4. Si des erreurs apparaissent :
   - Installer Python si manquant
   - Installer le driver Access si manquant


Étape 3 : Vérifier la configuration
-------------------------------------
1. Ouvrir config_import.ini avec le Bloc-notes

2. Vérifier l'URL du serveur Django :
   DJANGO_URL = https://compta.hydria.mg

3. Pour tester en local (développement uniquement) :
   # DJANGO_URL = https://compta.hydria.mg   (commenter avec #)
   DJANGO_URL = http://localhost:8000         (décommenter)

4. Ajuster le timeout si nécessaire (par défaut 300 secondes = 5 minutes)


🚀 UTILISATION QUOTIDIENNE

Une fois l'installation terminée, pour importer les données :

1. Double-cliquer sur LANCER_IMPORT.bat

2. Le script va :
   ✓ Se connecter à l'API Django
   ✓ Récupérer la liste des fichiers Access configurés
   ✓ Importer chaque fichier automatiquement

3. Vous verrez la progression :
   [API] Récupération de la liste des fichiers depuis Django...
   [OK] 2 fichier(s) récupéré(s) depuis l'API
      1. DiameX v3.16.1 - Base 1.accde
      2. DiameX v3.16.1 - Base 2.accde

   [READ] Lecture du fichier Access...
   [OK] 1234 lignes DATA lues
   [OK] 567 lignes SoldesReels lues

   [SEND] Envoi vers Django...
   [SUCCESS] Import réussi
   [✓] Import réussi pour DiameX v3.16.1 - Base 1.accde


📁 CONFIGURATION DES FICHIERS DIAMEX

Les chemins des fichiers Access à importer sont configurés dans Django :

1. Accéder à : https://www.hydria.mg/admin/employees/employebasediamex/

2. Pour chaque employé, renseigner :
   - Employé : Sélectionner l'employé
   - Chemin dossier DiameX : Ex: G:\\Mon Drive\\Compta Soakoja\\
   - Nom fichier Base DiameX : Ex: DiameX v3.16.1 - Base 1.accde

3. Le chemin complet sera automatiquement généré :
   G:\\Mon Drive\\Compta Soakoja\\DiameX v3.16.1 - Base 1.accde


🐛 DÉPANNAGE

Problème : "Python n'est pas installé"
-----------------------------------------
Solution :
1. Télécharger Python depuis https://www.python.org/downloads/
2. IMPORTANT : Cocher "Add Python to PATH" lors de l'installation
3. Redémarrer l'ordinateur
4. Relancer INSTALLER_IMPORT_DIAMEX.bat


Problème : "Driver Microsoft Access non détecté"
--------------------------------------------------
Solution :
1. Si Microsoft Office installé → Le driver devrait être présent
2. Sinon, télécharger "Access Database Engine 2016 Redistributable"
3. Choisir la bonne version (32-bit OU 64-bit selon votre Office)
4. Installer et redémarrer
5. Relancer INSTALLER_IMPORT_DIAMEX.bat


Problème : "Fichier introuvable"
----------------------------------
Solution :
1. Vérifier que le chemin dans Django est correct
2. Vérifier que le fichier .accde existe bien à cet emplacement
3. Vérifier les permissions d'accès au fichier


Problème : "Erreur réseau"
---------------------------
Solution :
1. Vérifier la connexion internet
2. Vérifier que https://www.hydria.mg est accessible
3. Augmenter le TIMEOUT dans config_import.ini si la connexion est lente


Problème : "HTTP 500 - Erreur serveur"
----------------------------------------
Solution :
1. Vérifier que l'employé est bien configuré dans Django
2. Vérifier que le surnom de l'employé est correct
3. Contacter l'administrateur système


📞 SUPPORT

En cas de problème non résolu, contacter l'administrateur système avec :
- Message d'erreur complet affiché
- Capture d'écran si possible
- Contenu du fichier config_import.ini


📋 NOTES IMPORTANTES

1. L'import peut prendre plusieurs minutes selon :
   - La taille des fichiers Access
   - Le nombre de fichiers à importer
   - La vitesse de la connexion internet

2. Ne PAS fermer la fenêtre pendant l'import
   - Attendre le message "TERMINÉ"
   - Vérifier qu'il n'y a pas d'erreurs

3. Les données importées sont automatiquement :
   - Associées à votre compte employé
   - Visibles dans l'interface web Hydria
   - Sauvegardées en base de données

4. Chaque import :
   - Met à jour les données existantes (pas de doublons)
   - Crée de nouvelles entrées si nécessaire
   - Conserve l'historique des modifications


🔄 MISE À JOUR

Pour mettre à jour le package d'import :
1. Télécharger la nouvelle version
2. Remplacer les fichiers existants
3. Relancer INSTALLER_IMPORT_DIAMEX.bat (pour mettre à jour les dépendances)


📜 HISTORIQUE DES VERSIONS

Version 1.0 - Janvier 2026
- Première version portable
- Support configuration INI
- Installation automatique des dépendances
- Documentation complète


================================================================================
                            FIN DU GUIDE
================================================================================
'''

def main():
    """Crée les deux fichiers dans le répertoire courant."""
    print("=" * 80)
    print("CRÉATION DES FICHIERS LONGS SUR LE VPS")
    print("=" * 80)

    # Créer import_diamex_portable.py
    try:
        with open('import_diamex_portable.py', 'w', encoding='utf-8') as f:
            f.write(IMPORT_DIAMEX_CONTENT)
        print("[OK] Fichier 'import_diamex_portable.py' créé (309 lignes)")
    except Exception as e:
        print(f"[ERROR] Impossible de créer import_diamex_portable.py: {e}")
        return 1

    # Créer README_IMPORT_DIAMEX.txt
    try:
        with open('README_IMPORT_DIAMEX.txt', 'w', encoding='utf-8') as f:
            f.write(README_CONTENT)
        print("[OK] Fichier 'README_IMPORT_DIAMEX.txt' créé (220 lignes)")
    except Exception as e:
        print(f"[ERROR] Impossible de créer README_IMPORT_DIAMEX.txt: {e}")
        return 1

    print("\n" + "=" * 80)
    print("VÉRIFICATION")
    print("=" * 80)

    # Vérifier que les fichiers existent
    if os.path.exists('import_diamex_portable.py'):
        size1 = os.path.getsize('import_diamex_portable.py')
        print(f"✓ import_diamex_portable.py : {size1} bytes")
    else:
        print("✗ import_diamex_portable.py : FICHIER MANQUANT")

    if os.path.exists('README_IMPORT_DIAMEX.txt'):
        size2 = os.path.getsize('README_IMPORT_DIAMEX.txt')
        print(f"✓ README_IMPORT_DIAMEX.txt : {size2} bytes")
    else:
        print("✗ README_IMPORT_DIAMEX.txt : FICHIER MANQUANT")

    print("\n" + "=" * 80)
    print("PROCHAINES ÉTAPES")
    print("=" * 80)
    print("1. Vérifier que les 3 autres fichiers existent déjà :")
    print("   - INSTALLER_IMPORT_DIAMEX.bat")
    print("   - LANCER_IMPORT.bat")
    print("   - config_import.ini")
    print("\n2. Lister tous les fichiers avec :")
    print("   ls -lh *.bat *.ini *.py *.txt")
    print("\n3. Le package est maintenant complet et prêt pour le ZIP !")
    print("=" * 80)

    return 0

if __name__ == '__main__':
    exit(main())
