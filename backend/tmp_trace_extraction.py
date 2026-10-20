"""Liste les requêtes qui restent pendant l'extraction en mode mémoire.

Usage : python tmp_trace_extraction.py [nb_libelles]
"""

import collections
import os
import re
import sys
import traceback

BENCH_DB = 'hydria_gl_bench'
NB = int(sys.argv[1]) if len(sys.argv) > 1 else 60


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

from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402
from apps.accounting.resolution_memoire import resolution_memoire  # noqa: E402

libelles = list(
    BaseDiameX.objects.filter(fichier_source='BENCH_RBF.MDB')
    .values_list('description', 'compte_code')[:NB]
)

compteur = collections.Counter()
piles = {}


def wrapper(execute, sql, params, many, context):
    texte = ' '.join(sql.split())
    modele = re.search(r'FROM "([a-z_]+)"', texte)
    cle = (modele.group(1) if modele else '?', texte[:110])
    compteur[cle] += 1
    if cle not in piles:
        piles[cle] = [
            f'{os.path.basename(fr.filename)}:{fr.lineno}'
            for fr in traceback.extract_stack()[:-1]
            if 'apps/' in fr.filename.replace('\\', '/')
        ][-4:]
    return execute(sql, params, many, context)


with resolution_memoire():
    with connection.execute_wrapper(wrapper):
        for description, code in libelles:
            extraire_ouvrage_et_mois_generique(description or '', code or '')

print(f'{sum(compteur.values())} requêtes pour {len(libelles)} libellés '
      f'({sum(compteur.values()) / max(len(libelles), 1):.1f} par libellé)')
for (table, sql), nombre in compteur.most_common(12):
    print(f'\n  {nombre:4d}× [{table}] {sql}')
    for ligne in piles[(table, sql)]:
        print(f'          {ligne}')
