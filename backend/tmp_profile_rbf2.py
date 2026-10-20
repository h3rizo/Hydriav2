"""Isole le coût de l'import du module et de l'index RBF complet.

Usage : python tmp_profile_rbf2.py
"""

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

debut = time.time()
import apps.core.views_ouvrage_interventions as module  # noqa: E402

print(f'import apps.core.views_ouvrage_interventions : {time.time() - debut:.2f}s', flush=True)

from django.core.cache import caches  # noqa: E402

from apps.accounting.models import BaseDiameX  # noqa: E402
from apps.core.views_ouvrage_interventions import (  # noqa: E402
    COMPTE_INDEMNITES_RBF, OUVRAGE_CARD_CACHE, _indemnity_point_id)

source = BaseDiameX.objects.filter(compte_code=COMPTE_INDEMNITES_RBF, montant_out__gt=0)
print('source prête', flush=True)

debut = time.time()
lignes = list(source.only('description', 'compte_code', 'montant_out', 'date_m')
              .order_by('id').values_list('id', 'description', 'compte_code', 'montant_out'))
print(f'chargement des {len(lignes)} lignes : {time.time() - debut:.2f}s', flush=True)
print('exemple de libellés :', flush=True)
for exemple in {description for _, description, _, _ in lignes[:200]}:
    print('   -', exemple[:110], flush=True)

from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique  # noqa: E402

debut = time.time()
nb_ouvrages = 0
plus_lent = (0.0, '')
for id_ligne, description, code, montant in lignes:
    t0 = time.perf_counter()
    extraction = extraire_ouvrage_et_mois_generique(description or '', code)
    duree = time.perf_counter() - t0
    if duree > plus_lent[0]:
        plus_lent = (duree, (description or '')[:90])
    if isinstance(extraction, list):
        extraction = extraction[0] if extraction else {}
    if (extraction or {}).get('ouvrage_obj'):
        nb_ouvrages += 1
print(f'boucle complète : {time.time() - debut:.2f}s, {nb_ouvrages} lignes rattachées à un ouvrage', flush=True)
print(f'extraction la plus lente : {plus_lent[0] * 1000:.1f} ms — {plus_lent[1]}', flush=True)

debut = time.time()
index = module._rbf_indemnity_lines_by_ouvrage()
print(f'_rbf_indemnity_lines_by_ouvrage : {time.time() - debut:.2f}s, '
      f'{len(index)} ouvrages', flush=True)
