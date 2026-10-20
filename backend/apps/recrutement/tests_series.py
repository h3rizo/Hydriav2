from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Poste
from apps.organization.models import Organisation
from apps.recrutement.models import EntretienQuestion, QuestionTest


class SuperviseurTechniqueSeriesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.admin = user_model.objects.create_superuser(
            username='admin_series_st',
            email='admin_series_st@example.com',
            password='testpass123',
        )
        organisation = Organisation.objects.create(
            nom_organisation='Org recrutement',
            type_organisation=Organisation.TYPE_GESTIONNAIRE,
        )
        cls.poste = Poste.objects.create(
            nom_poste='Superviseur technique',
            organisation=organisation,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_create_superviseur_technique_test_series_is_idempotent(self):
        url = reverse('recrutement:api_creer_serie_superviseur_technique')

        first_response = self.client.post(url)
        self.assertEqual(first_response.status_code, 200)
        first_payload = first_response.json()
        self.assertTrue(first_payload['success'])
        self.assertEqual(first_payload['created_count'], 12)
        self.assertEqual(first_payload['skipped_count'], 0)
        self.assertEqual(QuestionTest.objects.filter(poste=self.poste).count(), 12)

        second_response = self.client.post(url)
        self.assertEqual(second_response.status_code, 200)
        second_payload = second_response.json()
        self.assertTrue(second_payload['success'])
        self.assertEqual(second_payload['created_count'], 0)
        self.assertEqual(second_payload['skipped_count'], 12)
        self.assertEqual(QuestionTest.objects.filter(poste=self.poste).count(), 12)

    def test_create_superviseur_technique_entretien_series_is_idempotent(self):
        url = reverse('recrutement:api_creer_serie_entretien_superviseur_technique')

        first_response = self.client.post(url)
        self.assertEqual(first_response.status_code, 200)
        first_payload = first_response.json()
        self.assertTrue(first_payload['success'])
        self.assertEqual(first_payload['created_count'], 10)
        self.assertEqual(first_payload['skipped_count'], 0)
        self.assertEqual(EntretienQuestion.objects.filter(poste=self.poste).count(), 10)

        second_response = self.client.post(url)
        self.assertEqual(second_response.status_code, 200)
        second_payload = second_response.json()
        self.assertTrue(second_payload['success'])
        self.assertEqual(second_payload['created_count'], 0)
        self.assertEqual(second_payload['skipped_count'], 10)
        self.assertEqual(EntretienQuestion.objects.filter(poste=self.poste).count(), 10)
