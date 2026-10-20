"""Mesure le panneau « indemnités RBF » (621102) avec des libellés réels.

Le jeu de test synthétique ne nommait aucun ouvrage : les recherches en base étaient
donc court-circuitées. Ici on fabrique des libellés du format attendu par l'extracteur
(« …_Indemnite RBF<idxls>_<OUVRAGE> ») à partir des vrais ouvrages et points d'eau de
la base de test, puis on compare :

  * l'ancien comportement (une à cinq requêtes par ligne) ;
  * le nouveau (référentiels en mémoire), avec vérification que les rattachements
    ouvrage/point d'eau sont identiques ligne à ligne.

Usage : python tmp_bench_rbf_realiste.py [nb_lignes]
"""

import contextlib
import os
import random
import re
import sys
import time

BENCH_DB = 'hydria_gl_bench'
NB_LIGNES = int(sys.argv[1]) if len(sys.argv) > 1 else 3000


def read_dsn(env_file='.env'):
    for line in open(env_file, encoding='utf-8'):
        m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit('DATABASE_URL absente')


dsn = read_dsn().rstrip('/')
assert dsn.endswith('/hydria')
dsn = dsn[:-len('/hydria')] + '/' + BENCH_DB
os.environ['DATABASE_URL'] = dsn
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

import django  # noqa: E402

django.setup()

from django.core.cache.backends.locmem import LocMemCache  # noqa: E402
from django.db import connection  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

from apps.accounting import resolution_memoire as rm  # noqa: E402
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique  # noqa: E402
from apps.accounting.models import BaseDiameX  # noqa: E402
from apps.billing.models import PointEau  # noqa: E402
from apps.core import views_ouvrage_interventions as core  # noqa: E402
from apps.organization.models import Ouvrage  # noqa: E402

# Le cache disque de l'application ne fonctionne pas dans cet environnement
# (FileBasedCache : mkstemp tourne en boucle quand le dossier temporaire est refusé).
core.OUVRAGE_CARD_CACHE = LocMemCache('bench', {'TIMEOUT': None, 'MAX_ENTRIES': 30})

random.seed(7)
ouvrages = list(Ouvrage.objects.order_by('nom_ouvrage').values_list('id', 'nom_ouvrage'))
points = list(PointEau.objects.values_list('ouvrage_id', 'idxls', 'nomabonne'))
points_par_ouvrage = {}
for ouvrage_id, idxls, nomabonne in points:
    points_par_ouvrage.setdefault(ouvrage_id, []).append((idxls, nomabonne))

# --- Jeu de libellés réalistes -------------------------------------------------------
BaseDiameX.objects.filter(compte_code='621102').delete()
agents = ['MANARIASA Daniel', 'RAVELONIRINA Herisoa', 'RAMIADANA Francelette', 'RAZAFINDRAVAO Marie']
a_creer = []
for index in range(NB_LIGNES):
    ouvrage_id, nom_ouvrage = random.choice(ouvrages)
    points_ouvrage = points_par_ouvrage.get(ouvrage_id) or []
    idxls = random.choice([p[0] for p in points_ouvrage if p[0]] or ['1'])
    description = f"{random.choice(agents)}_Indemnite RBF{idxls}_{nom_ouvrage}"
    a_creer.append(BaseDiameX(
        id_access=900000 + index,
        fichier_source='BENCH_RBF.MDB',
        compte_code='621102',
        journal_code='601',
        date_m=django.utils.timezone.datetime(2025, random.randint(1, 12), 15).date(),
        date_rec=django.utils.timezone.datetime(2025, random.randint(1, 12), 20).date(),
        description=description,
        montant_out=round(random.uniform(5000, 90000), 2),
        montant_in=0.0,
        activ=random.choice(['AEP', 'Forage', 'BP']),
        fin=random.choice(['Bailleur A', 'Bailleur B', 'Budget']),
    ))
BaseDiameX.objects.bulk_create(a_creer, batch_size=500)
print(f'{NB_LIGNES} lignes 621102 réalistes créées '
      f'({Ouvrage.objects.count()} ouvrages, {PointEau.objects.count()} points d\'eau)')

