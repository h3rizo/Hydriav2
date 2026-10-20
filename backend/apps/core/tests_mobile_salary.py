import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import ConfigSalaire, ConfigTrancheIRSA


class MobileSalaryConfigTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="salary-mobile", password="secret")
        self.config = ConfigSalaire.objects.create(
            salaire_minimum="262680.00",
            deduction_irsa="2000.00",
            minimum_irsa="3000.00",
        )
        ConfigTrancheIRSA.objects.create(ordre=1, tranche_superieure="350000.00", pourcentage="0.00")
        ConfigTrancheIRSA.objects.create(ordre=2, tranche_superieure="400000.00", pourcentage="5.00")

    def test_authentication_is_required(self):
        response = self.client.get(reverse("core:mobile_salary_calculation_config"))
        self.assertEqual(response.status_code, 401)

    def test_configuration_uses_decimal_strings_and_complete_formula_contract(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:mobile_salary_calculation_config"))
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        configuration = payload["configuration"]
        self.assertEqual(configuration["formula_version"], 1)
        self.assertEqual(configuration["organisation"], "global")
        self.assertEqual(configuration["parameters"]["minimum_salary"], "262680.00")
        self.assertEqual(configuration["parameters"]["guardian_reference_hours"], "240")
        self.assertEqual(configuration["parameters"]["taxable_base_rounding_mode"], "FLOOR")
        self.assertEqual(len(configuration["irsa_brackets"]), 2)
        self.assertEqual(len(configuration["checksum"]), 64)

    def test_known_checksum_returns_differential_response(self):
        self.client.force_login(self.user)
        first = self.client.get(reverse("core:mobile_salary_calculation_config")).json()
        checksum = first["configuration"]["checksum"]
        second = self.client.get(reverse("core:mobile_salary_calculation_config"), {"checksum": checksum}).json()
        self.assertTrue(second["unchanged"])
        self.assertEqual(second["checksum"], checksum)
        self.assertNotIn("configuration", second)
