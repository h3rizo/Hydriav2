from django.db import migrations

# Ancien type -> type cible. Le caractère institutionnel est désormais porté par
# PointEau.estbranchementinstitutionnel et non plus par le type.
FUSIONS = (
    ('BI', 'BF'),
    ('BI volume', 'BP'),
    ('PMHI', 'PMH'),
)


def fusionner_types(apps, schema_editor):
    TypePointEau = apps.get_model('billing', 'TypePointEau')
    PointEau = apps.get_model('billing', 'PointEau')

    for ancien_nom, cible_nom in FUSIONS:
        ancien = TypePointEau.objects.filter(nom_type=ancien_nom).first()
        if ancien is None:
            continue
        cible = TypePointEau.objects.filter(nom_type=cible_nom).first()
        if cible is None:
            # Pas de type cible : on renomme l'ancien plutôt que de perdre le lien
            ancien.nom_type = cible_nom
            ancien.save(update_fields=['nom_type'])
            PointEau.objects.filter(type_point_eau_id=ancien.pk).update(
                estbranchementinstitutionnel=True
            )
            continue

        PointEau.objects.filter(type_point_eau_id=ancien.pk).update(
            type_point_eau_id=cible.pk,
            estbranchementinstitutionnel=True,
        )
        # Pas de suppression : composants d'inspection, barèmes chantiers et tarifs
        # référencent encore l'ancien type (CASCADE / PROTECT). On le désactive.
        ancien.actif = False
        ancien.save(update_fields=['actif'])


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0080_paiementforfaitaire_encaissement'),
    ]

    operations = [
        migrations.RunPython(fusionner_types, migrations.RunPython.noop),
    ]
