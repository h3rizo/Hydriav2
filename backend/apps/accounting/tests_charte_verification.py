from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.accounting.charte_verification import verifier_charte_compte
from apps.accounting.extracteurs_description import est_paiement_volume_multi
from apps.accounting.views_verification_ouvrages import diviser_paiement_volume_multi
from apps.accounting.views_verification_fournisseurs import (
    _normalize_matricule,
    extraire_infos_carburant,
)


class PaiementVolumeCharteTests(SimpleTestCase):
    def test_idxls_suffix_is_not_a_multi_payment(self):
        description = 'Paiement au volume Vohilengo AEPG 01/04/2026 (40;90)'

        self.assertFalse(est_paiement_volume_multi(description))
        self.assertEqual(
            diviser_paiement_volume_multi(description, '707401', 16400),
            [],
        )

    def test_real_multi_payment_is_still_detected(self):
        description = (
            'Paiement au volume Vohilengo AEPG 04/2026 16400; '
            'Vohilengo AEPG 05/2026 12000'
        )

        self.assertTrue(est_paiement_volume_multi(description))

    def test_paiement_volume_accepts_day_month_year(self):
        result = verifier_charte_compte(
            'Paiement au volume Vohipeno 01/07/2025',
            'paiement_volume',
            '707401',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Vohipeno')

    def test_paiement_volume_accepts_month_year(self):
        result = verifier_charte_compte(
            'Paiement au volume Sahasaona 09/2025',
            'paiement_volume',
            '707401',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Sahasaona')
        self.assertEqual(result['details']['mois'], 9)
        self.assertEqual(result['details']['annee'], 2025)

    def test_paiement_volume_accepts_idxls_suffix(self):
        result = verifier_charte_compte(
            'Paiement au volume Vohipeno 01/07/2025 (123;456)',
            'paiement_volume',
            '707401',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Vohipeno')

    def test_paiement_volume_accepts_precise_day_with_numeric_suffix(self):
        result = verifier_charte_compte(
            'Paiement au volume Avaratsena 19/06/2026 (8)',
            'paiement_volume',
            '707401',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Avaratsena')
        self.assertEqual(result['details']['date'], '19/06/2026')

    def test_paiement_volume_accepts_precise_day_with_idxls_list_suffix(self):
        result = verifier_charte_compte(
            'Paiement au volume Avaratsena 19/06/2026 (8;12;15)',
            'paiement_volume',
            '707401',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Avaratsena')
        self.assertEqual(result['details']['date'], '19/06/2026')

    def test_paiement_volume_accepts_releves_count_suffix(self):
        result = verifier_charte_compte(
            'Paiement au volume Sahasaona 09/2025 (3 releves)',
            'paiement_volume',
            '707401',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['ouvrage'], 'Sahasaona')


class InstallationBpCharteTests(SimpleTestCase):
    def test_installation_bp_accepts_paiement_pour_devis_with_subscriber(self):
        result = verifier_charte_compte(
            'MANAMPIHERY Indiamihenina_Paiement pour devis installation BP_183_Vohilengo AEPG',
            'installation_bp',
            '748201',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['nom_personne'], 'MANAMPIHERY Indiamihenina')
        self.assertEqual(result['details']['type_paiement'], 'Paiement pour devis installation BP')
        self.assertEqual(result['details']['idxls_pe'], '183')
        self.assertEqual(result['details']['ouvrage'], 'Vohilengo AEPG')

    def test_installation_bp_accepts_name_without_leading_underscore(self):
        result = verifier_charte_compte(
            'ZAFIHANONA JEAN NICOLAS_Paiement demande devis installation BP_186_Vohilengo AEPG',
            'installation_bp',
            '748201',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['nom_personne'], 'ZAFIHANONA JEAN NICOLAS')
        self.assertEqual(result['details']['type_paiement'], 'Paiement demande devis installation BP')
        self.assertEqual(result['details']['idxls_pe'], '186')
        self.assertEqual(result['details']['ouvrage'], 'Vohilengo AEPG')

    def test_installation_bp_accepts_paiement_devise_bp_without_leading_underscore(self):
        result = verifier_charte_compte(
            'MANAMPIHERY Andriamihenina_Paiement devise BP_186_Vohilengo AEPG',
            'installation_bp',
            '748201',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['nom_personne'], 'MANAMPIHERY Andriamihenina')
        self.assertEqual(result['details']['type_paiement'], 'Paiement devise BP')
        self.assertEqual(result['details']['idxls_pe'], '186')
        self.assertEqual(result['details']['ouvrage'], 'Vohilengo AEPG')

    def test_installation_bp_ignores_parenthetical_suffix_in_payment_type(self):
        result = verifier_charte_compte(
            '_Florine_Paiement pour installation BP (2ème tranche)_26_Sahivo',
            'installation_bp',
            '748201',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['nom_personne'], 'Florine')
        self.assertEqual(result['details']['type_paiement'], 'Paiement pour installation BP')
        self.assertEqual(result['details']['idxls_pe'], '26')
        self.assertEqual(result['details']['ouvrage'], 'Sahivo')


class BafCharteTests(SimpleTestCase):
    def test_baf_accepts_cnaps_without_underscores(self):
        result = verifier_charte_compte(
            'BAF CNaPS 2026 06',
            'baf',
            '748100',
        )

        self.assertTrue(result['conforme'])
        self.assertEqual(result['details']['annee'], '2026')
        self.assertEqual(result['details']['mois'], '06')


class VerificationFournisseursCarburantTests(SimpleTestCase):
    def test_extraire_infos_carburant_extrait_une_immatriculation_sans_texte_duplique(self):
        result = extraire_infos_carburant(
            "ACHAT CARBURANT pour moto 16733WWT",
            "16733 WWT",
        )

        self.assertEqual(result['matricule_vehicule'], '16733WWT')

    def test_lookup_vehicule_utilise_la_meme_normalisation_que_les_donnees_extraites(self):
        vehicules = [
            SimpleNamespace(immatriculation='16733 WWT'),
            SimpleNamespace(immatriculation='11492 WWT'),
        ]
        vehicules_map = {
            _normalize_matricule(v.immatriculation): v.immatriculation
            for v in vehicules
            if v.immatriculation
        }

        extracted = extraire_infos_carburant(
            "ACHAT CARBURANT pour moto 16733WWT",
            "16733 WWT",
        )['matricule_vehicule']
        matricule_norm = _normalize_matricule(extracted)

        self.assertIn(matricule_norm, vehicules_map)
        self.assertEqual(vehicules_map[matricule_norm], '16733 WWT')

    def test_extraire_infos_carburant_accepte_une_plaque_avec_espace_dans_le_libelle(self):
        result = extraire_infos_carburant(
            "ACHAT CARBURANT pour moto 16733 WWT",
            "",
        )

        self.assertEqual(result['matricule_vehicule'], '16733WWT')

    def test_extraire_infos_carburant_accepte_une_plaque_avec_tiret_dans_le_libelle(self):
        result = extraire_infos_carburant(
            "ACHAT CARBURANT pour voiture 1234-ABC",
            "",
        )

        self.assertEqual(result['matricule_vehicule'], '1234ABC')