# --- Équivalence de l'extraction ------------------------------------------------------
echantillon = list(BaseDiameX.objects.filter(fichier_source='BENCH_RBF.MDB')
                   .values_list('description', 'compte_code')[:150])


def resoudre_echantillon():
    resultats = []
    for description, code in echantillon:
        extraction = extraire_ouvrage_et_mois_generique(description or '', code or '')
        extraction = extraction[0] if isinstance(extraction, list) else (extraction or {})
        ouvrage = extraction.get('ouvrage_obj')
        point = extraction.get('point_eau_obj')
        resultats.append((
            str(getattr(ouvrage, 'id', '') or ''),
            str(getattr(point, 'id', '') or ''),
            str(extraction.get('point_eau_idxls') or ''),
            extraction.get('type_indemnite') or '',
        ))
    return resultats


print('\n=== Équivalence extraction (base vs mémoire) sur 150 libellés ===')
debut = time.time()
with CaptureQueriesContext(connection) as ctx_base:
    attendus = resoudre_echantillon()
duree_base = time.time() - debut
print(f'  base    : {duree_base:6.2f}s, {len(ctx_base.captured_queries):5d} requêtes')

rm.index_actuel(force=True)
debut = time.time()
with CaptureQueriesContext(connection) as ctx_memoire:
    with rm.resolution_memoire():
        obtenus = resoudre_echantillon()
duree_memoire = time.time() - debut
print(f'  mémoire : {duree_memoire:6.2f}s, {len(ctx_memoire.captured_queries):5d} requêtes')
print('  compteurs :', rm.statistiques())
ecarts = sum(1 for attendu, obtenu in zip(attendus, obtenus) if attendu != obtenu)
print(f'  écarts : {ecarts} / {len(echantillon)}')
if ecarts:
    for attendu, obtenu in zip(attendus, obtenus):
        if attendu != obtenu:
            print(f'    base={attendu} memoire={obtenu}')
            break
print('  rattachements trouvés (base) :',
      sum(1 for attendu in attendus if attendu[0]), '/', len(attendus))

# --- Mesure du cycle complet (fonction réelle) ---------------------------------------
print('\n=== Index complet des indemnités RBF ===')
total = BaseDiameX.objects.filter(compte_code='621102', montant_out__gt=0).count()
print(f'  {total} lignes à rattacher')

core.OUVRAGE_CARD_CACHE.clear()
original = rm.resolution_memoire


def mesurer(label):
    debut = time.time()
    with CaptureQueriesContext(connection) as ctx:
        index = core._rbf_indemnity_lines_by_ouvrage()
    duree = time.time() - debut
    lignes = sum(len(valeurs) for valeurs in index.values())
    print(f'  {label:<28} {duree:7.2f}s  {len(ctx.captured_queries):6d} requêtes  '
          f'{len(index)} ouvrages, {lignes} lignes rattachées')
    return duree, len(ctx.captured_queries), lignes


rm.resolution_memoire = contextlib.nullcontext  # ancien comportement
core.OUVRAGE_CARD_CACHE.clear()
duree_avant, requetes_avant, lignes_avant = mesurer('avant (requêtes/ligne)')

rm.resolution_memoire = original  # correctif
core.OUVRAGE_CARD_CACHE.clear()
rm.index_actuel(force=True)
duree_apres, requetes_apres, lignes_apres = mesurer('après (mémoire)')

print(f'\n  gain : {duree_avant / max(duree_apres, 0.001):.0f}× plus rapide, '
      f'{requetes_avant / max(requetes_apres, 1):.0f}× moins de requêtes')
print(f'  rattachements identiques : {lignes_avant == lignes_apres} '
      f'({lignes_avant} / {lignes_apres})')
print(f'  extrapolation à 7 500 lignes (débit local) : '
      f'avant {duree_avant / total * 7500:.0f}s, après {duree_apres / total * 7500:.0f}s')
