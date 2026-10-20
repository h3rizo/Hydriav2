from django.test import SimpleTestCase

from apps.accounting.charte_verification import verifier_charte_compte


class PaiementForfaitaireCharteTests(SimpleTestCase):
    def test_paiement_forfaitaire_accepts_simple_ouvrage_format(self):
        result = verifier_charte_compte(
            'Paiement forfaitaire Ambohimandroso Ambato',
            'paiement_forfaitaire',
            '748411',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Ambohimandroso Ambato')

    def test_paiement_forfaitaire_accepts_u_format_with_spaced_tarif(self):
        result = verifier_charte_compte(
            'Paiement forfaitaire_U_1_50 000_Ambondrona Nord',
            'paiement_forfaitaire',
            '748411',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Ambondrona Nord')

    def test_paiement_forfaitaire_accepts_simple_underscore_format(self):
        result = verifier_charte_compte(
            'Paiement forfaitaire_Ambohitrondry',
            'paiement_forfaitaire',
            '748411',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Ambohitrondry')
