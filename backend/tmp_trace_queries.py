"""Identifie l'origine Python des requêtes SQL d'un rendu (traceback par requête).

Usage : python tmp_trace_queries.py [url_suffixe] [motif_sql]
"""

import os
import re
import sys
import time
import traceback

BENCH_DB = 'hydria_gl_bench'
SUFFIXE = sys.argv[1] if len(sys.argv) > 1 else 'view_mode=grand_livre'
MOTIF = sys.argv[2] if len(sys.argv) > 2 else '641'


def read_dsn(env_file='.env'):
    for line in open(env_file, encoding='utf-8'):
        m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit('DATABASE_URL absente')


dsn = read_dsn().rstrip('/')
dsn = dsn[:-len('/hydria')] + '/' + BENCH_DB
os.environ['DATABASE_URL'] = dsn
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
User = get_user_model()
user, _ = User.objects.get_or_create(
    username='bench_gl',
    defaults={'is_superuser': True, 'is_staff': True, 'email': 'bench@example.com'})
user.is_superuser = True
user.is_staff = True
user.set_password('bench-only')
user.save()

origines = []


def wrapper(execute, sql, params, many, context):
    texte = ' '.join(sql.split())
    if MOTIF in texte or (params and MOTIF in str(params)):
        pile = [
            f'{os.path.basename(fr.filename)}:{fr.lineno}:{fr.name}'
            for fr in traceback.extract_stack()[:-1]
            if 'django' not in fr.filename or 'apps' in fr.filename
        ]
        origines.append((texte, str(params)[:220], pile[-6:]))
    return execute(sql, params, many, context)


client = Client()
client.force_login(user)
with connection.execute_wrapper(wrapper):
    debut = time.time()
    response = client.get('/comptabilite/entries/?' + SUFFIXE, HTTP_HOST='compta.hydria.mg')
print(f'GET {SUFFIXE} -> {response.status_code} en {time.time() - debut:.2f}s')
print(f'{len(origines)} requetes contenant {MOTIF!r}')
for sql, params, pile in origines[:8]:
    print('\n  SQL    :', sql[:150])
    print('  PARAMS :', params)
    print('  PILE   :')
    for ligne in pile:
        print('          ', ligne)
