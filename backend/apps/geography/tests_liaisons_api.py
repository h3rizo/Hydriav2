import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Commune, District, Fokontany, LiaisonVillage, Region, Village


class LiaisonsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        fokontany = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        cls.a = Village.objects.create(nom_village='A', fokontany=fokontany, latitude=-18.0, longitude=47.0)
        cls.b = Village.objects.create(nom_village='B', fokontany=fokontany, latitude=-18.1, longitude=47.1)
        cls.user = get_user_model().objects.create_user('u', password='p')

    def post(self, url, data):
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def test_requires_login(self):
        response = self.post(reverse('geography:api_liaison_create'), {})
        self.assertEqual(response.status_code, 401)

    def test_create_update_delete(self):
        self.client.force_login(self.user)
        response = self.post(reverse('geography:api_liaison_create'), {
            'source_id': str(self.a.id), 'cible_id': str(self.b.id),
            'type_liaison': 'desserte', 'moyen_acces': 'moto', 'distance_km': '3,5', 'temps_acces_minutes': 40,
        })
        self.assertEqual(response.status_code, 201, response.content)
        liaison = response.json()['liaison']
        self.assertEqual(liaison['distance_km'], 3.5)
        self.assertIsNotNone(liaison['distance_vol_oiseau_km'])

        duplicate = self.post(reverse('geography:api_liaison_create'), {
            'source_id': str(self.a.id), 'cible_id': str(self.b.id), 'type_liaison': 'desserte',
        })
        self.assertEqual(duplicate.status_code, 409)

        update = self.post(reverse('geography:api_liaison_update', args=[liaison['id']]), {
            'distance_km': 4, 'moyen_acces': 'pied', 'inverser': True,
        })
        self.assertEqual(update.status_code, 200, update.content)
        obj = LiaisonVillage.objects.get(pk=liaison['id'])
        self.assertEqual(obj.village_source_id, self.b.id)
        self.assertEqual(obj.moyen_acces, 'pied')
        self.assertEqual(obj.temps_acces_minutes, 40)

        bad = self.post(reverse('geography:api_liaison_update', args=[liaison['id']]), {'moyen_acces': 'fusee'})
        self.assertEqual(bad.status_code, 400)

        delete = self.post(reverse('geography:api_liaison_delete', args=[liaison['id']]), {})
        self.assertEqual(delete.status_code, 200)
        self.assertFalse(LiaisonVillage.objects.filter(pk=liaison['id']).exists())

    def test_self_link_rejected(self):
        self.client.force_login(self.user)
        response = self.post(reverse('geography:api_liaison_create'), {
            'source_id': str(self.a.id), 'cible_id': str(self.a.id),
        })
        self.assertEqual(response.status_code, 400)


class LiaisonsGeojsonBboxTests(TestCase):
    """GET /geography/api/geojson/liaisons-villages/?bbox=ouest,sud,est,nord"""

    def setUp(self):
        from decimal import Decimal
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)

        def village(nom, lon, lat):
            return Village.objects.create(nom_village=nom, fokontany=fkt, longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))
        a, b, c, d = village('A', 47.0, -18.0), village('B', 47.1, -18.0), village('C', 49.0, -15.0), village('D', 49.1, -15.0)
        LiaisonVillage.objects.create(village_source=a, village_cible=b)
        LiaisonVillage.objects.create(village_source=c, village_cible=d)
        self.user = get_user_model().objects.create_user(username='u', password='x')
        self.client.force_login(self.user)
        self.url = reverse('geography:api_geojson_liaisons_villages')

    def test_sans_bbox_tout_est_renvoye(self):
        self.assertEqual(len(self.client.get(self.url).json()['features']), 2)

    def test_bbox_filtre_sur_la_zone(self):
        features = self.client.get(self.url, {'bbox': '46.5,-18.5,47.5,-17.5'}).json()['features']
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]['properties']['source_nom'], 'A')

    def test_bbox_invalide(self):
        self.assertEqual(self.client.get(self.url, {'bbox': 'abc'}).status_code, 400)


class RoutesReseauGeojsonTests(TestCase):
    """GET /geography/api/geojson/routes-reseau/?bbox=...&zoom=N"""

    def setUp(self):
        from decimal import Decimal
        from apps.geography.models_routes import NoeudRoute, TronconRoute
        from apps.geography.services.reseau_routier import longueur_geodesique_m

        def noeud(lon, lat):
            return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))
        a, b, c = noeud(47.0, -18.0), noeud(47.1, -18.0), noeud(47.2, -18.0)
        for n1, n2, coords, cat in ((a, b, [[47.0, -18.0], [47.1, -18.0]], 'nationale'),
                                    (b, c, [[47.1, -18.0], [47.2, -18.0]], 'sentier')):
            TronconRoute.objects.create(noeud_debut=n1, noeud_fin=n2, geometrie=coords, categorie=cat,
                                        longueur_m=longueur_geodesique_m(coords))
        self.user = get_user_model().objects.create_user(username='r', password='x')
        self.client.force_login(self.user)
        self.url = reverse('geography:api_geojson_routes_reseau')
        self.bbox = '46.9,-18.1,47.3,-17.9'

    def categories(self, zoom):
        d = self.client.get(self.url, {'bbox': self.bbox, 'zoom': zoom}).json()
        return sorted(f['properties']['categorie'] for f in d['features'])

    def test_zoom_trop_faible_ne_renvoie_rien(self):
        self.assertEqual(self.categories(6), [])

    def test_les_categories_dependent_du_zoom(self):
        self.assertEqual(self.categories(9), ['nationale'])
        self.assertEqual(self.categories(11), ['nationale'])
        self.assertEqual(self.categories(13), ['nationale', 'sentier'])

    def test_bbox_hors_zone(self):
        d = self.client.get(self.url, {'bbox': '10,10,11,11', 'zoom': 13}).json()
        self.assertEqual(d['features'], [])

    def test_parametres_invalides(self):
        self.assertEqual(self.client.get(self.url, {'bbox': 'abc'}).status_code, 400)


