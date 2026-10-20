from django.contrib.auth import get_user_model
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import ModaliteGestion, PointEau
from apps.organization.models import Organisation, Ouvrage, TypeOuvrage
from hydria.views import calculate_dashboard_stats_with_permissions


class CustomLoginRedirectionTests(TestCase):
    """CustomLoginView.get_success_url() doit prioriser un ?next= valide/sur
    avant sa logique metier existante (candidat/client/accueil), tout en
    preservant cette logique quand next est absent ou invalide."""

    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username='login_redirect_tests', password='testpass123',
        )

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_next_valide_est_priorise(self):
        cible = '/systeme/parameters/'
        response = self.client.post(
            reverse('login'),
            {'username': 'login_redirect_tests', 'password': 'testpass123', 'next': cible},
        )
        self.assertRedirects(response, cible, fetch_redirect_response=False)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_next_externe_invalide_retombe_sur_logique_existante(self):
        response = self.client.post(
            reverse('login'),
            {
                'username': 'login_redirect_tests', 'password': 'testpass123',
                'next': 'https://malicious-external-site.example/',
            },
        )
        # Ne doit jamais rediriger vers le domaine externe.
        self.assertNotIn('malicious-external-site', response.url)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_sans_next_comportement_par_defaut_inchange(self):
        response = self.client.post(
            reverse('login'),
            {'username': 'login_redirect_tests', 'password': 'testpass123'},
        )
        self.assertRedirects(response, reverse('home_launcher'), fetch_redirect_response=False)


class DashboardCurrentManagementScopeTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.current_year = today.year
        self.organisation = Organisation.objects.create(
            nom_organisation='Gestionnaire dashboard',
            type_organisation=Organisation.TYPE_GESTIONNAIRE,
        )
        ouvrage_type = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG')

        self.current_ouvrage = Ouvrage.objects.create(
            nom_ouvrage='Ouvrage actuellement gere',
            type_ouvrage=ouvrage_type,
            annee_realisation=self.current_year,
        )
        self.future_ouvrage = Ouvrage.objects.create(
            nom_ouvrage='Ouvrage gere dans le futur',
            type_ouvrage=ouvrage_type,
            annee_realisation=self.current_year,
        )
        self.unmanaged_ouvrage = Ouvrage.objects.create(
            nom_ouvrage='Ouvrage sans modalite',
            type_ouvrage=ouvrage_type,
            annee_realisation=self.current_year,
        )

        for index, ouvrage in enumerate((
            self.current_ouvrage,
            self.future_ouvrage,
            self.unmanaged_ouvrage,
        )):
            PointEau.objects.create(
                code_point_eau=f'PE-DASH-{index}',
                nomabonne=f'Point dashboard {index}',
                ouvrage=ouvrage,
            )

        ModaliteGestion.objects.create(
            ouvrage=self.current_ouvrage,
            gestionnaire=self.organisation,
            type_gestion='privee',
            date_debut=today - timedelta(days=30),
            modalitepaiement='au_volume',
        )
        ModaliteGestion.objects.create(
            ouvrage=self.future_ouvrage,
            gestionnaire=self.organisation,
            type_gestion='privee',
            date_debut=today + timedelta(days=30),
            modalitepaiement='au_volume',
        )

    def test_global_dashboard_counts_all_ouvrages_without_management_filter(self):
        stats = calculate_dashboard_stats_with_permissions(Ouvrage.objects.all())

        self.assertEqual(stats['ouvrages'], 3)

    def test_organisation_dashboard_excludes_future_ouvrage(self):
        stats = calculate_dashboard_stats_with_permissions(
            Ouvrage.objects.all(),
            organisation_id=str(self.organisation.id),
        )

        self.assertEqual(stats['ouvrages'], 1)

    def test_current_year_dashboard_stops_at_today(self):
        stats = calculate_dashboard_stats_with_permissions(
            Ouvrage.objects.all(),
            organisation_id=str(self.organisation.id),
            annee=str(self.current_year),
        )

        self.assertEqual(stats['ouvrages'], 1)
