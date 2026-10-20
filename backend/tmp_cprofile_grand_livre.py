"""Profil Python (cProfile) d'un rendu de la vue grand livre.

Usage : python tmp_cprofile_grand_livre.py [url_suffixe]
"""

import cProfile
import io
import os
import pstats
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
dsn = dsn[:-len('/hydria')] + '/' + BENCH_DB
os.environ['DATABASE_URL'] = dsn
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
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

client = Client()
client.force_login(user)
url = '/comptabilite/entries/?' + SUFFIXE

started = time.time()
with cProfile.Profile() as profile:
    response = client.get(url, HTTP_HOST='compta.hydria.mg')
elapsed = time.time() - started
print(f'GET {url} -> {response.status_code} en {elapsed:.2f}s')

stream = io.StringIO()
stats = pstats.Stats(profile, stream=stream).sort_stats('cumulative')
stats.print_stats(28)
print(stream.getvalue())
