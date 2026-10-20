"""Hydria Academy (apps.serious_game) est servi sur planning.hydria.mg."""
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

PLANNING_SETTINGS = dict(
    ALLOWED_HOSTS=['www.hydria.mg', 'planning.hydria.mg', 'testserver'],
    PLANNING_SUBDOMAIN_HOSTS=['planning.hydria.mg'],
    PLANNING_SUBDOMAIN_URL='https://planning.hydria.mg',
)


@override_settings(**PLANNING_SETTINGS)
class AcademyRedirectTests(SimpleTestCase):
    def test_main_site_redirects_to_planning_subdomain_with_query(self):
        response = self.client.get('/serious-game/quiz/?theme=1', HTTP_HOST='www.hydria.mg')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://planning.hydria.mg/serious-game/quiz/?theme=1')

    def test_routes_exist_in_planning_urlconf(self):
        self.assertEqual(reverse('serious_game:home', urlconf='hydria.urls_planning'), '/serious-game/')
        self.assertEqual(reverse('serious_game:quiz_themes', urlconf='hydria.urls_planning'), '/serious-game/quiz/')
        self.assertEqual(reverse('academy_shortcut', urlconf='hydria.urls_planning'), '/academy/')


@override_settings(**PLANNING_SETTINGS)
class AcademyPlanningShellTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='academy_planning', password='x-test-pass-1')
        self.client.force_login(self.user)

    def test_home_renders_inside_planning_shell(self):
        response = self.client.get('/serious-game/', HTTP_HOST='planning.hydria.mg')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'planning/base.html')
        # Bouton d'acces present dans la navbar et le sidebar du sous-domaine.
        self.assertContains(response, 'href="/serious-game/simulation/"')
        self.assertContains(response, 'Hydria Academy')

    def test_django_messages_are_displayed_in_planning_shell(self):
        from apps.serious_game.models import QuizTheme

        theme = QuizTheme.objects.create(nom='Theme sans question', actif=True)
        response = self.client.get(
            f'/serious-game/quiz/theme/{theme.id}/commencer/',
            HTTP_HOST='planning.hydria.mg',
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aucune question active')

    def test_planning_home_shows_academy_entry(self):
        response = self.client.get('/accueil/', HTTP_HOST='planning.hydria.mg')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/serious-game/"')
