import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.geography.models import Commune, District, Fokontany, Region, Village
from apps.geography.models_routes import NoeudRoute, TronconRoute
from apps.geography.services import itineraire as it
from apps.geography.services import lieux
from apps.geography.services.reseau_routier import longueur_geodesique_m
from apps.organization.models import Base, Organisation


def noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


class LieuxBasesTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='Commune F', district=district)
        self.fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        self.village = Village.objects.create(nom_village='Fénérive Est', fokontany=self.fkt,
                                              latitude=Decimal('-17.38'), longitude=Decimal('49.41'))
        Village.objects.create(nom_village='Fénérive Ouest', fokontany=self.fkt,
                               latitude=Decimal('-17.39'), longitude=Decimal('49.30'))
        org = Organisation.objects.create(nom_organisation='Org')
        self.base = Base.objects.create(nom_base='Fénérive Est', organisation=org)
        self.sans_nom_village = Base.objects.create(nom_base='Siège', organisation=org)
        # Route horizontale de 4,4 km, à 1,1 km au sud du village.
        a, b = noeud(49.38, -17.39), noeud(49.42, -17.39)
        coords = [[49.38, -17.39], [49.42, -17.39]]
        self.route = TronconRoute.objects.create(noeud_debut=a, noeud_fin=b, geometrie=coords, categorie='route',
                                                 longueur_m=longueur_geodesique_m(coords))

    def admin(self):
        self.client.force_login(get_user_model().objects.create_user('admin', password='x', is_staff=True))

    def test_lieu_depart_priorite_gps_puis_village(self):
        self.assertIsNone(self.base.lieu_depart)
        self.base.village_depart = self.village
        self.assertEqual(self.base.lieu_depart, (49.41, -17.38, 'Fénérive Est'))
        self.base.latitude_depart, self.base.longitude_depart = Decimal('-17.50'), Decimal('49.00')
        self.assertEqual(self.base.lieu_depart, (49.0, -17.5, 'Fénérive Est'))        # la position GPS prime
        self.base.village_depart = None
        self.assertEqual(self.base.lieu_depart, (49.0, -17.5, 'Fénérive Est'))        # libellé = nom de la base

    def test_acces_point_projette_sur_la_route_la_plus_proche(self):
        a = lieux.acces_point(49.40, -17.38, nom='Base')
        self.assertEqual(a['troncon_id'], self.route.id)
        self.assertAlmostEqual(a['distance_m'], 1100, delta=60)
        self.assertAlmostEqual(a['fraction'], 0.5, delta=0.01)
        # utilisable directement par le moteur d'itinéraire
        autre = lieux.acces_point(49.39, -17.39)
        r = it.reseau().itineraire(a, autre, 'temps', 'moto')
        self.assertGreater(r['distance_m'], 0)

    def test_acces_point_hors_madagascar(self):
        with self.assertRaises(it.ItineraireIntrouvable):
            lieux.acces_point(2.35, 48.85)

    def test_acces_base(self):
        self.assertIsNone(lieux.acces_base(self.base))
        self.base.latitude_depart, self.base.longitude_depart = Decimal('-17.38'), Decimal('49.40')
        a = lieux.acces_base(self.base)
        self.assertEqual(a['nom'], 'Fénérive Est')

    def test_api_droits_et_liste_avec_suggestions(self):
        url = reverse('geography:api_bases_liste')
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(get_user_model().objects.create_user('simple', password='x'))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.admin()
        d = self.client.get(url).json()
        par_nom = {b['nom']: b for b in d['bases']}
        self.assertIsNone(par_nom['Siège']['lieu'])
        self.assertEqual(par_nom['Siège']['suggestions'], [])
        sug = par_nom['Fénérive Est']['suggestions']
        self.assertEqual([s['nom'] for s in sug], ['Fénérive Est'])                  # le nom exact est seul retenu
        self.assertTrue(sug[0]['exact'])
        # un nom de base qui n'est que le début du nom d'un village ne le suggère pas
        Village.objects.create(nom_village='Tanambao', fokontany=self.fkt, latitude=Decimal('-17.5'), longitude=Decimal('49.1'))
        Base.objects.create(nom_base='Tana', organisation=self.base.organisation)
        # et un village de même premier mot est suggéré en secours
        Village.objects.create(nom_village='Vavatenina Centre', fokontany=self.fkt, latitude=Decimal('-17.4'), longitude=Decimal('49.2'))
        Base.objects.create(nom_base='Vavatenina SK', organisation=self.base.organisation)
        d = self.client.get(url).json()
        par_nom = {b['nom']: b for b in d['bases']}
        self.assertEqual(par_nom['Tana']['suggestions'], [])
        self.assertEqual([s['nom'] for s in par_nom['Vavatenina SK']['suggestions']], ['Vavatenina Centre'])
        self.assertFalse(par_nom['Vavatenina SK']['suggestions'][0]['exact'])

    def test_api_placer_un_lieu_puis_le_retirer(self):
        self.admin()
        url = reverse('geography:api_base_lieu', args=[self.base.id])
        r = self.client.post(url, data=json.dumps({'lon': 49.40, 'lat': -17.38, 'village_id': str(self.village.id)}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()['base']
        self.assertEqual(d['lieu']['village_id'], str(self.village.id))
        self.assertAlmostEqual(d['distance_route_m'], 1100, delta=80)
        self.base.refresh_from_db()
        self.assertEqual(self.base.village_depart_id, self.village.id)
        self.assertEqual(self.base.longitude_depart, Decimal('49.4000000'))
        r = self.client.post(url, data=json.dumps({'effacer': True}), content_type='application/json')
        self.assertTrue(r.json()['success'])
        self.base.refresh_from_db()
        self.assertIsNone(self.base.lieu_depart)

    def test_api_refuse_les_positions_invalides(self):
        self.admin()
        url = reverse('geography:api_base_lieu', args=[self.base.id])
        for corps in ({'lon': 2.35, 'lat': 48.85}, {'lon': 'abc', 'lat': 1}, {}, {'lon': 49.4, 'lat': -17.4, 'village_id': '00000000-0000-0000-0000-000000000000'}):
            r = self.client.post(url, data=json.dumps(corps), content_type='application/json')
            self.assertEqual(r.status_code, 400, corps)
        self.base.refresh_from_db()
        self.assertIsNone(self.base.lieu_depart)

    def test_page(self):
        self.assertEqual(self.client.get(reverse('geography:lieux_bases')).status_code, 302)
        self.admin()
        r = self.client.get(reverse('geography:lieux_bases'))
        self.assertContains(r, 'Lieux des bases')

    def test_lien_depuis_la_page_des_organisations(self):
        lien = reverse('geography:lieux_bases')
        self.client.force_login(get_user_model().objects.create_user('simple', password='x'))
        self.assertNotContains(self.client.get(reverse('organization:list')), lien)      # réservé aux administrateurs
        self.admin()
        r = self.client.get(reverse('organization:list'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, lien)
        self.assertContains(r, 'Lieux des bases')

