"""Contrôle du grand livre imprimable sur la base de test (150 000 écritures).

Écrit le document rendu dans tmp_bench/grand_livre_demo.html (à ouvrir dans un
navigateur pour vérifier la mise en page et l'aperçu avant impression).

Usage : python tmp_check_impression.py [financement] [date_debut] [date_fin]
"""

import os
import re
import sys
import time

BENCH_DB = 'hydria_gl_bench'
FIN = sys.argv[1] if len(sys.argv) > 1 else ''
DEBUT = sys.argv[2] if len(sys.argv) > 2 else '2024-01-01'
FIN_PERIODE = sys.argv[3] if len(sys.argv) > 3 else '2024-12-31'


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

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext, setup_test_environment  # noqa: E402

setup_test_environment()

User = get_user_model()
user, _ = User.objects.get_or_create(
    username='bench_gl',
    defaults={'is_superuser': True, 'is_staff': True, 'email': 'bench@example.com'})
user.is_superuser = True
user.is_staff = True
user.set_password('bench-only')
user.save()

client = Client()
client.force_login(user)
HOST = {'HTTP_HOST': 'compta.hydria.mg'}
URL = '/comptabilite/entries/grand-livre/impression/'


def mesurer(label, url, **params):
    debut = time.time()
    with CaptureQueriesContext(connection) as ctx:
        reponse = client.get(url, params or None, **HOST)
    duree = time.time() - debut
    print(f'  {label:<40} {reponse.status_code}  {duree:6.2f}s  '
          f'{len(ctx.captured_queries):3d} requetes  {len(reponse.content) / 1024:7.0f} Ko')
    return reponse


print(f'Base {BENCH_DB}')
print('=== Formulaire (sans paramètre) ===')
formulaire = mesurer('formulaire', URL)
if FIN:
    print(f'=== Document fin={FIN} du {DEBUT} au {FIN_PERIODE} ===')
    document = mesurer('document', URL, fin=FIN, date_debut=DEBUT, date_fin=FIN_PERIODE)
    if document.status_code == 200:
        contexte = document.context
        doc = contexte.get('document')
        if doc:
            print(f'  solde debut   = {doc["solde_debut"]:>18,.0f}')
            print(f'  total periode = {doc["total_periode"]:>18,.0f}')
            print(f'  solde fin     = {doc["solde_fin"]:>18,.0f}')
            print(f'  lignes        = {doc["nb_lignes"]:>18,} ({doc["nb_cats"]} comptes)')
            for section in doc['sections']:
                print(f'  section {section["cle"]:<9} : {section["nb"]:>7,} lignes, '
                      f'total {section["total"]:>18,.0f}, {len(section["groupes"])} comptes')
            os.makedirs('tmp_bench', exist_ok=True)
            chemin = os.path.join('tmp_bench', 'grand_livre_demo.html')
            with open(chemin, 'wb') as fh:
                fh.write(document.content)
            print(f'  document écrit dans {chemin}')
        else:
            print('  ATTENTION : pas de document (erreurs :', contexte.get('erreurs'), ')')
else:
    # Financements disponibles puis le plus volumineux
    from apps.accounting.models import BaseDiameX
    from django.db.models import Count

    print('=== Financements disponibles ===')
    for ligne in (BaseDiameX.objects.values('fin').annotate(n=Count('id')).order_by('-n')[:8]):
        print(f'   {str(ligne["fin"]):<24} {ligne["n"]:>8,} écritures')
    print('Relancer avec un financement en argument pour produire le document.')
