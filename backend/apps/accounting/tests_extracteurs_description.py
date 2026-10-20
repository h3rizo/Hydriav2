from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounting.extracteurs_description import (
    extraire_indemnite_rbf_ppmh,
    extraire_installation_bp_bf,
    extraire_nom_abonne_underscore,
    extraire_ouvrage_et_mois_generique,
    extraire_remise_eau_descente_bp,
)
from apps.organization.models import Ouvrage, OuvrageAlias, TypeOuvrage


class PaiementForfaitaireOuvrageExtractionTests(TestCase):
    def setUp(self):
        self.type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG test')

    def test_reconnait_ouvrage_sans_espaces_et_restaure_nom_base(self):
        ouvrage = Ouvrage.objects.create(
            nom_ouvrage='Ambodivohitra / Tsaratampona II',
            type_ouvrage=self.type_ouvrage,
        )

        result = extraire_ouvrage_et_mois_generique(
            'Paiement forfaitaire_U_1_75000_Ambodivohitra/TsaratamponaII',
            '748411',
        )

        self.assertEqual(result['ouvrage_obj'], ouvrage)
        self.assertEqual(result['ouvrage_nom'], ouvrage.nom_ouvrage)

    def test_reconnait_alias_metier_et_restaure_nom_officiel(self):
        ouvrage = Ouvrage.objects.create(
            nom_ouvrage='Ambodivohitra / Tsaratampona II',
            type_ouvrage=self.type_ouvrage,
        )
        OuvrageAlias.objects.create(
            ouvrage=ouvrage,
            alias='Ambodivoutra Tsaratampona 2',
        )

        result = extraire_ouvrage_et_mois_generique(
            'Paiement forfaitaire_U_1_75000_ambodivoutra   tsaratampona 2',
            '748411',
        )

        self.assertEqual(result['ouvrage_obj'], ouvrage)
        self.assertEqual(result['ouvrage_nom'], ouvrage.nom_ouvrage)

    def test_refuse_meme_alias_normalise_pour_deux_ouvrages(self):
        ouvrage_a = Ouvrage.objects.create(
            nom_ouvrage='Ouvrage Alpha',
            type_ouvrage=self.type_ouvrage,
        )
        ouvrage_b = Ouvrage.objects.create(
            nom_ouvrage='Ouvrage Beta',
            type_ouvrage=self.type_ouvrage,
        )
        OuvrageAlias.objects.create(ouvrage=ouvrage_a, alias='Erreur Commune')

        with self.assertRaises(ValidationError):
            OuvrageAlias.objects.create(ouvrage=ouvrage_b, alias=' erreurcommune ')

    def test_refuse_alias_egal_au_nom_officiel_d_un_autre_ouvrage(self):
        Ouvrage.objects.create(
            nom_ouvrage='Ouvrage Alpha',
            type_ouvrage=self.type_ouvrage,
        )
        ouvrage_b = Ouvrage.objects.create(
            nom_ouvrage='Ouvrage Beta',
            type_ouvrage=self.type_ouvrage,
        )

        with self.assertRaises(ValidationError):
            OuvrageAlias.objects.create(ouvrage=ouvrage_b, alias='ouvragealpha')

    def test_alias_est_applique_aux_autres_extracteurs_generiques(self):
        ouvrage = Ouvrage.objects.create(
            nom_ouvrage='Vohilengo AEPG',
            type_ouvrage=self.type_ouvrage,
        )
        OuvrageAlias.objects.create(ouvrage=ouvrage, alias='Vohilenggo')

        result = extraire_ouvrage_et_mois_generique(
            'MANAMPIHERY Indiamihenina_Paiement pour devis installation BP_183_Vohilenggo',
            '748201',
        )

        self.assertEqual(result['ouvrage_obj'], ouvrage)
        self.assertEqual(result['ouvrage_nom'], ouvrage.nom_ouvrage)


class OuvrageAliasManagementViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='alias-tester',
            password='test-password',
        )
        self.client.force_login(self.user)
        type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG test')
        self.ouvrage = Ouvrage.objects.create(
            nom_ouvrage='Ambodivohitra / Tsaratampona II',
            type_ouvrage=type_ouvrage,
        )

    def test_page_gestion_aliases_est_accessible(self):
        response = self.client.get(
            reverse('accounting:gestion_aliases_ouvrages'),
            {'q': 'Ambodivohitra', 'ouvrage': self.ouvrage.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ouvrage.nom_ouvrage)

    def test_page_permet_ajout_alias(self):
        response = self.client.post(
            reverse('accounting:gestion_aliases_ouvrages'),
            {
                'action': 'add',
                'ouvrage_id': self.ouvrage.id,
                'q': 'Ambodivohitra',
                'alias': 'Ambodivoutra Tsaratampona 2',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(OuvrageAlias.objects.filter(
            ouvrage=self.ouvrage,
            alias='Ambodivoutra Tsaratampona 2',
        ).exists())


class RemiseEauDescenteBpExtractionTests(TestCase):
    def test_installation_bp_pour_devis_uses_last_segments(self):
        description = (
            'MANAMPIHERY Indiamihenina_Paiement pour devis installation '
            'BP_183_Vohilengo AEPG'
        )
        result = extraire_installation_bp_bf(description)

        self.assertEqual(result['point_eau_idxls'], '183')
        self.assertEqual(result['ouvrage_nom'], 'Vohilengo AEPG')

        generic = extraire_ouvrage_et_mois_generique(description, '748201')
        self.assertEqual(generic['point_eau_nom_extrait'], 'MANAMPIHERY Indiamihenina')
        self.assertEqual(generic['point_eau_idxls'], '183')
        self.assertEqual(generic['ouvrage_nom'], 'Vohilengo AEPG')

    def test_extracts_subscriber_before_first_underscore(self):
        self.assertEqual(
            extraire_nom_abonne_underscore('RAKOTONIRINA Martin_Paiement remise en eau_47_Vohipeno'),
            'RAKOTONIRINA Martin',
        )

    def test_extracts_subscriber_after_leading_underscore(self):
        self.assertEqual(
            extraire_nom_abonne_underscore('_RAKOTONIRINA Martin_Paiement remise en eau_47_Vohipeno'),
            'RAKOTONIRINA Martin',
        )

    def test_description_without_underscore_has_no_subscriber_candidate(self):
        self.assertIsNone(extraire_nom_abonne_underscore('Paiement remise en eau Vohipeno'))

    def test_remise_eau_uses_last_underscore_for_ouvrage_and_previous_number_for_idxls(self):
        result = extraire_remise_eau_descente_bp(
            '_RAKOTONIRINA Martin_Paiement remise en eau_47_Vohipeno'
        )

        self.assertEqual(result['nom_personne'], 'RAKOTONIRINA Martin')
        self.assertEqual(result['type_paiement'], 'remise_eau')
        self.assertEqual(result['point_eau_idxls'], '47')
        self.assertEqual(result['ouvrage_nom'], 'Vohipeno')

    def test_descente_bp_fallback_parses_tail_segments(self):
        result = extraire_remise_eau_descente_bp(
            '_Martin_Paiement_descente_BP_789_Anjahambe'
        )

        self.assertEqual(result['nom_personne'], 'Martin')
        self.assertEqual(result['type_paiement'], 'descente_bp')
        self.assertEqual(result['point_eau_idxls'], '789')
        self.assertEqual(result['ouvrage_nom'], 'Anjahambe')

    def test_generic_dispatch_supports_compte_761002(self):
        result = extraire_ouvrage_et_mois_generique(
            '_RAKOTONIRINA Martin_Paiement remise en eau_47_Vohipeno',
            '761002'
        )

        self.assertEqual(result['type_paiement'], 'remise_eau')
        self.assertEqual(result['point_eau_idxls'], '47')
        self.assertEqual(result['ouvrage_nom'], 'Vohipeno')
        self.assertEqual(result['point_eau_nom_extrait'], 'RAKOTONIRINA Martin')

    def test_indemnite_rbf_short_pattern_ignores_bracket_annotation(self):
        result = extraire_indemnite_rbf_ppmh(
            '_TSIMANAMBOHO Franclin_Indemnité RBF2_Ambalabe [RBF3]'
        )

        self.assertEqual(result['type_indemnite'], 'RBF')
        self.assertEqual(result['point_eau_idxls'], '2')
        self.assertEqual(result['ouvrage_nom'], 'Ambalabe')

    def test_generic_621102_extracts_subscriber_and_short_rbf_pattern(self):
        result = extraire_ouvrage_et_mois_generique(
            '_TSIMANAMBOHO Franclin_Indemnité RBF2_Ambalabe [RBF3]',
            '621102',
        )

        self.assertEqual(result['point_eau_nom_extrait'], 'TSIMANAMBOHO Franclin')
        self.assertEqual(result['point_eau_idxls'], '2')
        self.assertEqual(result['ouvrage_nom'], 'Ambalabe')
