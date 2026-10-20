"""Vérifie l'équivalence entre résolution en mémoire et résolution en base.

Pour un échantillon de libellés réels de la base de test, on compare l'extraction
(ouvrage, point d'eau, type, année) obtenue :

  * avec ``resolution_memoire()`` (index en mémoire, aucune requête par ligne) ;
  * sans (comportement d'origine, plusieurs requêtes par ligne).

Puis on mesure le coût de l'index complet des indemnités RBF (621102).

Usage : python tmp_verif_resolution.py [taille_echantillon]
"""

import os
import random
import re
import sys
import time

BENCH_DB = 'hydria_gl_bench'
ECHANTILLON = int(sys.argv[1]) if len(sys.argv) > 1 else 120


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

from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402
from apps.accounting.resolution_memoire import (  # noqa: E402
    index_actuel, resolution_memoire, statistiques)
from apps.billing.models import PointEau  # noqa: E402
from apps.organization.models import Ouvrage  # noqa: E402

print(f'Référentiels : {Ouvrage.objects.count()} ouvrages, {PointEau.objects.count()} points d\'eau')

codes = list(BaseDiameX.objects.values_list('compte_code', flat=True).distinct())
print(f'{len(codes)} codes de compte dans le journal')

libelles = list(
    BaseDiameX.objects.exclude(description__isnull=True).exclude(description='')
    .values_list('description', 'compte_code').order_by('?')[:ECHANTILLON]
)
rbf = list(BaseDiameX.objects.filter(compte_code='621102', montant_out__gt=0)
           .values_list('description', flat=True)[:40])
echantillon = libelles + [(description, '621102') for description in rbf]
print(f'{len(echantillon)} libellés comparés')


def extraire(description, code):
    extraction = extraire_ouvrage_et_mois_generique(description or '', code or '')
    if isinstance(extraction, list):
        return [resume(item) for item in extraction]
    return resume(extraction)


def resume(extraction):
    extraction = extraction or {}
    ouvrage = extraction.get('ouvrage_obj')
    point = extraction.get('point_eau_obj')
    return {
        'ouvrage': str(getattr(ouvrage, 'id', '') or ''),
        'ouvrage_nom': extraction.get('ouvrage_nom') or '',
        'point': str(getattr(point, 'id', '') or ''),
        'point_idxls': str(extraction.get('point_eau_idxls') or ''),
        'type': extraction.get('type_indemnite') or '',
        'annee': extraction.get('annee'),
    }


print('\n=== Extraction en base (comportement d\'origine) ===')
debut = time.time()
with CaptureQueriesContext(connection) as ctx_base:
    attendus = [extraire(description, code) for description, code in echantillon]
duree_base = time.time() - debut
nb_requetes_base = len(ctx_base.captured_queries)
print(f'  {len(echantillon)} libellés : {duree_base:.2f}s, {nb_requetes_base} requêtes '
      f'({nb_requetes_base / max(len(echantillon), 1):.1f} par libellé)')

print('\n=== Extraction en mémoire ===')
index_actuel(force=True)
debut = time.time()
with CaptureQueriesContext(connection) as ctx_memoire:
    with resolution_memoire():
        obtenus = [extraire(description, code) for description, code in echantillon]
duree_memoire = time.time() - debut
print(f'  {len(echantillon)} libellés : {duree_memoire:.2f}s, '
      f'{len(ctx_memoire.captured_queries)} requêtes (index + reports en base)')
print('  compteurs :', statistiques())

ecarts = [
    (echantillon[i][0][:70], attendus[i], obtenus[i])
    for i in range(len(echantillon)) if attendus[i] != obtenus[i]
]
print(f'\n=== Écarts : {len(ecarts)} / {len(echantillon)} ===')
for libelle, attendu, obtenu in ecarts[:10]:
    print(f'  libellé   : {libelle}')
    print(f'    base    : {attendu}')
    print(f'    memoire : {obtenu}')

print('\n=== Index complet des indemnités RBF (621102) ===')
from apps.core.views_ouvrage_interventions import _rbf_indemnity_lines_by_ouvrage  # noqa: E402

nb_rbf = BaseDiameX.objects.filter(compte_code='621102', montant_out__gt=0).count()
print(f'  {nb_rbf} lignes 621102 à rattacher')
debut = time.time()
with CaptureQueriesContext(connection) as ctx_rbf:
    index = _rbf_indemnity_lines_by_ouvrage()
duree = time.time() - debut
print(f'  terminé en {duree:.2f}s, {len(ctx_rbf.captured_queries)} requêtes, '
      f'{len(index)} ouvrages rattachés')
