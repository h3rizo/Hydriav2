"""
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
from configparser import ConfigParser, Error as ConfigParserError
from urllib.parse import urlsplit

# Charger la configuration depuis le fichier INI
config = ConfigParser()
config_file = 'config_import.ini'

if not os.path.exists(config_file):
    print(f"[ERROR] Fichier de configuration '{config_file}' introuvable")
    print(f"[INFO] Assurez-vous que {config_file} est dans le même dossier que ce script")
    sys.exit(1)

try:
    config.read(config_file, encoding='utf-8')
except ConfigParserError as e:
    print(f"[ERROR] Le fichier '{config_file}' est invalide: {e}")
    print("[INFO] Verifiez qu'une meme option n'apparait pas deux fois dans une section.")
    sys.exit(1)

# Lire les paramètres de configuration
try:
    DJANGO_URL = config.get('SERVEUR', 'DJANGO_URL')
    TIMEOUT = config.getint('OPTIONS', 'TIMEOUT', fallback=300)
    VERBOSE = config.getboolean('OPTIONS', 'VERBOSE', fallback=True)
    IMPORT_BATCH_SIZE = config.getint('OPTIONS', 'IMPORT_BATCH_SIZE', fallback=1000)
except Exception as e:
    print(f"[ERROR] Erreur lors de la lecture de la configuration: {e}")
    sys.exit(1)


def _normalize_base_url(url, fallback):
    value = str(url or '').strip().rstrip('/')
    if not value:
        return fallback
    if '://' not in value:
        value = f'https://{value}'
    return value.rstrip('/')


def _derive_scan_api_url(base_url):
    parsed = urlsplit(base_url)
    host = (parsed.netloc or '').lower()
    scheme = parsed.scheme or 'https'
    if host == 'compta.hydria.mg':
        return f'{scheme}://compta.hydria.mg'
    if host.endswith('hydria.mg'):
        return f'{scheme}://compta.hydria.mg'
    return base_url.rstrip('/')


IMPORT_API_URL = _normalize_base_url(DJANGO_URL, 'https://www.hydria.mg')
SCAN_API_URL = _normalize_base_url(
    config.get('SERVEUR', 'SCAN_API_URL', fallback=''),
    _derive_scan_api_url(IMPORT_API_URL),
)

AGENT_TOKEN = config.get('SERVEUR', 'AGENT_TOKEN', fallback='').strip()
AUTH_HEADERS = {'Authorization': f'Token {AGENT_TOKEN}'} if AGENT_TOKEN else {}


def log_progress(message):
    """Affiche un message de progression si VERBOSE est activé"""
    if VERBOSE:
        print(message)


def _sanitize_import_batch_size(batch_size):
    try:
        value = int(batch_size)
    except (TypeError, ValueError):
        value = 1000
    return max(100, min(value, 5000))

def _normalize_selected_months(selected_months=None):
    normalized = set()
    for item in selected_months or []:
        value = str(item or '').strip()
        if len(value) == 7 and value[4] == '-':
            normalized.add(value)
    return normalized


def _row_month_key(row_dict):
    date_value = row_dict.get('DateM')
    if not date_value:
        return ''
    if hasattr(date_value, 'strftime'):
        return date_value.strftime('%Y-%m')
    value = str(date_value).strip()
    if len(value) >= 7 and value[4] == '-':
        return value[:7]
    return ''


def lire_access_local(file_path, selected_months=None):
    """
    Lit un fichier Access LOCAL et retourne les données des tables DATA et SoldesReels.

    Args:
        file_path: Chemin complet vers le fichier .accde (ex: G:/.../file.accde)

    Returns:
        dict: {'data_rows': [...], 'soldes_rows': [...]}
    """
    log_progress(f"[READ] Lecture du fichier Access: {file_path}")
    selected_months_set = _normalize_selected_months(selected_months)
    if selected_months_set:
        log_progress("[FILTER] Mois selectionnes: " + ", ".join(sorted(selected_months_set)))

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
                    row_dict[key] = value.replace('\xa0', ' ').strip()
            month_key = _row_month_key(row_dict)
            if selected_months_set and month_key not in selected_months_set:
                continue
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
                        row_dict[key] = value.replace('\xa0', ' ').strip()
                month_key = _row_month_key(row_dict)
                if selected_months_set and month_key not in selected_months_set:
                    continue
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
    log_progress(f"[SEND] Envoi vers Django: {IMPORT_API_URL}/comptabilite/api/import-from-access/")
    log_progress(f"[INFO] Employé: {employe_surnom}")

    session = requests.Session()
    batch_size = _sanitize_import_batch_size(IMPORT_BATCH_SIZE)
    data_rows = list(data.get('data_rows') or [])
    soldes_rows = list(data.get('soldes_rows') or [])
    chunk_count = max(1, (len(data_rows) + batch_size - 1) // batch_size)
    all_entry_keys = [
        {'prog': row.get('Prog'), 'id_access': row.get('ID')}
        for row in data_rows
        if row.get('ID') is not None
    ]

    try:
        for chunk_index, start in enumerate(range(0, len(data_rows) or 1, batch_size), start=1):
            data_chunk = data_rows[start:start + batch_size] if data_rows else []
            soldes_chunk = soldes_rows if chunk_index == 1 else []
            post_data = {
                'file_path': file_path,
                'fichier_nom': fichier_nom,
                'data_rows': json.dumps(data_chunk),
                'soldes_rows': json.dumps(soldes_chunk),
                'employe_surnom': employe_surnom,
                'chunk_index': str(chunk_index),
                'chunk_count': str(chunk_count),
            }
            if chunk_index == chunk_count:
                post_data['all_entry_keys'] = json.dumps(all_entry_keys)

            log_progress(
                f"[SEND] Lot {chunk_index}/{chunk_count}: {len(data_chunk)} lignes DATA, "
                f"{len(soldes_chunk)} lignes SoldesReels"
            )
            response = session.post(
                f'{IMPORT_API_URL}/comptabilite/api/import-from-access/',
                data=post_data,
                headers=AUTH_HEADERS,
                timeout=TIMEOUT
            )

            log_progress(f"[OK] Réponse HTTP {response.status_code} sur lot {chunk_index}/{chunk_count}")

            if response.status_code != 200:
                print(f"[ERROR] HTTP {response.status_code}: {response.text[:500]}")
                return False

            result = response.json()
            if not result.get('success'):
                print(f"[ERROR] {result.get('error')}")
                return False

            log_progress(f"[SUCCESS] {result.get('message')}")
            log_progress(f"Stats: {result.get('stats')}")
            errors = result.get('errors', [])
            if errors:
                log_progress(f"[WARNING] {len(errors)} erreur(s) détectée(s):")
                for i, error in enumerate(errors, 1):
                    log_progress(f"  {i}. {error}")

        return True
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
            f'{IMPORT_API_URL}/api/bases-diamex/',
            headers=AUTH_HEADERS,
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
        print(f"\n[INFO] Mode fichier unique: {fichier_nom}")
    else:
        # Récupérer la liste des fichiers depuis l'API Django
        fichiers = recuperer_fichiers_depuis_api()

        if not fichiers:
            print("\n[ERROR] Aucun fichier à importer. Vérifiez la configuration dans Django.")
            print("[INFO] Vous pouvez aussi spécifier un fichier en argument:")
            print('       python import_diamex_portable.py "C:\\chemin\\vers\\fichier.accde"')
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
