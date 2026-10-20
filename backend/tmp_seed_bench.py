"""Génère un jeu d'écritures DiameX synthétique dans la base jetable ``hydria_gl_bench``.

But : mesurer la vue « grand livre » à volume réaliste et comparer l'ancienne
agrégation Python à la nouvelle agrégation SQL. Le script refuse toute autre base
que ``hydria_gl_bench`` : aucune écriture dans ``hydria``.

Usage : python tmp_seed_bench.py [nombre_d_ecritures]
"""

import json
import random
import re
import sys
import time

import psycopg2

BENCH_DB = 'hydria_gl_bench'
TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 120000


def read_dsn(env_file='.env'):
    for line in open(env_file, encoding='utf-8'):
        m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit('DATABASE_URL absente de .env')


dsn = read_dsn()
if dsn.rstrip('/').endswith('/' + BENCH_DB):
    pass
elif dsn.rstrip('/').endswith('/hydria'):
    dsn = dsn.rstrip('/')[:-len('/hydria')] + '/' + BENCH_DB
else:
    raise SystemExit(f'Refus : base source inattendue ({dsn})')
if not dsn.rstrip('/').endswith(BENCH_DB):
    raise SystemExit(f'Refus : la base cible doit etre {BENCH_DB}')

t0 = time.time()
conn = psycopg2.connect(dsn, connect_timeout=20)
cur = conn.cursor()
cur.execute('SET statement_timeout = 0')
cur.execute('DELETE FROM basediamex')

cur.execute("SELECT id, employe_obligatoire, fournisseur_obligatoire, necessite_ouvrage FROM comptes")
comptes = cur.fetchall()
cur.execute('SELECT id FROM journaux')
journaux = [r[0] for r in cur.fetchall()]
cur.execute('SELECT id FROM employes')
employes = [r[0] for r in cur.fetchall()]
print(f'references: {len(comptes)} comptes, {len(journaux)} journaux, {len(employes)} employes')

ACTIVS = ['AEP', 'Forage', 'BP', 'Adduction', None, '', '  aep  ', 'Extension']
FINS = ['Bailleur A', 'Bailleur B', 'Budget', None, '', 'FND1-EDF', 'fnd1-edf', 'Fonds propre']
CODES = [
    '707401', '748411', '748415', '748201', '621102', '625107', '761000', '761002',
    '606100', '626100', '641000', '646000', '627000', '411000', '521000',
    '00BOOK01', '00FND1XX', '00FND2YY', '00PERS01', '00PERS02',
]
DESCRIPTIONS = [
    'NIF123_MADAGASCAR EAU_ACHAT FOURNITURE DIVERSES',
    'ISI456_SOCIETE FORAGE_TRAVAUX DE FORAGE AMPASINA',
    'Paiement volume Ambato janvier 2025',
    'Paiement forfaitaire Ambohidratrimo 2025',
    'Indemnite RBF PPMH point d eau Antsirabe',
    'Salaire du mois de janvier 2025',
    'CNAPS cotisations',
    'Frais de deplacement mission',
    'Transfert de fonds 00BOOK vers caisse',
    'Recette vente eau au volume',
    'Achat carburant vehicule',
    'EdF eclairage public janvier',
]

random.seed(20261014)
rows = []
for index in range(TOTAL):
    code = random.choice(CODES)
    montant_in = round(random.uniform(0, 900000), 2) if random.random() < 0.55 else 0.0
    montant_out = round(random.uniform(0, 900000), 2) if montant_in == 0 else (
        round(random.uniform(0, 50000), 2) if random.random() < 0.1 else 0.0)
    # 3 écritures sur 4 portent leur clé étrangère de compte (comme après un import complet)
    compte_id = random.choice(comptes)[0] if random.random() < 0.75 else None
    journal_id = random.choice(journaux) if random.random() < 0.75 else None
    rows.append((
        index + 1,
        random.choice(['DIAMEX_MG_2024.MDB', 'DIAMEX_MG_2025.MDB', 'DIAMEX_ITASY.MDB']),
        random.choice(['701', '702', '601', 'CAI', 'BQ1']),
        f'2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}',
        random.choice([None, index, 1000 + index]),
        f'2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}',
        random.choice(DESCRIPTIONS),
        montant_in,
        montant_out,
        code,
        random.choice([None, 'TIERS1', 'TIERS2']),
        random.choice([None, 'DEPLACEMENT', 'CARBURANT', 'SALAIRE']),
        random.choice([None, 'info complementaire']),
        random.choice(FINS),
        random.choice(ACTIVS),
        random.choice([None, './scans/2024/a.pdf', 'C:\\DIAMEX\\scans\\b.pdf']),
        'DIAMEX',
        f'2024-{random.randint(1, 12):02d}-15',
        random.choice(employes) if employes else None,
        False,
        compte_id,
        journal_id,
    ))

cur.executemany(
    """
    INSERT INTO basediamex (
        id_access, fichier_source, journal_code, date_m, rec, date_rec, description,
        montant_in, montant_out, compte_code, pers, detail, info, fin, activ, scan, prog,
        date_import, imported_by_id, "check", compte_id, journal_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """,
    rows,
)
conn.commit()
cur.execute('SELECT count(*) FROM basediamex')
print(f'{cur.fetchone()[0]} ecritures inserees en {time.time() - t0:.1f}s')

# Cache de vérification des scans volumineux : c'est ce qui fait exploser les
# requêtes « id IN (…) » de la vue grand livre.
cur.execute('SELECT id, scan FROM basediamex ORDER BY id')
all_rows = cur.fetchall()
with_scan = [r[0] for r in all_rows if r[1]]
valid_ids = with_scan[:45000]
dead_ids = with_scan[45000:60000]
cur.execute('DELETE FROM scan_verification_cache')
cur.execute(
    """
    INSERT INTO scan_verification_cache (
        date_verification, fichier_source, scans_valides_count, liens_morts_count,
        operations_sans_scan_count, operations_total_count, scans_valides_ids,
        liens_morts_ids, statut, message_erreur
    ) VALUES (now(), NULL, %s, %s, 0, 0, %s::jsonb, %s::jsonb, 'termine', NULL)
    """,
    (len(valid_ids), len(dead_ids), json.dumps(valid_ids), json.dumps(dead_ids)),
)
conn.commit()
print(f'cache de verification : {len(valid_ids)} scans valides / {len(dead_ids)} liens morts')
conn.close()
