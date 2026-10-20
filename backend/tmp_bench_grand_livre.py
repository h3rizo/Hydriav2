"""Mesure ciblée de la vue « grand livre » sur la base jetable hydria_gl_bench.

Écrit chaque étape dans tmp_bench/bench.log au fur et à mesure (pas de mise en
tampon) pour pouvoir suivre un long benchmark.

Usage : python tmp_bench_grand_livre.py [etapes]
  etapes : liste de mots-clés parmi liste, arbre, detail, agreg, enrich, tout
"""

import os
import re
import sys
import time

BENCH_DB = 'hydria_gl_bench'
LOG = os.path.join('tmp_bench', 'bench.log')

ETAPES = set(sys.argv[1:]) or {'tout'}
if 'tout' in ETAPES:
    ETAPES = {'liste', 'arbre', 'detail', 'agreg', 'enrich'}


def log(message):
    line = f'[{time.strftime("%H:%M:%S")}] {message}'
    print(line, flush=True)
    os.makedirs('tmp_bench', exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as fh:
        fh.write(line + '\n')


def read_dsn(env_file='.env'):
    for line in open(env_file, encoding='utf-8'):
        m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit('DATABASE_URL absente de .env')


dsn = read_dsn().rstrip('/')
assert dsn.endswith('/hydria'), dsn
dsn = dsn[:-len('/hydria')] + '/' + BENCH_DB
os.environ['DATABASE_URL'] = dsn
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

import django  # noqa: E402

django.setup()

from decimal import Decimal  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext, setup_test_environment  # noqa: E402

from apps.accounting import views as V  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402

setup_test_environment()
connection.ensure_connection()
with connection.cursor() as cur:
    cur.execute('SELECT count(*) FROM basediamex')
    total = cur.fetchone()[0]
log(f'Base {BENCH_DB} : {total} ecritures')

User = get_user_model()
user, _ = User.objects.get_or_create(
    username='bench_gl',
    defaults={'is_superuser': True, 'is_staff': True, 'email': 'bench@example.com'},
)
user.is_superuser = True
user.is_staff = True
user.is_active = True
user.set_password('bench-only')
user.save()

client = Client()
client.force_login(user)
HOST = {'HTTP_HOST': 'compta.hydria.mg'}


def bench(label, url):
    started = time.time()
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url, **HOST)
    elapsed = time.time() - started
    log(f'  {label:<46} {response.status_code}  {elapsed:7.2f}s  '
        f'{len(ctx.captured_queries):4d} requetes  {len(response.content) / 1024:8.0f} Ko')
    return response, elapsed, len(ctx.captured_queries)


if 'liste' in ETAPES:
    log('=== Vue liste (reference, paginee) ===')
    # NB : sans filtre de compte, la vue liste déclenche le panneau « indemnités RBF »
    # (_rbf_indemnity_lines_by_ouvrage) qui recalcule l'index complet des 621102 : des
    # minutes sur un gros journal. On filtre sur un compte hors 621102 pour mesurer la
    # vue liste elle-même.
    bench('vue liste (compte 748201)', '/comptabilite/entries/?view_mode=liste&compte=748201')
    bench('vue liste (compte 707401, page 2)',
          '/comptabilite/entries/?view_mode=liste&compte=707401&page=2')

if 'json' in ETAPES:
    log('=== Export JSON (tableau de bord) ===')
    bench('entries format=json (compte 707401)',
          '/comptabilite/entries/?format=json&compte=707401&view_mode=liste')

if 'arbre' in ETAPES:
    log('=== Vue grand livre : arbre agrege ===')
    tree_response, tree_seconds, tree_queries = bench(
        'grand livre (arbre)', '/comptabilite/entries/?view_mode=grand_livre')
    bench('grand livre (cards)', '/comptabilite/entries/?view_mode=grand_livre_cards')
    if os.environ.get('BENCH_DUMP'):
        with open(os.path.join('tmp_bench', 'arbre.html'), 'wb') as fh:
            fh.write(tree_response.content)

if 'detail' in ETAPES:
    log("=== Vue grand livre : niveau comptes puis ecritures d'un compte ===")
    with CaptureQueriesContext(connection):
        response = client.get('/comptabilite/entries/?view_mode=grand_livre', **HOST)

    def extraire_lien(contenu, marqueur):
        match = re.search(r'href="(\?[^"]*' + marqueur + r'[^"]*)"',
                          contenu.decode('utf-8', 'ignore'))
        return match.group(1).replace('&amp;', '&') if match else None

    lien_comptes = extraire_lien(response.content, r'gl_cat=')
    if lien_comptes:
        log(f'  lien comptes : {lien_comptes[:200]}')
        page_comptes, _, _ = bench('grand livre + gl_cat', '/comptabilite/entries/' + lien_comptes)
        lien_detail = extraire_lien(page_comptes.content, r'gl_detail=1')
        if lien_detail:
            log(f'  lien ecritures : {lien_detail[:200]}')
            bench('grand livre + gl_detail', '/comptabilite/entries/' + lien_detail)
        else:
            log('  ATTENTION : aucun lien gl_detail sur la page des comptes !')
    else:
        log('  ATTENTION : aucun lien gl_cat dans l\'arbre !')

