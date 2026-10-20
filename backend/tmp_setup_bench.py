"""Prepare une base jetable `hydria_gl_bench` (copie de hydria) + migrations.

Aucune ecriture dans `hydria`. Toutes les sorties vont dans des fichiers
(pas de pipes : le sandbox Windows les refuse).
"""
import os
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit, unquote, quote

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

BENCH_DB = 'hydria_gl_bench'
PG_BIN = r'C:\Program Files\PostgreSQL\17\bin'
LOG = os.path.join('tmp_bench', 'setup.log')


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    os.makedirs('tmp_bench', exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as fh:
        fh.write(line + '\n')


def read_dsn(env_file='.env'):
    for line in open(env_file, encoding='utf-8'):
        m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit('DATABASE_URL absente de .env')


def main():
    dsn = read_dsn()
    parts = urlsplit(dsn)
    user = unquote(parts.username or '')
    password = unquote(parts.password or '')
    host = parts.hostname or 'localhost'
    port = parts.port or 5432
    base_path = parts.path.lstrip('/')

    log(f'Source: {user}@{host}:{port}/{base_path} (mot de passe non affiche)')

    admin_dsn = f"host={host} port={port} user={user} password={password} dbname=postgres"
    conn = psycopg2.connect(admin_dsn, connect_timeout=15)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s', (BENCH_DB,))
    cur.execute(f'DROP DATABASE IF EXISTS {BENCH_DB}')
    cur.execute(f'CREATE DATABASE {BENCH_DB}')
    cur.close()
    conn.close()
    log(f'Base {BENCH_DB} creee')

    env = dict(os.environ)
    env['PGPASSWORD'] = password
    dump_file = os.path.join('tmp_bench', 'dump.sql')

    with open(os.path.join('tmp_bench', 'pg_dump.log'), 'w', encoding='utf-8') as out:
        rc = subprocess.run(
            [os.path.join(PG_BIN, 'pg_dump.exe'), '-h', host, '-p', str(port), '-U', user,
             '-d', base_path, '-f', dump_file, '--no-owner', '--no-privileges'],
            env=env, stdout=out, stderr=subprocess.STDOUT,
        ).returncode
    log(f'pg_dump rc={rc} taille={os.path.getsize(dump_file) / 1e6:.1f} Mo')
    if rc != 0:
        raise SystemExit('pg_dump a echoue')

    with open(os.path.join('tmp_bench', 'psql_restore.log'), 'w', encoding='utf-8') as out:
        rc = subprocess.run(
            [os.path.join(PG_BIN, 'psql.exe'), '-h', host, '-p', str(port), '-U', user,
             '-d', BENCH_DB, '-v', 'ON_ERROR_STOP=0', '-f', dump_file, '-q'],
            env=env, stdout=out, stderr=subprocess.STDOUT,
        ).returncode
    log(f'psql restore rc={rc}')

    bench_dsn = parts._replace(path='/' + BENCH_DB).geturl()
    env_migrate = dict(os.environ)
    env_migrate['DATABASE_URL'] = bench_dsn
    with open(os.path.join('tmp_bench', 'migrate.log'), 'w', encoding='utf-8') as out:
        rc = subprocess.run(
            [os.path.join('..', '.venv', 'Scripts', 'python.exe'), 'manage.py', 'migrate', '--noinput'],
            env=env_migrate, stdout=out, stderr=subprocess.STDOUT, cwd=os.getcwd(),
        ).returncode
    log(f'migrate rc={rc}')

    conn = psycopg2.connect(bench_dsn, connect_timeout=15)
    cur = conn.cursor()
    cur.execute('SELECT count(*) FROM basediamex')
    log(f'basediamex dans {BENCH_DB}: {cur.fetchone()[0]}')
    cur.close()
    conn.close()
    log('TERMINE')


if __name__ == '__main__':
    sys.exit(main())
