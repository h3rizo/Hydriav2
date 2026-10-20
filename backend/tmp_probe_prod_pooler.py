"""Tente une connexion LECTURE SEULE a la base de production via le pooler Supabase.

Le hostname direct (db.<ref>.supabase.co) ne resout pas depuis ce poste ; le pooler
partage par region, si. On essaie quelques regions usuelles.
"""
import re
from urllib.parse import urlsplit, unquote

import psycopg2

REF = 'ytqvyihgztdnwkgvozqn'
REGIONS = [
    'aws-0-eu-west-3', 'aws-1-eu-west-3', 'aws-0-eu-central-1', 'aws-1-eu-central-1',
    'aws-0-eu-west-1', 'aws-1-eu-west-1', 'aws-0-ap-southeast-1', 'aws-1-ap-southeast-1',
    'aws-0-us-east-1', 'aws-1-us-east-1',
]

dsn = None
for line in open('.env.production', encoding='utf-8'):
    m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
    if m:
        dsn = m.group(1).strip().strip('"').strip("'")
        break
parts = urlsplit(dsn)
password = unquote(parts.password or '')
dbname = parts.path.lstrip('/') or 'postgres'

for region in REGIONS:
    host = f'{region}.pooler.supabase.com'
    user = f'postgres.{REF}'
    try:
        conn = psycopg2.connect(host=host, port=5432, user=user, password=password,
                                dbname=dbname, connect_timeout=8,
                                sslmode='require')
    except Exception as exc:  # noqa: BLE001
        print(f'{host}: {str(exc).strip().splitlines()[0][:90]}')
        continue
    print(f'OK -> {host} (user={user})')
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SET statement_timeout = '150s'")
    cur.execute('SELECT pg_size_pretty(pg_total_relation_size(%s))', ('basediamex',))
    print('   taille basediamex:', cur.fetchone()[0])
    cur.execute('SELECT count(*) FROM basediamex')
    print('   lignes basediamex:', cur.fetchone()[0])
    conn.close()
    break
else:
    print('Aucun pooler joignable')