if 'agreg' in ETAPES:
    log('=== Agregation : Python (ancienne) vs SQL (nouvelle) ===')
    queryset = BaseDiameX.objects.select_related('journal', 'compte').order_by('-date_m', '-id')

    started = time.time()
    legacy_entries = list(queryset)
    load_seconds = time.time() - started
    log(f'  chargement des {len(legacy_entries)} ecritures : {load_seconds:.2f}s')

    started = time.time()
    for entry in legacy_entries:
        entry.compte_categorie_label = V._get_entry_compte_category_label(entry)
    log(f'  categorie de compte par ecriture : {time.time() - started:.2f}s')

    def legacy_build(entries):
        grouped = []
        activ_map = {}

        def get_or_create(container, key, label, child_key):
            item = container.get(key)
            if item is None:
                item = {'key': key, 'label': label, child_key: [],
                        'total_in': Decimal('0'), 'total_out': Decimal('0'),
                        'nb': 0, '_children_map': {}}
                container[key] = item
            return item

        for entry in entries:
            activ_label = (entry.activ or 'Sans activ').strip()
            fin_label = (entry.fin or 'Sans financement').strip()
            categorie_label = (entry.compte_categorie_label or 'Sans catégorie compte').strip()
            compte_code = (entry.compte_code or 'Sans compte').strip()
            compte_nom = (getattr(getattr(entry, 'compte', None), 'nom_compte', '') or '').strip()
            compte_label = f'{compte_code} - {compte_nom}' if compte_nom else compte_code

            activ_item = get_or_create(activ_map, V._normalize_text(activ_label), activ_label, 'financements')
            fin_item = get_or_create(activ_item['_children_map'], V._normalize_text(fin_label), fin_label, 'categories')
            if fin_item not in activ_item['financements']:
                activ_item['financements'].append(fin_item)
            categorie_item = get_or_create(fin_item['_children_map'], V._normalize_text(categorie_label),
                                           categorie_label, 'comptes')
            if categorie_item not in fin_item['categories']:
                fin_item['categories'].append(categorie_item)
            compte_item = get_or_create(categorie_item['_children_map'], V._normalize_text(compte_label),
                                        compte_label, 'entries')
            if compte_item not in categorie_item['comptes']:
                categorie_item['comptes'].append(compte_item)

            montant_in = Decimal(str(entry.montant_in or 0))
            montant_out = Decimal(str(entry.montant_out or 0))
            for item in (activ_item, fin_item, categorie_item, compte_item):
                item['total_in'] += montant_in
                item['total_out'] += montant_out
                item['nb'] += 1

        return sorted(activ_map.values(), key=lambda item: V._normalize_text(item['label']))

    started = time.time()
    legacy_groups = legacy_build(legacy_entries)
    log(f'  ancienne agregation Python : {time.time() - started:.2f}s')

    started = time.time()
    with CaptureQueriesContext(connection) as ctx:
        sql_groups = V._build_grand_livre_groups(
            BaseDiameX.objects.select_related('journal', 'compte').order_by('-date_m', '-id'))
    log(f'  nouvelle agregation SQL : {time.time() - started:.2f}s '
        f'({len(ctx.captured_queries)} requete)')

    def aplatir(groups):
        flat = {}
        for activ in groups:
            for fin in activ['financements']:
                for cat in fin['categories']:
                    for compte in cat['comptes']:
                        node = flat.setdefault((activ['label'], fin['label'], cat['label']),
                                               {'in': Decimal('0'), 'out': Decimal('0'), 'nb': 0})
                        node['in'] += compte['total_in']
                        node['out'] += compte['total_out']
                        node['nb'] += compte['nb']
        return flat

    flat_legacy = aplatir(legacy_groups)
    flat_sql = aplatir(sql_groups)
    log(f'  groupes (activ/fin/categorie) : legacy={len(flat_legacy)} sql={len(flat_sql)}')
    only_legacy = set(flat_legacy) - set(flat_sql)
    only_sql = set(flat_sql) - set(flat_legacy)
    log(f'  presents seulement en legacy : {len(only_legacy)}')
    for key in list(only_legacy)[:6]:
        log(f'     - {key}')
    log(f'  presents seulement en SQL    : {len(only_sql)}')
    for key in list(only_sql)[:6]:
        log(f'     + {key}')

    ecarts = 0
    for key in sorted(set(flat_legacy) & set(flat_sql)):
        left, right = flat_legacy[key], flat_sql[key]
        if (left['in'], left['out'], left['nb']) != (right['in'], right['out'], right['nb']):
            ecarts += 1
            if ecarts <= 6:
                log(f'     ECART {key}: legacy={left["in"]}/{left["out"]}/{left["nb"]} '
                    f'sql={right["in"]}/{right["out"]}/{right["nb"]}')
    log(f'  ecarts sur les groupes communs : {ecarts}')
    log(f'  total entree legacy={sum(n["in"] for n in flat_legacy.values()):,.0f} '
        f'sql={sum(n["in"] for n in flat_sql.values()):,.0f}')

if 'enrich' in ETAPES:
    log("=== Enrichissement par ecriture (cout de l'ancienne vue) ===")
    queryset = BaseDiameX.objects.select_related('journal', 'compte').order_by('-date_m', '-id')
    for sample in (200, 600):
        subset = list(queryset[:sample])
        started = time.time()
        V._build_entries_enrichment(subset)
        elapsed = time.time() - started
        log(f'  {sample:5d} ecritures enrichies : {elapsed:7.2f}s')
