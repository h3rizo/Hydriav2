"""Vérifie que les tuiles de l'en-tête du grand livre affichent des valeurs réelles.

Usage : python tmp_check_tuiles.py
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

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

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
for suffixe in ('view_mode=grand_livre', 'view_mode=grand_livre_cards'):
    reponse = client.get('/comptabilite/entries/?' + suffixe, HTTP_HOST='compta.hydria.mg')
    contexte = reponse.context
    print(f'\n=== {suffixe} ({reponse.status_code}) ===')
    for cle in ('total_count', 'recettes', 'depenses', 'solde', 'transferts_solde',
                'transferts_count', 'pers_solde', 'pers_count', 'scans_valides_count',
                'operations_sans_scan', 'operations_total', 'liens_morts_count',
                'taux_sans_scan', 'taux_scans_valides', 'liens_morts_count'):
        print(f'   {cle:22} = {contexte.get(cle)}')
    print('   listes filtres :',
          len(contexte.get('fichiers_sources') or []), 'fichiers,',
          len(contexte.get('journaux_codes') or []), 'journaux,',
          len(contexte.get('comptes_options') or []), 'comptes,',
          len(contexte.get('fournisseur_autocomplete_values') or []), 'fournisseurs')

    # Les tuiles doivent contenir des chiffres, pas des vides.
    contenu = reponse.content.decode()
    for titre in ('Total entrées', 'Recettes', 'Dépenses', 'Transferts', 'Avances'):
        bloc = re.search(re.escape(titre) + r'(.{0,220})', contenu, re.S)
        valeur = 'ABSENT'
        if bloc:
            valeur = ' '.join(bloc.group(1).split())[:90]
        print(f'   tuile {titre:14} -> {valeur}')
