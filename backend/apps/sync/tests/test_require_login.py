"""La connexion obligatoire (mode enforce en production) doit laisser passer login/refresh de la synchro,
mais pas les autres routes sans jeton. Régression constatée au déploiement du 2026-10-25."""
from django.test import RequestFactory, SimpleTestCase, override_settings

from hydria.require_login import RequireLoginMiddleware


@override_settings(REQUIRE_LOGIN_MODE='enforce')
class ConnexionObligatoireTests(SimpleTestCase):
    def setUp(self):
        self.fabrique = RequestFactory()
        self.middleware = RequireLoginMiddleware(lambda requete: 'passe')

    def exempte(self, chemin, **entetes):
        return self.middleware._is_exempt(self.fabrique.post(chemin, **entetes))

    def test_login_et_refresh_sans_session_passent(self):
        self.assertTrue(self.exempte('/api/sync/auth/login'))
        self.assertTrue(self.exempte('/api/sync/auth/refresh'))

    def test_autres_routes_sans_jeton_restent_bloquees(self):
        for chemin in ('/api/sync/changes', '/api/sync/arborescence', '/api/sync/upload',
                       '/api/fichiers/', '/api/fichiers/11111111-1111-4111-8111-111111111111/telechargement'):
            self.assertFalse(self.exempte(chemin), chemin)

    def test_avec_en_tete_authorization_la_vue_valide_le_jeton(self):
        self.assertTrue(self.exempte('/api/sync/changes', HTTP_AUTHORIZATION='Bearer abc'))
