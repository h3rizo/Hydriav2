"""Compare la boucle d'extraction RBF avec et sans le mode « résolution en mémoire ».

Usage : python tmp_profile_rbf3.py [nb_lignes]
"""

import os
import re
import sys
import time

BENCH_DB = 'hydria_gl_bench'
LIMITE = int(sys.argv[1]) if len(sys.argv) > 1 else 500


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

from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.db import connection  # noqa: E402

from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402
from apps.accounting.resolution_memoire import (  # noqa: E402
    index_actuel, resolution_memoire, statistiques)
from apps.core.views_ouvrage_interventions import COMPTE_INDEMNITES_RBF  # noqa: E402

entrees = list(
    BaseDiameX.objects.filter(compte_code=COMPTE_INDEMNITES_RBF, montant_out__gt=0)
    .only('description', 'compte_code', 'montant_out', 'date_m').order_by('id')[:LIMITE]
)
print(f'{len(entrees)} lignes', flush=True)

print('\n--- sans mode mémoire ---', flush=True)
debut = time.time()
with CaptureQueriesContext(connection) as ctx:
    for entree in entrees:
        extraire_ouvrage_et_mois_generique(entree.description or '', entree.compte_code)
print(f'  {time.time() - debut:.2f}s, {len(ctx.captured_queries)} requêtes', flush=True)

index_actuel(force=True)
print('\n--- avec mode mémoire ---', flush=True)
debut = time.time()
with CaptureQueriesContext(connection) as ctx:
    with resolution_memoire():
        for entree in entrees:
            extraire_ouvrage_et_mois_generique(entree.description or '', entree.compte_code)
            if len(ctx.captured_queries) % 50 == 0:
                pass
print(f'  {time.time() - debut:.2f}s, {len(ctx.captured_queries)} requêtes', flush=True)
print('  compteurs :', statistiques(), flush=True)
