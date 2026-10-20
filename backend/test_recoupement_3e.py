import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.billing.models import Releve
from apps.accounting.models import BaseDiameX
from dateutil.relativedelta import relativedelta
from datetime import datetime
from decimal import Decimal

print("=== TEST RECOUPEMENT 3E ===\n")

# Simuler la logique du backend
print("1. Charger tous les relevés >= 2025 (avec montant):")
releves_tous = Releve.objects.filter(
    montant__isnull=False,
    montant__gt=0,
    point_eau__ouvrage__isnull=False,
    datereleve__year__gte=2025
).select_related('point_eau', 'point_eau__ouvrage')

print(f"   Nombre total: {releves_tous.count()}")

# Grouper par (ouvrage, année facturation, mois facturation)
releves_par_ouvrage = {}

for releve in releves_tous[:10]:  # Tester avec les 10 premiers
    if releve.point_eau and releve.point_eau.ouvrage and releve.datereleve:
        # Calculer la date de facturation (mois suivant le relevé)
        date_facturation = releve.datereleve + relativedelta(months=1)

        ouvrage_nom = releve.point_eau.ouvrage.nom_ouvrage if hasattr(releve.point_eau.ouvrage, 'nom_ouvrage') else str(releve.point_eau.ouvrage.id)

        key = (
            releve.point_eau.ouvrage.id,
            date_facturation.year,
            date_facturation.month
        )

        if key not in releves_par_ouvrage:
            releves_par_ouvrage[key] = {
                'ouvrage_id': releve.point_eau.ouvrage.id,
                'ouvrage_nom': ouvrage_nom,
                'annee': date_facturation.year,
                'mois': date_facturation.month,
                'nb_releves': 0,
                'total_releves': Decimal('0'),
                'nb_transactions_diamex': 0,
                'total_diamex': Decimal('0')
            }

        releves_par_ouvrage[key]['nb_releves'] += 1
        releves_par_ouvrage[key]['total_releves'] += Decimal(str(releve.montant))

print(f"\n2. Nombre de groupes créés: {len(releves_par_ouvrage)}")
print("\n3. Premiers groupes:")
for i, (key, data) in enumerate(list(releves_par_ouvrage.items())[:5]):
    print(f"   Groupe {i+1}:")
    print(f"     Ouvrage: {data['ouvrage_nom']}")
    print(f"     Période: {data['mois']:02d}/{data['annee']}")
    print(f"     Nb relevés: {data['nb_releves']}")
    print(f"     Total relevés: {data['total_releves']}")
    print()

# Vérifier si janvier 2025 apparaît
print("4. Vérifier présence de janvier 2025:")
janvier_2025_groups = [k for k in releves_par_ouvrage.keys() if k[1] == 2025 and k[2] == 1]
print(f"   Nombre de groupes pour janvier 2025: {len(janvier_2025_groups)}")

if len(janvier_2025_groups) > 0:
    print("   Ouvrages concernés:")
    for key in janvier_2025_groups[:5]:
        data = releves_par_ouvrage[key]
        print(f"     - {data['ouvrage_nom']}")
