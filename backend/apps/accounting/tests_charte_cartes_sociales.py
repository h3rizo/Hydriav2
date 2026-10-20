from django.test import SimpleTestCase

from apps.accounting.charte_verification import verifier_charte_compte


class CartesSocialesCharteTests(SimpleTestCase):
    def test_cartes_sociales_accepts_any_valid_day(self):
        result = verifier_charte_compte(
            'Cartes sociales Ambato 13/06/2025',
            'cartes_sociales',
            '748415',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Ambato')
        self.assertEqual(result['details']['date'], '13/06/2025')
