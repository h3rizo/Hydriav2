import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.geography.models import Commune, District, Fokontany, Region, Village
from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute
from apps.geography.services import coupures as svc
from apps.geography.services.reseau_routier import longueur_geodesique_m


def noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


def troncon(a, b, coords):
    return TronconRoute.objects.create(
        noeud_debut=a, noeud_fin=b, geometrie=coords, longueur_m=longueur_geodesique_m(coords))


class CoupuresTests(TestCase):
    def setUp(self):
        # Réseau principal : long tronçon horizontal (A---B) + un second pour qu'il soit le plus grand.
        self.a, self.b, self.c = noeud(47.00, -18.00), noeud(47.02, -18.00), noeud(47.04, -18.00)
        self.t_ab = troncon(self.a, self.b, [[47.00, -18.00], [47.02, -18.00]])
        self.t_bc = troncon(self.b, self.c, [[47.02, -18.00], [47.04, -18.00]])
        # Morceau isolé à ~220 m au nord du milieu de A-B.
        # x est nettement plus proche du réseau que y : le point de raccord est donc sans ambiguïté.
        self.x, self.y = noeud(47.010, -17.998), noeud(47.012, -17.995)
        self.t_xy = troncon(self.x, self.y, [[47.010, -17.998], [47.012, -17.995]])
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        v = Village.objects.create(nom_village='Isolé', fokontany=fkt, latitude=Decimal('-17.998'), longitude=Decimal('47.011'))
        self.acces_isole = VillageAccesRoute.objects.create(
            village=v, troncon=self.t_xy, fraction=0.5, distance_m=0,
            longitude=Decimal('47.011'), latitude=Decimal('-17.998'), reseau_principal=False)
        w = Village.objects.create(nom_village='Sur A-B', fokontany=fkt, latitude=Decimal('-18.0'), longitude=Decimal('47.015'))
        self.acces_ab = VillageAccesRoute.objects.create(
            village=w, troncon=self.t_ab, fraction=0.75, distance_m=0,
            longitude=Decimal('47.015'), latitude=Decimal('-18.0'))

    def test_detecte_la_coupure_et_propose_un_raccord(self):
        liste = svc.lister_coupures()
        self.assertEqual(len(liste), 1)
        self.assertEqual(liste[0]['nb_villages'], 1)
        self.assertTrue(150 < liste[0]['ecart_m'] < 300)

    def test_raccord_decoupe_le_troncon_vise_et_reaffecte_les_acces(self):
        c = svc.lister_coupures()[0]
        t = svc.raccorder(c['from_noeud_id'], [], c['to'][0], c['to'][1])
        self.assertEqual(t.source, 'manuel')
        self.assertEqual(svc.lister_coupures(), [])
        self.assertEqual(TronconRoute.objects.count(), 5)  # 3 + raccord + moitié créée par la découpe
        self.acces_isole.refresh_from_db()
        self.assertTrue(self.acces_isole.reseau_principal)
        # Le village à 75 % de A-B passe sur la seconde moitié (la coupure est à ~50 %).
        self.acces_ab.refresh_from_db()
        self.assertNotEqual(self.acces_ab.troncon_id, self.t_ab.id)
        self.assertAlmostEqual(self.acces_ab.fraction, 0.5, delta=0.05)

    def test_refuse_une_arrivee_trop_loin_du_reseau(self):
        c = svc.lister_coupures()[0]
        with self.assertRaises(svc.RaccordInvalide):
            svc.raccorder(c['from_noeud_id'], [], 47.01, -17.90)

    def test_api_reservee_au_staff(self):
        url = reverse('geography:api_coupures_liste')
        self.assertEqual(self.client.get(url).status_code, 401)
        User = get_user_model()
        self.client.force_login(User.objects.create_user('simple', password='x'))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(User.objects.create_user('admin', password='x', is_staff=True))
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['coupures']), 1)

    def test_api_raccorder(self):
        User = get_user_model()
        self.client.force_login(User.objects.create_user('admin', password='x', is_staff=True))
        c = svc.lister_coupures()[0]
        r = self.client.post(reverse('geography:api_coupure_raccorder'),
                             data=json.dumps({'from_noeud_id': c['from_noeud_id'], 'waypoints': [], 'fin': c['to']}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['success'])

    def test_page_reservee_au_staff_et_se_rend(self):
        url = reverse('geography:coupures_routes')
        self.assertEqual(self.client.get(url).status_code, 302)  # redirige vers la connexion
        User = get_user_model()
        self.client.force_login(User.objects.create_user('admin', password='x', is_staff=True))
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Coupures du réseau routier')
