from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.geography.models_routes import NoeudRoute, TronconRoute
from apps.geography.services.reseau_routier import longueur_geodesique_m


def _noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


class ItineraireMobileTests(TestCase):
    """GET /navigation-terrain/api/mobile/itineraire/ : position GPS -> entité, par la route."""

    def setUp(self):
        a, b, c = _noeud(47.00, -18.0), _noeud(47.02, -18.0), _noeud(47.04, -18.0)
        for n1, n2, coords, cat in ((a, b, [[47.00, -18.0], [47.02, -18.0]], 'route'),
                                    (b, c, [[47.02, -18.0], [47.04, -18.0]], 'sentier')):
            TronconRoute.objects.create(noeud_debut=n1, noeud_fin=n2, geometrie=coords, categorie=cat,
                                        longueur_m=longueur_geodesique_m(coords))
        self.user = get_user_model().objects.create_user(username='agent', password='x')
        self.client.force_login(self.user)
        self.url = reverse('navigation_terrain:mobile_itineraire')
        self.params = {'from_lat': -18.0, 'from_lon': 47.001, 'to_lat': -18.0, 'to_lon': 47.039}

    def test_authentification_requise(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url, self.params).status_code, 401)

    def test_parametres_manquants_ou_invalides(self):
        self.assertEqual(self.client.get(self.url, {'from_lat': -18}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {**self.params, 'profil': 'fusée'}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {**self.params, 'from_lat': 'abc'}).status_code, 400)

    def test_position_hors_de_madagascar(self):
        r = self.client.get(self.url, {**self.params, 'from_lat': 48.8, 'from_lon': 2.3})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.json()['success'])

    def test_itineraire_par_la_route(self):
        r = self.client.get(self.url, self.params)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d['success'])
        self.assertAlmostEqual(d['distance_km'], 4.1, delta=0.2)      # ~0,038° de longitude à -18°
        self.assertGreater(d['duree_minutes'], 0)
        self.assertEqual(d['geometrie']['type'], 'LineString')
        self.assertGreaterEqual(len(d['geometrie']['coordinates']), 3)
        self.assertIn('sentier', d['repartition_km'])

    def test_le_profil_change_la_duree(self):
        moto = self.client.get(self.url, {**self.params, 'profil': 'moto'}).json()
        pied = self.client.get(self.url, {**self.params, 'profil': 'pied'}).json()
        self.assertEqual(pied['profil'], 'pied')
        self.assertGreater(pied['duree_minutes'], moto['duree_minutes'] * 2)
