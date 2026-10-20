from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.recrutement.models import Candidat, SessionTest


class CompletedCandidateAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='candidat@example.com',
            email='candidat@example.com',
            password='testpass123',
        )
        pdf_file = SimpleUploadedFile('cv.pdf', b'%PDF-1.4 test file', content_type='application/pdf')
        lettre_file = SimpleUploadedFile('lettre.pdf', b'%PDF-1.4 lettre', content_type='application/pdf')
        self.candidat = Candidat.objects.create(
            user=self.user,
            nom='Doe',
            prenom='Jane',
            email='candidat@example.com',
            telephone='0340000000',
            experience='Experience',
            formation='Formation',
            adresse='Tana',
            statut='test_termine',
            cv=pdf_file,
            lettre_motivation=lettre_file,
        )
        self.session = SessionTest.objects.create(
            candidat=self.candidat,
            statut='termine',
        )

    def test_completed_candidate_is_redirected_away_from_home_launcher(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('home_launcher'))

        self.assertRedirects(
            response,
            reverse('recrutement:resultats', kwargs={'session_id': self.session.id}),
            fetch_redirect_response=False,
        )

    def test_completed_candidate_can_still_open_results_page(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('recrutement:resultats', kwargs={'session_id': self.session.id})
        )

        self.assertEqual(response.status_code, 200)
