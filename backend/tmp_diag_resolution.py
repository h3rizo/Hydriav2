"""Diagnostic du résolveur en mémoire : pourquoi une recherche est-elle refusée ?

Usage : python tmp_diag_resolution.py
"""

import os
import re

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

from django.db.models import Q  # noqa: E402
from django.db.models.query import ModelIterable  # noqa: E402

from apps.accounting import resolution_memoire as rm  # noqa: E402
from apps.billing.models import PointEau  # noqa: E402
from apps.organization.models import Ouvrage  # noqa: E402

Ouvrage.objects.order_by('nom_ouvrage').first()
nom_ouvrage = Ouvrage.objects.values_list('nom_ouvrage', flat=True).first()
print('ouvrage de test :', repr(nom_ouvrage))

cas = [
    ('Ouvrage iexact', Ouvrage.objects.filter(nom_ouvrage__iexact=nom_ouvrage)),
    ('Ouvrage icontains', Ouvrage.objects.filter(nom_ouvrage__icontains=nom_ouvrage[:6])),
    ('Ouvrage all', Ouvrage.objects.all()),
    ('PointEau iexact nomabonne', PointEau.objects.filter(nomabonne__iexact='NIF123')),
    ('PointEau all puis filter',
     PointEau.objects.all().filter(nomabonne__iexact='NIF123')),
    ('PointEau ouvrage + nomabonne',
     PointEau.objects.filter(ouvrage=Ouvrage.objects.first(), nomabonne__iexact='X')),
    ('PointEau code_point_eau', PointEau.objects.filter(code_point_eau__iexact='X')),
    ('PointEau idxls entier', PointEau.objects.filter(idxls=123)),
    ('PointEau exclude', PointEau.objects.exclude(nomabonne='X')),
    ('PointEau in', PointEau.objects.filter(nomabonne__in=['A', 'B'])),
]

for libelle, queryset in cas:
    conditions = rm._conditions_simples(queryset)
    print(f'\n{libelle}')
    print(f'  iterable    : {getattr(queryset, "_iterable_class", None)} '
          f'(ModelIterable attendu : {getattr(queryset, "_iterable_class", None) is ModelIterable})')
    print(f'  conditions  : {conditions if conditions is not None else "REFUSÉ"}')
    if conditions is None:
        requete = queryset.query
        print(f'  is_sliced={requete.is_sliced} distinct={requete.distinct} '
              f'annotations={list(requete.annotation_select)} order_by={requete.order_by} '
              f'combinator={requete.combinator}')
        where = requete.where
        print(f'  where.negated={where.negated} connector={where.connector!r} '
              f'enfants={[type(e).__name__ for e in where.children]}')
        for enfant in where.children:
            lhs = getattr(enfant, 'lhs', None)
            print(f'    - {enfant!r} | lookup={getattr(enfant, "lookup_name", None)} '
                  f'| lhs_type={type(lhs).__name__} '
                  f'| lhs_model={getattr(getattr(lhs, "model", None), "__name__", None)} '
                  f'| lhs_name={getattr(lhs, "name", None)} '
                  f'| Field={isinstance(lhs, rm.Field)}')
    else:
        print(f'  modèle indexé : {rm._source_index(queryset.model, rm.index_actuel()) is not None}')

print('\n--- résolution effective ---')
rm.index_actuel(force=True)
with rm.resolution_memoire():
    attendu = Ouvrage.objects.filter(nom_ouvrage__iexact=nom_ouvrage).first()
    print('Ouvrage iexact :', getattr(attendu, 'nom_ouvrage', None),
          '| compteurs', rm.statistiques())
    point = PointEau.objects.filter(nomabonne__iexact='NIF123').first()
    print('PointEau iexact :', point, '| compteurs', rm.statistiques())