class VillagesNonReliesGeojsonTests(TestCase):
    """GET /geography/api/geojson/villages-non-relies/"""

    def setUp(self):
        from decimal import Decimal
        from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        a = NoeudRoute.objects.create(longitude=Decimal('47.0'), latitude=Decimal('-18.0'))
        b = NoeudRoute.objects.create(longitude=Decimal('47.1'), latitude=Decimal('-18.0'))
        t = TronconRoute.objects.create(noeud_debut=a, noeud_fin=b, geometrie=[[47.0, -18.0], [47.1, -18.0]],
                                        categorie='route', longueur_m=10000)

        def village(nom, lon, distance, principal=True):
            v = Village.objects.create(nom_village=nom, fokontany=fkt, longitude=Decimal(str(lon)), latitude=Decimal('-18.0'))
            VillageAccesRoute.objects.create(village=v, troncon=t, fraction=0.5, distance_m=distance,
                                             longitude=Decimal('47.05'), latitude=Decimal('-18.0'), reseau_principal=principal)
        village('Relie', 47.05, 20)
        village('Eloigne', 47.06, 2500)
        village('Isole', 47.07, 30, principal=False)
        village('Les deux', 47.08, 1500, principal=False)
        self.user = get_user_model().objects.create_user(username='n', password='x')
        self.client.force_login(self.user)
        self.url = reverse('geography:api_geojson_villages_non_relies')

    def villages(self, **params):
        d = self.client.get(self.url, params).json()
        return d, {f['properties']['nom']: f['properties'] for f in d['features'] if f['properties']['type'] == 'village'}

    def test_seuls_les_villages_mal_relies_sont_renvoyes(self):
        d, v = self.villages()
        self.assertEqual(set(v), {'Eloigne', 'Isole', 'Les deux'})
        self.assertEqual(v['Eloigne']['motifs'], ['eloigne'])
        self.assertEqual(v['Isole']['motifs'], ['isole'])
        self.assertEqual(v['Les deux']['motifs'], ['isole', 'eloigne'])
        self.assertEqual((d['nb_isoles'], d['nb_eloignes']), (2, 2))

    def test_un_segment_d_acces_pour_les_villages_eloignes(self):
        d, _ = self.villages()
        self.assertEqual(sum(1 for f in d['features'] if f['properties']['type'] == 'acces'), 2)

    def test_le_seuil_est_reglable(self):
        _, v = self.villages(seuil=3000)
        self.assertEqual(set(v), {'Isole', 'Les deux'})       # 'Eloigne' (2 500 m) passe sous le seuil
        self.assertEqual(v['Les deux']['motifs'], ['isole'])
        self.assertEqual(self.client.get(self.url, {'seuil': 'x'}).status_code, 400)


class BasesGeojsonTests(TestCase):
    """GET /geography/api/geojson/bases/"""

    def setUp(self):
        from decimal import Decimal
        from apps.organization.models import Base, Organisation
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        village = Village.objects.create(nom_village='Vohipeno', fokontany=fkt, longitude=Decimal('47.8'), latitude=Decimal('-22.3'))
        org = Organisation.objects.create(nom_organisation='Org')
        Base.objects.create(nom_base='Par GPS', organisation=org, latitude_depart=Decimal('-18.9'), longitude_depart=Decimal('47.5'))
        Base.objects.create(nom_base='Par village', organisation=org, village_depart=village)
        Base.objects.create(nom_base='Sans lieu', organisation=org)
        self.user = get_user_model().objects.create_user(username='b', password='x')
        self.client.force_login(self.user)
        self.url = reverse('geography:api_geojson_bases')

    def test_seules_les_bases_placees_sont_dessinees(self):
        d = self.client.get(self.url).json()
        par_nom = {f['properties']['nom']: f for f in d['features']}
        self.assertEqual(set(par_nom), {'Par GPS', 'Par village'})
        self.assertEqual(par_nom['Par GPS']['geometry']['coordinates'], [47.5, -18.9])
        self.assertEqual(par_nom['Par village']['geometry']['coordinates'], [47.8, -22.3])
        self.assertTrue(par_nom['Par village']['properties']['sur_village'])
        self.assertEqual((d['nb_non_placees'], d['non_placees']), (1, ['Sans lieu']))
