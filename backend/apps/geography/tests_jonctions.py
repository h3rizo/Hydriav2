from decimal import Decimal

import networkx as nx
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.geography.models_routes import NoeudRoute, TronconRoute
from apps.geography.services import jonctions
from apps.geography.services.reseau_routier import longueur_geodesique_m


def noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


def troncon(a, b, coords):
    return TronconRoute.objects.create(noeud_debut=a, noeud_fin=b, geometrie=coords,
                                       longueur_m=longueur_geodesique_m(coords))


def connexe():
    g = nx.Graph()
    g.add_edges_from(TronconRoute.objects.values_list('noeud_debut_id', 'noeud_fin_id'))
    return nx.number_connected_components(g) == 1


class JonctionsTests(TestCase):
    def setUp(self):
        # Route 1 : horizontale de 4,4 km. Route 2 : verticale qui s'arrête 22 m au nord de la route 1.
        self.n1, self.n2 = noeud(47.00, -18.0), noeud(47.04, -18.0)
        self.t1 = troncon(self.n1, self.n2, [[47.00, -18.0], [47.04, -18.0]])
        self.n3, self.n4 = noeud(47.02, -17.9998), noeud(47.02, -17.98)
        self.t2 = troncon(self.n3, self.n4, [[47.02, -17.9998], [47.02, -17.98]])

    def test_chercher_trouve_la_jonction(self):
        c = jonctions.chercher(jonctions.charger(), rayon_m=50, ecart_m=500)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]['noeud_id'], self.n3.id)
        self.assertTrue(15 < c[0]['distance_m'] < 30)
        self.assertAlmostEqual(c[0]['fraction'], 0.5, delta=0.01)

    def test_tolerance_trop_petite_ne_fait_rien(self):
        self.assertEqual(jonctions.nettoyer_auto(tol_m=10, ecart_m=500), 0)
        self.assertFalse(connexe())

    def test_dry_run_n_ecrit_rien(self):
        self.assertEqual(jonctions.nettoyer_auto(tol_m=30, ecart_m=500, dry_run=True), 1)
        self.assertEqual(TronconRoute.objects.count(), 2)

    def test_nettoyage_relie_et_decoupe(self):
        self.assertEqual(jonctions.nettoyer_auto(tol_m=30, ecart_m=500), 1)
        self.assertTrue(connexe())
        self.assertEqual(TronconRoute.objects.count(), 4)   # route 1 coupée en 2 + jonction + route 2
        j = TronconRoute.objects.get(type_voie='jonction')
        self.assertEqual(j.source, 'raccord')
        self.assertTrue(15 < j.longueur_m < 30)
        # rien à refaire ensuite
        self.assertEqual(jonctions.nettoyer_auto(tol_m=30, ecart_m=500), 0)

    def test_noeud_deja_sur_la_route_decoupe_sans_jonction(self):
        n5 = noeud(47.02, -18.0)   # exactement sur la route 1, qui n'est pas coupée à cet endroit
        n6 = noeud(47.02, -17.99)
        troncon(n5, n6, [[47.02, -18.0], [47.02, -17.99]])
        r = jonctions.relier(n5.id, self.t1.id, 0.5)
        self.assertIsNone(r)
        self.assertEqual(TronconRoute.objects.filter(type_voie='jonction').count(), 0)
        self.assertEqual(TronconRoute.objects.count(), 4)   # route 1 coupée en 2

    def test_api_jonctions(self):
        user = get_user_model().objects.create_user('admin', password='x', is_staff=True)
        url = reverse('geography:api_jonctions_liste')
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(get_user_model().objects.create_user('simple', password='x'))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(user)
        d = self.client.get(url, {'rayon_m': 50, 'ecart_m': 500}).json()
        self.assertEqual(d['total'], 1)
        j = d['jonctions'][0]
        r = self.client.post(reverse('geography:api_jonction_relier'), data={
            'noeud_id': j['noeud_id'], 'troncon_id': j['troncon_id'], 'fraction': j['fraction']},
            content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(connexe())
        ctx = self.client.get(reverse('geography:api_jonctions_contexte'), {'lon': 47.02, 'lat': -18.0}).json()
        self.assertTrue(ctx['success'])
        self.assertEqual(len(ctx['troncons']['features']), 4)
        self.assertEqual(self.client.get(reverse('geography:jonctions_routes')).status_code, 200)
