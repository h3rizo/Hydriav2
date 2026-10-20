"""
Script Python pour lire un fichier Access LOCAL (Windows)
et envoyer les données vers Django via API.

Usage:
    python import_access_local.py

Le script :
1. Lit les fichiers Access depuis EmployeBaseDiameX (chemins G:...)
2. Extrait les tables DATA et SoldesReels
3. Envoie en JSON vers /comptabilite/api/import-from-access/
"""
import pyodbc
import json
import requests
import sys
import os
from decimal import Decimal

# Configuration
DJANGO_URL = 'https://www.hydria.mg'  # URL du serveur Django
# DJANGO_URL = 'http://localhost:8000'  # Pour tests locaux

# Note: Le surnom de l'employé sera récupéré automatiquement depuis l'API
# pour chaque fichier importé (pas besoin de configuration manuelle)

def lire_access_local(file_path):
    """
    Lit un fichier Access LOCAL et retourne les données des tables DATA et SoldesReels.

    Args:
        file_path: Chemin complet vers le fichier .accde (ex: G:/.../file.accde)

    Returns:
        dict: {'data_rows': [...], 'soldes_rows': [...]}
    """
    print(f"[READ] Lecture du fichier Access: {file_path}")

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
        print("[READ] Lecture table DATA...")
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
                    row_dict[key] = value.replace('\xa0', ' ').strip()
            data_rows.append(row_dict)

        print(f"[OK] {len(data_rows)} lignes DATA lues")

        # ========== TABLE SoldesReels ==========
        soldes_rows = []
        try:
            print("[READ] Lecture table SoldesReels...")
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
                        row_dict[key] = value.replace('\xa0', ' ').strip()
                soldes_rows.append(row_dict)

            print(f"[OK] {len(soldes_rows)} lignes SoldesReels lues")
        except pyodbc.Error:
            print("[WARNING] Table SoldesReels introuvable (ignorée)")

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
    print(f"[SEND] Envoi vers Django: {DJANGO_URL}/comptabilite/api/import-from-access/")
    print(f"[INFO] Employé: {employe_surnom}")

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

    # Si vous avez besoin d'authentification, ajoutez-la ici
    # session.auth = ('username', 'password')
    # Ou avec cookie de session Django:
    # session.cookies.set('sessionid', 'votre_session_id')

    try:
        response = session.post(
            f'{DJANGO_URL}/comptabilite/api/import-from-access/',
            data=post_data,
            timeout=300  # 5 minutes timeout (import peut être long)
        )

        print(f"[OK] Réponse HTTP {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"[SUCCESS] {result.get('message')}")
                print(f"Stats: {result.get('stats')}")
                # Afficher les erreurs s'il y en a
                errors = result.get('errors', [])
                if errors:
                    print(f"[WARNING] {len(errors)} erreur(s) détectée(s):")
                    for i, error in enumerate(errors, 1):
                        print(f"  {i}. {error}")
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
        list: Liste de dict avec 'path' et 'nom'
    """
    print("[API] Récupération de la liste des fichiers depuis Django...")

    try:
        # Session pour gérer les cookies (si authentification)
        session = requests.Session()

        # Appel API pour obtenir la liste des bases DiameX
        response = session.get(
            f'{DJANGO_URL}/api/bases-diamex/',  # Fixed: URL path without /employes/ prefix
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                fichiers = data.get('fichiers', [])
                print(f"[OK] {len(fichiers)} fichier(s) récupéré(s) depuis l'API")

                # Afficher la liste
                for idx, fichier in enumerate(fichiers, 1):
                    print(f"   {idx}. {fichier['nom']}")

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
    print("IMPORT DIAMEX LOCAL -> DJANGO")
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
        print(f"\n[INFO] Mode fichier unique: {fichier_nom}")
    else:
        # Récupérer la liste des fichiers depuis l'API Django
        fichiers = recuperer_fichiers_depuis_api()

        if not fichiers:
            print("\n[ERROR] Aucun fichier à importer. Vérifiez la configuration dans Django.")
            print("[INFO] Vous pouvez aussi spécifier un fichier en argument:")
            print('       python import_access_local.py "C:\\chemin\\vers\\fichier.accde"')
            sys.exit(1)

    # Traiter chaque fichier
    for fichier in fichiers:
        print(f"\n{'='*60}")
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

    print("\n" + "="*60)
    print("TERMINÉ")
    print("="*60)

if __name__ == '__main__':
    main()
