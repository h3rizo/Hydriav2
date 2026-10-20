"""Mesure le coût du panneau « indemnités RBF » (liste des écritures 621102).

Usage : python tmp_bench_rbf.py
"""

import os
import re
import time

BENCH_DB = 'hydria_gl_bench'


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

from django.db import connection  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

from apps.accounting.models import BaseDiameX  # noqa: E402

print('Ecritures 621102 :', BaseDiameX.objects.filter(compte_code='621102').count())
premieres = list(BaseDiameX.objects.order_by('-date_m', '-id')[:50])
print('621102 dans les 50 premieres :', sum(1 for e in premieres if e.compte_code == '621102'))

debut = time.time()
from apps.core.views_ouvrage_interventions import _rbf_indemnity_lines_by_ouvrage  # noqa: E402

with CaptureQueriesContext(connection) as ctx:
    index = _rbf_indemnity_lines_by_ouvrage()
duree = time.time() - debut
print(f'_rbf_indemnity_lines_by_ouvrage : {duree:.2f}s / {len(ctx.captured_queries)} requetes')
print('ouvrages indexes :', len(index) if hasattr(index, '__len__') else '?')
if ctx.captured_queries:
    plus_lente = max(ctx.captured_queries, key=lambda q: float(q['time']))
    print(f'  plus lente : {float(plus_lente["time"]):.3f}s '
          f'{" ".join(plus_lente["sql"].split())[:160]}')
