"""Mesure la part « pointage » de la vue liste (attach_pointage) sur la base jetable.

Usage : python tmp_bench_pointage.py
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

from apps.accounting import pointage_ecritures  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402
from apps.billing.models import PaiementForfaitaire, Releve  # noqa: E402

with connection.cursor() as cur:
    for table in ('releves', 'paiements_forfaitaires', 'basediamex'):
        try:
            cur.execute(f'SELECT count(*) FROM {table}')
            print(f'{table}: {cur.fetchone()[0]} lignes')
        except Exception as exc:  # noqa: BLE001
            print(f'{table}: {exc}')

entries = list(
    BaseDiameX.objects.filter(compte_code__in=('748411', '707401'))
    .select_related('journal', 'compte').order_by('-date_m', '-id')[:50]
)
print(f'{len(entries)} ecritures 748411/707401 selectionnees')

debut = time.time()
with CaptureQueriesContext(connection) as ctx:
    pointage_ecritures.attach_pointage(entries)
duree = time.time() - debut
print(f'attach_pointage : {duree:.2f}s / {len(ctx.captured_queries)} requetes')
for query in sorted(ctx.captured_queries, key=lambda q: float(q['time']), reverse=True)[:3]:
    print(f'   {float(query["time"]):7.3f}s  {" ".join(query["sql"].split())[:150]}')
