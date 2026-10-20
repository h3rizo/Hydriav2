"""
Script de nettoyage et reimport complet des donnees Access
Supprime toutes les donnees BaseDiameX et reimporte depuis les fichiers Access
"""

import pyodbc
import os
import sys
import django
from datetime import datetime

# Forcer l'encodage UTF-8 pour la console
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from django.db import transaction
from apps.accounting.models import BaseDiameX
from apps.organization.models import Journal, Compte
from apps.employees.models import EmployeBaseDiameX

print("=" * 80)
print("SCRIPT DE NETTOYAGE ET REIMPORT DES DONNEES ACCESS")
print("=" * 80)
print()

# Etape 1: Compter les entrees actuelles
current_count = BaseDiameX.objects.count()
print(f"Nombre d'entrees actuelles dans BaseDiameX: {current_count}")
print()

# Confirmation
print("ATTENTION: Cette operation va supprimer TOUTES les donnees actuelles et reimporter depuis les fichiers Access.")
confirmation = input("Tapez 'OUI' pour confirmer: ")

if confirmation != 'OUI':
    print("Operation annulee.")
    exit(0)

print()

# Etape 2: Supprimer toutes les donnees
print("=" * 80)
print("SUPPRESSION DES DONNEES EXISTANTES")
print("=" * 80)

try:
    deleted_count = BaseDiameX.objects.all().delete()[0]
    print(f"OK - {deleted_count} entrees supprimees")
except Exception as e:
    print(f"ERREUR lors de la suppression: {e}")
    exit(1)

print()

# Etape 3: Recuperer les chemins des fichiers Access
print("=" * 80)
print("RECHERCHE DES FICHIERS ACCESS")
print("=" * 80)

bases_employes = EmployeBaseDiameX.objects.all()
fichiers_access = []

for base in bases_employes:
    chemin = base.chemin_complet
    if chemin and os.path.exists(chemin):
        fichiers_access.append({
            'chemin': chemin,
            'nom': base.base_diamex,
            'employe': base.employe
        })
        print(f"OK - {base.base_diamex}")
        print(f"     {chemin}")
    else:
        print(f"SKIP - {base.base_diamex} (fichier introuvable)")

if not fichiers_access:
    print()
    print("ERREUR: Aucun fichier Access trouve")
    exit(1)

print()
print(f"Total fichiers a importer: {len(fichiers_access)}")
print()

# Etape 4: Import de chaque fichier
print("=" * 80)
print("IMPORT DES FICHIERS ACCESS")
print("=" * 80)
print()

total_imported = 0
total_errors = 0

for fichier_info in fichiers_access:
    file_path = fichier_info['chemin']
    fichier_nom = fichier_info['nom']
    employe = fichier_info['employe']

    print(f"Import: {fichier_nom}")
    print(f"Chemin: {file_path}")
    print()

    try:
        # Connexion au fichier Access
        conn_str = (
            r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            f'DBQ={file_path};'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Lire les donnees de la table DATA
        cursor.execute("SELECT * FROM DATA")
        columns = [column[0] for column in cursor.description]

        # Statistiques d'import
        imported_count = 0
        errors = []

        with transaction.atomic():
            for row in cursor.fetchall():
                try:
                    # Creer un dictionnaire des donnees
                    data = dict(zip(columns, row))

                    # ID Access
                    id_access = data.get('ID')
                    if not id_access:
                        continue

                    # Preparer les donnees
                    entry_data = {
                        'fichier_source': fichier_nom,
                        'id_access': id_access,
                        'journal_code': data.get('Journal'),
                        'date_m': data.get('DateM'),
                        'rec': data.get('Rec'),
                        'date_rec': data.get('DateRec'),
                        'description': data.get('Description'),
                        'montant_in': float(data.get('In') or 0),
                        'montant_out': float(data.get('Out') or 0),
                        'compte_code': data.get('Cat'),
                        'pers': data.get('PERS'),
                        'detail': data.get('Detail'),
                        'info': data.get('Info'),
                        'fin': data.get('Fin'),
                        'activ': data.get('Activ'),
                        'scan': data.get('Scan'),
                        'prog': data.get('Prog'),
                        'date_input': data.get('DateInput'),
                        'is_checked': bool(data.get('Check')),
                        'match': data.get('Match'),
                        'bank_rec': data.get('BankRec'),
                        'imported_by': employe,
                        'date_import': datetime.now(),
                    }

                    # Relier au journal si possible
                    if entry_data['journal_code']:
                        journal = Journal.objects.filter(code=entry_data['journal_code']).first()
                        if journal:
                            entry_data['journal'] = journal

                    # Relier au compte si possible
                    if entry_data['compte_code']:
                        compte = Compte.objects.filter(compte=entry_data['compte_code']).first()
                        if compte:
                            entry_data['compte'] = compte

                    # Creer l'entree
                    BaseDiameX.objects.create(**entry_data)
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Erreur ligne ID {id_access}: {str(e)}")
                    total_errors += 1

        cursor.close()
        conn.close()

        total_imported += imported_count

        print(f"  OK - {imported_count} entrees importees")
        if errors:
            print(f"  WARN - {len(errors)} erreurs:")
            for err in errors[:5]:  # Afficher les 5 premieres erreurs
                print(f"    {err}")
            if len(errors) > 5:
                print(f"    ... et {len(errors) - 5} autres erreurs")
        print()

    except Exception as e:
        print(f"  ERREUR lors de l'import du fichier: {e}")
        print()
        total_errors += 1

# Etape 5: Verification finale
print("=" * 80)
print("VERIFICATION FINALE")
print("=" * 80)

final_count = BaseDiameX.objects.count()
print(f"Total entrees importees: {final_count}")
print(f"Total erreurs: {total_errors}")
print()

# Verifier l'entree specifique ID Access 3019 dans le fichier Fenerive
print("Verification de l'entree ID Access 3019 (606100, 36000 Ar):")
entry_3019 = BaseDiameX.objects.filter(
    id_access=3019,
    fichier_source__icontains='Fenerive'
).first()

if entry_3019:
    print(f"  OK - Trouvee:")
    print(f"    ID PostgreSQL: {entry_3019.id}")
    print(f"    ID Access: {entry_3019.id_access}")
    print(f"    Fichier: {entry_3019.fichier_source}")
    print(f"    Cat: {entry_3019.compte_code}")
    print(f"    IN: {entry_3019.montant_in}")
    print(f"    OUT: {entry_3019.montant_out}")
    print(f"    Prog: {entry_3019.prog}")
else:
    print("  ERREUR - Entree non trouvee")

print()

# Statistiques par fichier
print("Statistiques par fichier:")
from django.db.models import Count

stats = BaseDiameX.objects.values('fichier_source').annotate(
    count=Count('id')
).order_by('fichier_source')

for stat in stats:
    print(f"  {stat['fichier_source']}: {stat['count']} entrees")

print()
print("=" * 80)
print("REIMPORT TERMINE")
print("=" * 80)
