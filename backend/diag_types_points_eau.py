# Diagnostic (lecture seule) : types de points d'eau, composants et points d'eau rattachés.
# Usage (depuis le dossier backend) :  python diag_types_points_eau.py
import os
import sys
import unicodedata
from collections import defaultdict

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from django.db.models import Count  # noqa: E402

from apps.billing.models import PointEau, TypePointEau  # noqa: E402
from apps.inspections.models import ComposantTypePointEau  # noqa: E402


def norm(text):
    text = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in text if not unicodedata.combining(c)).strip().lower()


types = list(
    TypePointEau.objects.annotate(
        nb_composants=Count('composants', distinct=True),
        nb_points=Count('pointeau', distinct=True),
    ).order_by('nom_type')
)

LIGNE = '{:30} {:>10} {:>12}  {}'
print("=== Types de points d'eau ===")
print(LIGNE.format('nom', 'composants', 'points eau', 'id'))
for t in types:
    print(LIGNE.format((t.nom_type or '')[:30], t.nb_composants, t.nb_points, t.id))

groupes = defaultdict(list)
for t in types:
    groupes[norm(t.nom_type)].append(t)
doublons = {k: v for k, v in groupes.items() if len(v) > 1}

print()
if not doublons:
    print('Aucun type en double (meme nom, casse et accents ignores).')
else:
    print('=== Types en DOUBLON (meme nom) ===')
    for nom, liste in doublons.items():
        print()
        print('"{}" : {} enregistrements'.format(nom, len(liste)))
        for t in liste:
            print('  - id {}  composants={}  points eau={}'.format(t.id, t.nb_composants, t.nb_points))
            for c in ComposantTypePointEau.objects.filter(type_point_eau=t).order_by('ordre_affichage'):
                print('        * {}'.format(c.nom_composant))

print()
print("=== Points d'eau sans type ===")
print(PointEau.objects.filter(type_point_eau__isnull=True).count())
