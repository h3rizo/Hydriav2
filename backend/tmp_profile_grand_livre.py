"""Diagnostic : requêtes SQL les plus lentes d'un rendu de la vue grand livre.

Usage : python tmp_profile_grand_livre.py [url_suffixe]
"""

import os
import re
import sys
import time

BENCH_DB = 'hydria_gl_bench'
SUFFIXE = sys.argv[1] if len(sys.argv) > 1 else 'view_mode=grand_livre'


def read_dsn(env_file='.env'):
    for line in open(env_file, encoding='utf-8'):
        m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit('DATABASE_URL absente')


dsn = read_dsn().rstrip('/')
assert dsn.endswith('/hydria')
dsn = dsn[:-len('/hydria')] + '/' + BENCH_DB
os.environ['DATABASE_URL'] = dsn
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext, setup_test_environment  # noqa: E402

setup_test_environment()

User = get_user_model()
user, _ = User.objects.get_or_create(
    username='bench_gl',
    defaults={'is_superuser': True, 'is_staff': True, 'email': 'bench@example.com'})
user.is_superuser = True
user.is_staff = True
user.set_password('bench-only')
user.save()

client = Client()
client.force_login(user)

url = '/comptabilite/entries/?' + SUFFIXE
started = time.time()
with CaptureQueriesContext(connection) as ctx:
    response = client.get(url, HTTP_HOST='compta.hydria.mg')
elapsed = time.time() - started
print(f'GET {url}')
print(f'  status={response.status_code} duree={elapsed:.2f}s '
      f'requetes={len(ctx.captured_queries)} rendu={len(response.content) / 1024:.0f} Ko')

queries = sorted(ctx.captured_queries, key=lambda q: float(q['time']), reverse=True)
total_sql = sum(float(q['time']) for q in ctx.captured_queries)
print(f'  temps SQL cumule = {total_sql:.2f}s (soit {total_sql / elapsed * 100:.0f}% de la duree)')
print('\n  Top 12 requetes les plus lentes :')
for query in queries[:12]:
    sql = ' '.join(query['sql'].split())
    print(f'    {float(query["time"]):7.3f}s  {sql[:180]}')
