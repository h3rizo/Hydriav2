"""Localise le blocage de _rbf_indemnity_lines_by_ouvrage (dump de pile après 20 s).

Usage : python tmp_diag_rbf_blocage.py
"""

import faulthandler
import os
import re
import sys
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
print('django prêt', flush=True)

from apps.core.views_ouvrage_interventions import _rbf_indemnity_lines_by_ouvrage  # noqa: E402

print('appel de _rbf_indemnity_lines_by_ouvrage (dump de pile dans 20 s)', flush=True)
faulthandler.dump_traceback_later(20, repeat=True)
debut = time.time()
index = _rbf_indemnity_lines_by_ouvrage()
faulthandler.cancel_dump_traceback_later()
print(f'terminé en {time.time() - debut:.2f}s, {len(index)} ouvrages', flush=True)
