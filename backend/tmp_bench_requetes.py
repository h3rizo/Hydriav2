"""Compte les requêtes par libellé, avant / après la résolution en mémoire.

Usage : python tmp_bench_requetes.py [nb_libelles]
"""

import contextlib
import os
import re
import sys
import time

BENCH_DB = 'hydria_gl_bench'
NB = int(sys.argv[1]) if len(sys.argv) > 1 else 300


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

from apps.accounting import resolution_memoire as rm  # noqa: E402
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402

connection.queries_limit = 5_000_000  # comptage exact (la limite Django tronque à 9 000)

libelles = list(
    BaseDiameX.objects.filter(fichier_source='BENCH_RBF.MDB')
    .values_list('description', 'compte_code')[:NB]
)
print(f'{len(libelles)} libellés RBF')


def mesurer(label, contexte):
    with contexte():
        debut = time.time()
        with connection.execute_wrapper(_compteur):
            for description, code in libelles:
                extraire_ouvrage_et_mois_generique(description or '', code or '')
        duree = time.time() - debut
    print(f'  {label:<34} {duree:6.2f}s   {_total[0]:6d} requêtes '
          f'({_total[0] / max(len(libelles), 1):.2f} par libellé)')


_total = [0]


def _compteur(execute, sql, params, many, context):
    _total[0] += 1
    return execute(sql, params, many, context)


rm.index_actuel(force=True)
mesurer('avant (résolution en base)', contextlib.nullcontext)
_total[0] = 0
mesurer('après (résolution en mémoire)', rm.resolution_memoire)
print('  compteurs internes :', rm.statistiques())
