"""
Verification de l'entree ID Access 3019 dans le fichier Fenerive
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

# Chercher le fichier Fenerive directement
access_file = r"G:\.shortcut-targets-by-id\13R7xs4jr8LMLiOLUOPtHpaYiPha2gKdw\HYDRAU SOAKOJA\SKJ FENERIVE\03 COMPTA\DiameX v3.16.1 - 1 - Soakoja Fénérive 20251014 RAF (2).accde"

if not access_file:
    print("ERREUR: Fichier Fenerive introuvable")
    exit(1)

print(f"Fichier Fenerive: {access_file}")
print()

try:
    conn_str = (
        r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
        f'DBQ={access_file};'
    )
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    # Chercher l'ID 3019
    print("=" * 80)
    print("RECHERCHE ID 3019 DANS FENERIVE")
    print("=" * 80)

    cursor.execute("SELECT * FROM DATA WHERE ID = 3019")
    columns = [column[0] for column in cursor.description]
    row = cursor.fetchone()

    if row:
        data = dict(zip(columns, row))
        print("ENTREE TROUVEE:")
        print(f"  ID: {data.get('ID')}")
        print(f"  Journal: {data.get('Journal')}")
        print(f"  Cat: {data.get('Cat')}")
        print(f"  DateM: {data.get('DateM')}")
        print(f"  IN: {data.get('In')}")
        print(f"  OUT: {data.get('Out')}")
        print(f"  Prog: {data.get('Prog')}")
        print(f"  Description: {data.get('Description')}")
    else:
        print("AUCUNE ENTREE avec ID=3019")
        print()

        # Chercher les IDs proches
        cursor.execute("SELECT TOP 10 ID, Journal, Cat, [In], [Out], Prog FROM DATA WHERE ID >= 3015 AND ID <= 3025 ORDER BY ID")
        rows = cursor.fetchall()

        if rows:
            print("IDs proches de 3019:")
            for r in rows:
                print(f"  ID={r[0]}, Journal={r[1]}, Cat={r[2]}, IN={r[3]}, OUT={r[4]}, Prog={r[5]}")
        else:
            print("Aucun ID proche trouve")

    print()

    # Chercher Cat=606100 avec montant 36000
    print("=" * 80)
    print("RECHERCHE Cat=606100 avec OUT=36000")
    print("=" * 80)

    cursor.execute("""
        SELECT ID, Journal, Cat, DateM, [In], [Out], Prog, Description
        FROM DATA
        WHERE Cat = '606100'
        AND [Out] BETWEEN 35900 AND 36100
        ORDER BY DateM DESC
    """)

    rows = cursor.fetchall()

    if rows:
        print(f"Nombre d'entrees trouvees: {len(rows)}")
        print()
        for r in rows:
            print(f"ID={r[0]}, Journal={r[1]}, Cat={r[2]}, DateM={r[3]}, IN={r[4]}, OUT={r[5]}")
            print(f"  Prog: {r[6]}")
            print(f"  Description: {r[7][:80] if r[7] else ''}")
            print()
    else:
        print("Aucune entree trouvee")

    # Statistiques du fichier
    print("=" * 80)
    print("STATISTIQUES DU FICHIER")
    print("=" * 80)

    cursor.execute("SELECT MIN(ID) as MinID, MAX(ID) as MaxID, COUNT(*) as Total FROM DATA")
    row = cursor.fetchone()
    print(f"ID minimum: {row[0]}")
    print(f"ID maximum: {row[1]}")
    print(f"Total entrees: {row[2]}")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"ERREUR: {e}")
    import traceback
    traceback.print_exc()
