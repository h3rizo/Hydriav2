"""Décompose le coût du rattachement des indemnités RBF (621102) ligne par ligne.

Usage : python tmp_profile_rbf.py [nb_lignes]
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

from django.db import connection  # noqa: E402

from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402
from apps.accounting.resolution_memoire import resolution_memoire, statistiques  # noqa: E402
from apps.core.views_ouvrage_interventions import (  # noqa: E402
    COMPTE_INDEMNITES_RBF, _descriptions_digest, _indemnity_point_id)

source = BaseDiameX.objects.filter(compte_code=COMPTE_INDEMNITES_RBF, montant_out__gt=0)
entrees = list(source.only('description', 'compte_code', 'montant_out', 'date_m').order_by('id')[:LIMITE])
print(f'{len(entrees)} lignes 621102 échantillonnées')

debut = time.time()
empreinte = source.aggregate(django.db.models.Count('id'), django.db.models.Max('id'), django.db.models.Sum('montant_out'))
print(f'agrégat de contrôle : {time.time() - debut:.2f}s')

debut = time.time()
digest = _descriptions_digest(source)
print(f'digest des libellés  : {time.time() - debut:.2f}s ({digest})')

from apps.accounting.indemnites_points import annee_exercice  # noqa: E402

temps_extraction = 0.0
temps_annee = 0.0
temps_point = 0.0
plus_lents = []
with resolution_memoire():
    for index, entree in enumerate(entrees):
        t0 = time.perf_counter()
        extraction = extraire_ouvrage_et_mois_generique(entree.description or '', entree.compte_code)
        t1 = time.perf_counter()
        if isinstance(extraction, list):
            extraction = extraction[0] if extraction else {}
        ouvrage = (extraction or {}).get('ouvrage_obj')
        annee_exercice(entree.description, entree.date_m.year if entree.date_m else None)
        t2 = time.perf_counter()
        if ouvrage:
            _indemnity_point_id(extraction, ouvrage, {})
        t3 = time.perf_counter()
        temps_extraction += t1 - t0
        temps_annee += t2 - t1
        temps_point += t3 - t2
        plus_lents.append((t1 - t0, (entree.description or '')[:90]))
        if (index + 1) % 100 == 0:
            print(f'  {index + 1:5d} lignes : extraction {temps_extraction:6.2f}s, '
                  f'annee {temps_annee:5.2f}s, point {temps_point:5.2f}s')

print(f'\nTotaux sur {len(entrees)} lignes :')
print(f'  extraction ouvrage : {temps_extraction:6.2f}s '
      f'({temps_extraction / max(len(entrees), 1) * 1000:.1f} ms/ligne)')
print(f'  année d\'exercice   : {temps_annee:6.2f}s')
print(f'  point d\'eau        : {temps_point:6.2f}s')
print('  requêtes restantes en base :', statistiques())

plus_lents.sort(reverse=True)
print('\n  Extractions les plus lentes :')
for duree, description in plus_lents[:5]:
    print(f'    {duree * 1000:8.1f} ms  {description}')

with connection.cursor() as cur:
    cur.execute('SELECT count(*) FROM basediamex WHERE compte_code = %s AND montant_out > 0',
                [COMPTE_INDEMNITES_RBF])
    total = cur.fetchone()[0]
print(f'\nExtrapolation sur les {total} lignes 621102 : '
      f'{(temps_extraction + temps_annee + temps_point) / max(len(entrees), 1) * total:.0f}s')
