"""Quelles recherches coûtent le plus pendant l'extraction (nb d'objets parcourus) ?

Usage : python tmp_diag_cout_resolution.py [nb_libelles]
"""

import collections
import os
import re
import sys
import time

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

from apps.accounting import resolution_memoire as rm  # noqa: E402
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402

libelles = list(
    BaseDiameX.objects.filter(fichier_source='BENCH_RBF.MDB')
    .values_list('description', 'compte_code')[:NB]
)

appels = collections.Counter()
parcourus = collections.Counter()
duree = collections.Counter()
_iterer_original = rm._iterer


def _iterer_instrumente(conditions, modele_nom, index):
    description = f'{modele_nom} ' + ' & '.join(
        f'{champ}__{lookup}' for champ, lookup, _ in conditions)
    debut = time.perf_counter()
    resultat = _iterer_original(conditions, modele_nom, index)
    duree[description] += time.perf_counter() - debut
    appels[description] += 1
    parcourus[description] += len(resultat[0])
    return resultat


rm._iterer = _iterer_instrumente

with rm.resolution_memoire():
    for libelle in libelles:
        extraire_ouvrage_et_mois_generique(libelle, '621102')

print(f'{len(libelles)} libellés')
print(f'\n{"recherche":<60} {"appels":>7} {"objets":>9} {"ms total":>10}')
for description, nombre in appels.most_common(12):
    print(f'{description:<60} {nombre:>7} {parcourus[description]:>9} '
          f'{duree[description] * 1000:>10.1f}')
