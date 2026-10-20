"""
Recherche de l'entree avec Cat=606100 et montant~36000 dans Access
Pour identifier la vraie entree correspondante
"""

import pyodbc
import os
import sys
import django

# Forcer l'encodage UTF-8 pour la console
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models import EmployeBaseDiameX

# Chercher le fichier Access
bases_employes = EmployeBaseDiameX.objects.all()
access_file = None

for base in bases_employes:
    chemin = base.chemin_complet
    if chemin and os.path.exists(chemin):
        access_file = chemin
        break

if not access_file:
    print("ERREUR: Aucun fichier Access trouve")
    exit(1)

print("Fichier Access:", access_file)
print()

try:
    conn_str = (
        r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
        f'DBQ={access_file};'
    )
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    # Chercher l'entree avec Cat=606100 et prog=EHA-Soakoja-Fenerive Est
    print("=" * 80)
    print("RECHERCHE: Cat=606100 + Prog=EHA-Soakoja-Fenerive Est")
    print("=" * 80)

    cursor.execute("""
        SELECT ID, Journal, Cat, DateM, DateRec, Rec, [In], [Out], Prog, Description
        FROM DATA
        WHERE Cat = '606100'
        AND Prog LIKE '%EHA-Soakoja-Fenerive Est%'
        ORDER BY DateM DESC
    """)

    rows = cursor.fetchall()

    if rows:
        print(f"Nombre d'entrees trouvees: {len(rows)}")
        print()
        for row in rows:
            print(f"ID Access: {row[0]}")
            print(f"Journal: {row[1]}")
            print(f"Cat: {row[2]}")
            print(f"DateM: {row[3]}")
            print(f"DateRec: {row[4]}")
            print(f"Rec: {row[5]}")
            print(f"IN: {row[6]}")
            print(f"OUT: {row[7]}")
            print(f"Prog: {row[8]}")
            print(f"Description: {row[9]}")
            print("-" * 80)
    else:
        print("Aucune entree trouvee")
        print()

        # Chercher juste avec Cat=606100
        print("=" * 80)
        print("RECHERCHE ELARGIE: Cat=606100 (tous Prog)")
        print("=" * 80)

        cursor.execute("""
            SELECT TOP 20 ID, Journal, Cat, DateM, [In], [Out], Prog
            FROM DATA
            WHERE Cat = '606100'
            ORDER BY DateM DESC
        """)

        rows = cursor.fetchall()
        if rows:
            print(f"Nombre d'entrees trouvees: {len(rows)}")
            print()
            for row in rows:
                print(f"ID={row[0]}, Journal={row[1]}, Cat={row[2]}, DateM={row[3]}, IN={row[4]}, OUT={row[5]}, Prog={row[6]}")
        else:
            print("Aucune entree trouvee avec Cat=606100")

    # Chercher avec montant OUT proche de 36000
    print()
    print("=" * 80)
    print("RECHERCHE: Montant OUT proche de 36000")
    print("=" * 80)

    cursor.execute("""
        SELECT ID, Journal, Cat, DateM, [In], [Out], Prog
        FROM DATA
        WHERE [Out] BETWEEN 35000 AND 37000
        AND Prog LIKE '%EHA-Soakoja-Fenerive Est%'
        ORDER BY DateM DESC
    """)

    rows = cursor.fetchall()
    if rows:
        print(f"Nombre d'entrees trouvees: {len(rows)}")
        print()
        for row in rows:
            print(f"ID={row[0]}, Journal={row[1]}, Cat={row[2]}, DateM={row[3]}, IN={row[4]}, OUT={row[5]}, Prog={row[6]}")
    else:
        print("Aucune entree trouvee")

    # Verifier l'etendue des IDs dans la base Access
    print()
    print("=" * 80)
    print("STATISTIQUES DE LA BASE ACCESS")
    print("=" * 80)

    cursor.execute("SELECT MIN(ID) as MinID, MAX(ID) as MaxID, COUNT(*) as Total FROM DATA")
    row = cursor.fetchone()
    print(f"ID minimum: {row[0]}")
    print(f"ID maximum: {row[1]}")
    print(f"Total entrees: {row[2]}")
    print()
    print(f"L'ID 4592 devrait {'exister' if row[0] <= 4592 <= row[1] else 'NE PAS exister'} dans cette plage")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"ERREUR: {e}")
    import traceback
    traceback.print_exc()
