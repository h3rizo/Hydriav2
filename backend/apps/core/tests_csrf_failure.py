from django.contrib.messages import get_messages
from django.test import SimpleTestCase, Client, override_settings


@override_settings(ALLOWED_HOSTS=['testserver'])
class CsrfFailureViewTests(SimpleTestCase):
    """Le vrai CsrfViewMiddleware doit router vers apps.core.views_csrf.csrf_failure."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def test_login_jeton_perime_redirige_avec_message(self):
        url = '/accounts/login/?next=/accueil/'
        response = self.client.post(url, {'username': 'x', 'password': 'y'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], url)
        textes = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('session a expiré' in t for t in textes))

    def test_login_visiteur_redirige_vers_page_connexion(self):
        response = self.client.post('/accounts/login/visiteur/', {'email': 'a@b.mg'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/accounts/login/')

    def test_appel_api_recoit_json_403(self):
        response = self.client.post('/api/capture-gps/', {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'csrf')

    def test_autre_formulaire_garde_page_403(self):
        response = self.client.post('/comptabilite/import/', {'champ': 'valeur'})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('Location', response)
