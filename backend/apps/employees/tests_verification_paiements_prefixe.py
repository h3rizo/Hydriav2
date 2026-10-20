from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.employees.views_verification_paiements import verifier_compte_cat


class VerificationPaiementsPrefixeTests(SimpleTestCase):
    @patch('apps.employees.views_verification_paiements._get_postes_for_prefix')
    def test_indemnite_terrain_uses_prefix_fallback_when_employe_missing(self, mock_get_postes):
        compte_indemnite = SimpleNamespace(compte='625125', nom_compte='Indemnite terrain')
        poste_admin = SimpleNamespace(
            id='poste-admin-1',
            nom_poste='Assistante admin',
            compte_salaire=None,
            compte_irsa=None,
            compte_cnaps_fmfp_sante=None,
            compte_indemnite=compte_indemnite,
        )
        mock_get_postes.return_value = [poste_admin]

        result = verifier_compte_cat(
            '625125',
            'indemnite_terrain',
            employe_obj=None,
            prefixe='ADMIN',
        )

        self.assertTrue(result['correct'], result)
        self.assertEqual(result['attendu'], '625125')

    @patch('apps.employees.views_verification_paiements._get_postes_for_prefix')
    def test_indemnite_terrain_uses_prefix_fallback_when_current_poste_lacks_account(self, mock_get_postes):
        poste_sans_compte = SimpleNamespace(
            id='poste-admin-0',
            prefixe='ADMIN',
            nom_poste='Assistante admin',
            compte_salaire=None,
            compte_irsa=None,
            compte_cnaps_fmfp_sante=None,
            compte_indemnite=None,
        )
        compte_indemnite = SimpleNamespace(compte='625125', nom_compte='Indemnite terrain')
        poste_admin_valide = SimpleNamespace(
            id='poste-admin-1',
            prefixe='ADMIN',
            nom_poste='Caissiere',
            compte_salaire=None,
            compte_irsa=None,
            compte_cnaps_fmfp_sante=None,
            compte_indemnite=compte_indemnite,
        )
        employe = SimpleNamespace(poste=poste_sans_compte)
        mock_get_postes.return_value = [poste_sans_compte, poste_admin_valide]

        result = verifier_compte_cat(
            '625125',
            'indemnite_terrain',
            employe_obj=employe,
            prefixe='ADMIN',
        )

        self.assertTrue(result['correct'], result)
        self.assertEqual(result['attendu'], '625125')
