"""Profil de l'extraction d'une indemnité RBF (libellés réalistes).

Usage : python tmp_profile_extraction.py [nb_libelles]
"""

import cProfile
import io
import os
import pstats
import re
import sys
import time

BENCH_DB = 'hydria_gl_bench'
NB = int(sys.argv[1]) if len(sys.argv) > 1 else 200


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

from apps.accounting.extracteurs_description import extraire_indemnite_rbf_ppmh  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402
from apps.accounting.resolution_memoire import resolution_memoire  # noqa: E402

libelles = list(
    BaseDiameX.objects.filter(fichier_source='BENCH_RBF.MDB')
    .values_list('description', flat=True)[:NB]
)
print(f'{len(libelles)} libellés, exemple : {libelles[0] if libelles else "-"}')

with resolution_memoire():
    debut = time.time()
    for libelle in libelles[:20]:
        extraire_indemnite_rbf_ppmh(libelle)
    print(f'20 extractions : {time.time() - debut:.2f}s')

    profile = cProfile.Profile()
    debut = time.time()
    profile.enable()
    for libelle in libelles:
        extraire_indemnite_rbf_ppmh(libelle)
    profile.disable()
    duree = time.time() - debut
    print(f'{len(libelles)} extractions : {duree:.2f}s ({duree / len(libelles) * 1000:.1f} ms/libellé)')

flux = io.StringIO()
pstats.Stats(profile, stream=flux).sort_stats('tottime').print_stats(15)
print(flux.getvalue())
