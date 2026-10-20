import datetime
from decimal import Decimal

from django.db import migrations

# Tarifs pleins relevés dans les données de production : BF 75 000 Ar, PMH 50 000 Ar.
# Les anciens BI (37 500) et PMHI (25 000) deviennent BF / PMH à 50 %.
TARIFS_INITIAUX = (
    ('BF', Decimal('75000.00')),
    ('PMH', Decimal('50000.00')),
)
DATE_DEBUT = datetime.date(2020, 1, 1)


def initialiser(apps, schema_editor):
    TypePointEau = apps.get_model('billing', 'TypePointEau')
    ConfigTarifForfaitaire = apps.get_model('billing', 'ConfigTarifForfaitaire')
    PointEau = apps.get_model('billing', 'PointEau')

    for nom_type, tarif in TARIFS_INITIAUX:
        type_pe = TypePointEau.objects.filter(nom_type=nom_type).first()
        if type_pe is None:
            continue
        ConfigTarifForfaitaire.objects.get_or_create(
            type_point_eau=type_pe, date_debut=DATE_DEBUT, defaults={'tarif': tarif},
        )
        # Pourcentage déduit du montant actuel ; le montant lui-même n'est pas modifié
        for point in PointEau.objects.filter(
            type_point_eau=type_pe, tarifforfaitaire__isnull=False, pourcentage_tarif__isnull=True
        ).only('id', 'tarifforfaitaire'):
            pourcentage = (Decimal(str(point.tarifforfaitaire)) * 100 / tarif).quantize(Decimal('0.0001'))
            PointEau.objects.filter(pk=point.pk).update(pourcentage_tarif=pourcentage)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0082_config_tarif_forfaitaire_pourcentage'),
    ]

    operations = [
        migrations.RunPython(initialiser, migrations.RunPython.noop),
    ]
