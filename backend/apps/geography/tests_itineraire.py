from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.geography.models import Commune, District, Fokontany, Region, Village
from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute
from apps.geography.services import itineraire as it
from apps.geography.services.voies_config import PROFILS
from apps.geography.services.reseau_routier import longueur_geodesique_m


def noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


def troncon(a, b, coords, categorie='route', **kw):
    return TronconRoute.objects.create(noeud_debut=a, noeud_fin=b, geometrie=coords, categorie=categorie,
                                       longueur_m=longueur_geodesique_m(coords), **kw)


class ItineraireTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        self.fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        # A --(route 40 km/h)-- B --(sentier 5 km/h)-- C, alignés sur l'équateur-ish (~2,2 km chacun).
        self.a, self.b, self.c = noeud(47.00, -18.0), noeud(47.02, -18.0), noeud(47.04, -18.0)
        self.t_ab = troncon(self.a, self.b, [[47.00, -18.0], [47.02, -18.0]], 'route')
        self.t_bc = troncon(self.b, self.c, [[47.02, -18.0], [47.04, -18.0]], 'sentier')

    def village(self, nom, lon, troncon_, fraction, distance=0):
        v = Village.objects.create(nom_village=nom, fokontany=self.fkt,
                                   latitude=Decimal('-18.0'), longitude=Decimal(str(lon)))
        VillageAccesRoute.objects.create(village=v, troncon=troncon_, fraction=fraction, distance_m=distance,
                                         longitude=Decimal(str(lon)), latitude=Decimal('-18.0'))
        return v

    def test_distance_et_duree_sur_deux_tronçons(self):
        va = self.village('A', 47.00, self.t_ab, 0.0)
        vc = self.village('C', 47.04, self.t_bc, 1.0)
        r = it.itineraire_villages(va.id, vc.id)
        attendu = self.t_ab.longueur_m + self.t_bc.longueur_m
        self.assertAlmostEqual(r['distance_m'], attendu, delta=1)
        # vitesses du profil par défaut (moto) : route puis sentier
        moto = PROFILS['moto']
        secondes = self.t_ab.longueur_m / (moto['route'] / 3.6) + self.t_bc.longueur_m / (moto['sentier'] / 3.6)
        self.assertAlmostEqual(r['duree_s'], secondes, delta=2)
        self.assertEqual(r['geometrie'][0], [47.00, -18.0])
        self.assertEqual(r['geometrie'][-1], [47.04, -18.0])

    def test_deux_villages_sur_le_meme_troncon(self):
        v1 = self.village('1', 47.005, self.t_ab, 0.25)
        v2 = self.village('2', 47.015, self.t_ab, 0.75)
        r = it.itineraire_villages(v1.id, v2.id)
        self.assertAlmostEqual(r['distance_m'], 0.5 * self.t_ab.longueur_m, delta=1)

    def test_marche_jusqu_a_la_route(self):
        v1 = self.village('1', 47.0, self.t_ab, 0.0, distance=400)
        v2 = self.village('2', 47.02, self.t_ab, 1.0, distance=600)
        r = it.itineraire_villages(v1.id, v2.id)
        self.assertEqual(r['marche_m'], 1000)
        self.assertAlmostEqual(r['distance_m'], self.t_ab.longueur_m + 1000, delta=1)
        self.assertIn('marche', r['repartition_m'])

    def test_troncon_non_praticable_coupe_le_chemin(self):
        va = self.village('A', 47.00, self.t_ab, 0.0)
        vc = self.village('C', 47.04, self.t_bc, 1.0)
        TronconRoute.objects.filter(pk=self.t_bc.pk).update(praticable=False)
        TronconRoute.objects.filter(pk=self.t_bc.pk).first().save()  # met à jour updated_at -> invalide le cache
        with self.assertRaises(it.ItineraireIntrouvable):
            it.itineraire_villages(va.id, vc.id)

    def test_api(self):
        va = self.village('A', 47.00, self.t_ab, 0.0)
        vc = self.village('C', 47.04, self.t_bc, 1.0)
        url = reverse('geography:api_itineraire')
        self.assertEqual(self.client.get(url, {'depart': va.id, 'arrivee': vc.id}).status_code, 401)
        self.client.force_login(get_user_model().objects.create_user('u', password='x'))
        r = self.client.get(url, {'depart': va.id, 'arrivee': vc.id})
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual(d['geometrie']['type'], 'LineString')
        self.assertGreater(d['duree_minutes'], 0)
        self.assertEqual(self.client.get(url, {'depart': 'nimporte', 'arrivee': vc.id}).status_code, 400)
        self.assertEqual(self.client.get(url, {'depart': va.id}).status_code, 400)


    def test_profils_de_deplacement(self):
        va = self.village('A', 47.00, self.t_ab, 0.0)
        vc = self.village('C', 47.04, self.t_bc, 1.0)
        moto = it.itineraire_villages(va.id, vc.id, profil='moto')
        voiture = it.itineraire_villages(va.id, vc.id, profil='voiture')
        pied = it.itineraire_villages(va.id, vc.id, profil='pied')
        # même parcours, donc même distance ; seule la durée change
        self.assertAlmostEqual(moto['distance_m'], pied['distance_m'], delta=1)
        self.assertEqual(moto['profil'], 'moto')
        attendu_pied = (self.t_ab.longueur_m / (PROFILS['pied']['route'] / 3.6)
                        + self.t_bc.longueur_m / (PROFILS['pied']['sentier'] / 3.6))
        self.assertAlmostEqual(pied['duree_s'], attendu_pied, delta=2)
        self.assertGreater(pied['duree_s'], 2 * moto['duree_s'])          # la marche est bien plus lente (moitié du trajet en sentier)
        self.assertLess(voiture['duree_s'], pied['duree_s'])
        with self.assertRaises(ValueError):
            it.itineraire_villages(va.id, vc.id, profil='fusee')

    def test_surcharge_manuelle_de_vitesse_ne_vaut_que_pour_les_engins_motorises(self):
        TronconRoute.objects.filter(pk=self.t_ab.pk).update(vitesse_kmh=90)
        va = self.village('A', 47.00, self.t_ab, 0.0)
        vb = self.village('B', 47.02, self.t_ab, 1.0)
        moto = it.itineraire_villages(va.id, vb.id, profil='moto')
        pied = it.itineraire_villages(va.id, vb.id, profil='pied')
        self.assertAlmostEqual(moto['duree_s'], self.t_ab.longueur_m / (90 / 3.6), delta=2)
        self.assertAlmostEqual(pied['duree_s'], self.t_ab.longueur_m / (PROFILS['pied']['route'] / 3.6), delta=2)

    def test_api_profil(self):
        va = self.village('A', 47.00, self.t_ab, 0.0)
        vc = self.village('C', 47.04, self.t_bc, 1.0)
        self.client.force_login(get_user_model().objects.create_user('u2', password='x'))
        url = reverse('geography:api_itineraire')
        moto = self.client.get(url, {'depart': va.id, 'arrivee': vc.id}).json()
        pied = self.client.get(url, {'depart': va.id, 'arrivee': vc.id, 'profil': 'pied'}).json()
        self.assertEqual((moto['profil'], pied['profil']), ('moto', 'pied'))
        self.assertGreater(pied['duree_minutes'], moto['duree_minutes'])
        self.assertEqual(self.client.get(url, {'depart': va.id, 'arrivee': vc.id, 'profil': 'fusee'}).status_code, 400)
