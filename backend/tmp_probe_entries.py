"""Sonde lecture seule : volumetrie DiameX en production (Supabase) et en local.

Usage: python tmp_probe_entries.py [prod|local]
Aucune ecriture : uniquement des SELECT COUNT / EXPLAIN.
"""
import os
import re
import sys
import time

import psycopg2

TARGET = (sys.argv[1] if len(sys.argv) > 1 else 'local').lower()

ENV_FILE = '.env.production' if TARGET == 'prod' else '.env'
DSN = None
with open(ENV_FILE, encoding='utf-8') as fh:
    for line in fh:
        m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
        if m:
            DSN = m.group(1).strip().strip('"').strip("'")
            break

if not DSN:
    raise SystemExit(f'DATABASE_URL introuvable dans {ENV_FILE}')

print(f'Cible: {TARGET}')
conn = psycopg2.connect(DSN, connect_timeout=20)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor()
cur.execute("SET statement_timeout = '120s'")

t0 = time.time()
cur.execute('SELECT current_database(), version()')
print('DB:', cur.fetchone()[0])
print('connect+ping: %.2fs' % (time.time() - t0))


def q(label, sql, params=None, timed=True):
    t = time.time()
    cur.execute(sql, params)
    rows = cur.fetchall()
    dt = time.time() - t
    print(f'\n### {label}  ({dt:.2f}s)' if timed else f'\n### {label}')
    for r in rows[:25]:
        print('   ', r)
    if len(rows) > 25:
        print(f'    ... {len(rows)} lignes')
    return rows


q('Tables candidates', """
    SELECT table_name FROM information_schema.tables
    WHERE table_schema='public' AND table_name LIKE '%diamex%'
    ORDER BY table_name
""")

q('Colonnes de la table des ecritures', """
    SELECT column_name, data_type FROM information_schema.columns
    WHERE table_name = 'basediamex' ORDER BY ordinal_position
""")

q('Volumetrie basediamex', 'SELECT count(*) FROM basediamex')

q('Repartition par annee (date_rec)', """
    SELECT EXTRACT(YEAR FROM date_rec)::int AS annee, count(*)
    FROM basediamex
    GROUP BY 1 ORDER BY 1
""")

q('Top 15 comptes', """
    SELECT compte_code, count(*) AS n
    FROM basediamex
    GROUP BY 1 ORDER BY n DESC LIMIT 15
""")

q('Top 15 activ', """
    SELECT activ, count(*) AS n
    FROM basediamex
    GROUP BY 1 ORDER BY n DESC LIMIT 15
""")

q('Index sur basediamex', """
    SELECT indexname, indexdef FROM pg_indexes
    WHERE tablename = 'basediamex'
""")

q('Taille table + toast', """
    SELECT pg_size_pretty(pg_total_relation_size('basediamex'))
""")

q('Nb lignes avec scan', "SELECT count(*) FROM basediamex WHERE scan IS NOT NULL AND scan <> ''")
q('Nb lignes compte FK non nul', 'SELECT count(*) FROM basediamex WHERE compte_id IS NOT NULL')
q('Nb comptes', 'SELECT count(*) FROM accounting_compte')
q('Nb ouvrages', 'SELECT count(*) FROM organization_ouvrage')
q('Nb fournisseurs actifs', 'SELECT count(*) FROM billing_fournisseur WHERE actif')

t = time.time()
cur.execute("""
    EXPLAIN (ANALYZE, BUFFERS, TIMING)
    SELECT count(*) FROM basediamex
""")
print('\n### EXPLAIN count(*)')
for r in cur.fetchall():
    print('   ', r[0])
print('  (%.2fs)' % (time.time() - t))

cur.close()
conn.close()

