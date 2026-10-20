from decimal import Decimal

from django.test import SimpleTestCase

from apps.billing.views_facturation import _volume_propre


class VolumePropreTests(SimpleTestCase):
    def test_supprime_le_bruit_des_flottants(self):
        # Valeurs réelles relevées en base (FloatField) le 30/09/2026.
        self.assertEqual(_volume_propre(30.76000000000002), Decimal('30.760'))
        self.assertEqual(_volume_propre(1.4800000000000182), Decimal('1.480'))
        self.assertEqual(_volume_propre(3.130000000000109), Decimal('3.130'))

    def test_valeurs_vides_et_negatives(self):
        self.assertEqual(_volume_propre(None), Decimal('0.000'))
        self.assertEqual(_volume_propre(-1.5), Decimal('-1.500'))

    def test_le_montant_exact_ne_passe_pas_a_la_centaine_suivante(self):
        import math
        bruite = float(Decimal(str(1.3000000000000007)) * Decimal('1000'))
        propre = float(_volume_propre(1.3000000000000007) * Decimal('1000'))
        self.assertEqual(math.ceil(bruite / 100) * 100, 1400)  # le bug d'origine
        self.assertEqual(math.ceil(propre / 100) * 100, 1300)
