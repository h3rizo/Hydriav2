from django.test import SimpleTestCase

from apps.core.templatetags.hydria_asset_icons import (
    equipment_icon,
    ouvrage_icon,
    point_eau_icon,
)


class HydriaAssetIconTests(SimpleTestCase):
    def test_point_icons_match_readings_workflow(self):
        self.assertEqual(point_eau_icon('Kiosque'), 'fa-store')
        self.assertEqual(point_eau_icon('Borne fontaine'), 'fa-faucet')
        self.assertEqual(point_eau_icon('BI volume'), 'fa-faucet')
        self.assertEqual(point_eau_icon('Branchement privé'), 'fa-home')
        self.assertEqual(point_eau_icon('Autre'), 'fa-tint')

    def test_equipment_icons_are_semantic_and_accent_insensitive(self):
        self.assertEqual(equipment_icon('Réservoir'), 'fa-database')
        self.assertEqual(equipment_icon('Compteur de tête'), 'fa-tachometer-alt')
        self.assertEqual(equipment_icon('Vanne principale'), 'fa-sliders-h')
        self.assertEqual(equipment_icon('Pompe solaire'), 'fa-cogs')
        self.assertEqual(equipment_icon('Captage source'), 'fa-water')
        self.assertEqual(equipment_icon('Autre équipement'), 'fa-cog')

    def test_ouvrage_icons_cover_operational_types(self):
        self.assertEqual(ouvrage_icon('AEPG extension'), 'fa-droplet')
        self.assertEqual(ouvrage_icon('AEPP'), 'fa-faucet-drip')
        self.assertEqual(ouvrage_icon('FPMH'), 'fa-water')
        self.assertEqual(ouvrage_icon('Travaux en cours'), 'fa-person-digging')
        self.assertEqual(ouvrage_icon('Suspendu'), 'fa-pause')
