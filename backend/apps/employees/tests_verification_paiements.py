from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.employees.views_verification_paiements import (
    extraire_info_description,
    verifier_compte_cat,
)


class VerificationPaiementsDescriptionTests(SimpleTestCase):
    def test_osiefsova_trimestre_case_variant_is_conforme(self):
        description = "_ST RANDRIANANTENAINA Alain_OSIEFSova_2025 4e trimestre [-1212526,97 split 1/10]"

        info = extraire_info_description(description)

        self.assertEqual(info["type_paiement"], "mutuelle_sante")
        self.assertEqual(info["annee"], 2025)
        self.assertEqual(info["mois"], 12)
        self.assertTrue(info["conforme"], info["erreurs"])

    def test_indemnite_compensatrice_conge_non_pris_is_conforme(self):
        description = "_MEN BIAKA Marie Jeanne_Indemnité compensatrice de congé non pris_2025"

        info = extraire_info_description(description)

        self.assertEqual(info["type_paiement"], "salaire")
        self.assertEqual(info["annee"], 2025)
        self.assertIsNone(info["mois"])
        self.assertTrue(info["conforme"], info["erreurs"])

    def test_prestation_admin_essai_is_treated_as_salaire(self):
        description = "_ADMIN RAKOTOARISOA Anique Bernard_Prestation admin à l'essai_Journée_27000_x 3"

        info = extraire_info_description(description)

        self.assertEqual(info["type_paiement"], "salaire")
        self.assertIsNone(info["annee"])
        self.assertIsNone(info["mois"])
        self.assertTrue(info["conforme"], info["erreurs"])

    def test_frais_medicaux_libres_is_conforme(self):
        description = "_DIR RAZAFINTSALAMA Herizo_Frais médicaux_gorge/consultation/medicament"

        info = extraire_info_description(description)

        self.assertEqual(info["type_paiement"], "frais_medicaux")
        self.assertIsNone(info["annee"])
        self.assertIsNone(info["mois"])
        self.assertTrue(info["conforme"], info["erreurs"])
