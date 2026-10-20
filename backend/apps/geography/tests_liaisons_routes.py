import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.geography.models import Commune, District, Fokontany, LiaisonVillage, Region, Village
from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute
from apps.geography.services import liaisons_routes
from apps.geography.services.reseau_routier import haversine_m
from apps.geography.services.reseau_routier import longueur_geodesique_m


def noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


def troncon(a, b, coords, categorie='route'):
    return TronconRoute.objects.create(noeud_debut=a, noeud_fin=b, geometrie=coords, categorie=categorie,
                                       longueur_m=longueur_geodesique_m(coords))


class LiaisonsRoutesTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        self.fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        # Route en L : A(47.00,-18.00) -> B(47.02,-18.00) -> C(47.02,-18.02) : le trajet n'est PAS une ligne droite.
        self.a, self.b, self.c = noeud(47.00, -18.00), noeud(47.02, -18.00), noeud(47.02, -18.02)
        self.t_ab = troncon(self.a, self.b, [[47.00, -18.00], [47.02, -18.00]])
        self.t_bc = troncon(self.b, self.c, [[47.02, -18.00], [47.02, -18.02]])
        self.v1 = self.village('V1', 47.00, -18.00, self.t_ab, 0.0)
        self.v2 = self.village('V2', 47.02, -18.02, self.t_bc, 1.0)
        self.v_isole = Village.objects.create(nom_village='Isolé', fokontany=self.fkt,
                                              latitude=Decimal('-17.0'), longitude=Decimal('46.0'))

    def village(self, nom, lon, lat, tr, fraction):
        v = Village.objects.create(nom_village=nom, fokontany=self.fkt,
                                   latitude=Decimal(str(lat)), longitude=Decimal(str(lon)))
        VillageAccesRoute.objects.create(village=v, troncon=tr, fraction=fraction, distance_m=0,
                                         longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))
        return v

    def liaison(self, cible=None, **kw):
        return LiaisonVillage.objects.create(village_source=self.v1, village_cible=cible or self.v2, **kw)

    def test_calcule_la_courbe_et_remplit_les_valeurs_vides(self):
        l = self.liaison()
        stats = liaisons_routes.calculer([l])
        l.refresh_from_db()
        self.assertEqual(stats['ok'], 1)
        self.assertEqual(l.route_statut, 'ok')
        self.assertEqual(len(l.trace_route), 3)           # A -> B -> C : une vraie courbe, pas 2 points
        attendu = (self.t_ab.longueur_m + self.t_bc.longueur_m) / 1000
        self.assertAlmostEqual(l.distance_route_km, attendu, delta=0.02)
        self.assertAlmostEqual(float(l.distance_km), attendu, delta=0.02)   # champ vide -> complété
        self.assertGreater(l.temps_acces_minutes, 0)

    def test_ne_touche_pas_aux_valeurs_saisies_sauf_demande(self):
        l = self.liaison(distance_km=Decimal('9.99'), temps_acces_minutes=777)
        liaisons_routes.calculer([l])
        l.refresh_from_db()
        self.assertEqual(l.distance_km, Decimal('9.99'))
        self.assertEqual(l.temps_acces_minutes, 777)
        self.assertNotEqual(l.distance_route_km, 9.99)
        liaisons_routes.calculer([l], forcer_distances=True)
        l.refresh_from_db()
        self.assertNotEqual(l.distance_km, Decimal('9.99'))
        self.assertNotEqual(l.temps_acces_minutes, 777)

    def test_pirogue_et_riviere_restent_en_ligne_droite(self):
        l1 = self.liaison(moyen_acces='pirogue', type_liaison='desserte')
        l2 = self.liaison(type_route='riviere', type_liaison='proximite')
        stats = liaisons_routes.calculer([l1, l2])
        self.assertEqual(stats['ignore'], 2)
        l1.refresh_from_db()
        self.assertEqual(l1.route_statut, 'ignore')
        self.assertIsNone(l1.trace_route)

    def test_village_sans_acces_au_reseau(self):
        l = self.liaison(cible=self.v_isole)
        stats = liaisons_routes.calculer([l])
        l.refresh_from_db()
        self.assertEqual(stats['introuvable'], 1)
        self.assertEqual(l.route_statut, 'introuvable')

    def test_plusieurs_destinations_depuis_la_meme_source(self):
        v3 = self.village('V3', 47.02, -18.00, self.t_ab, 1.0)
        l1, l2 = self.liaison(), self.liaison(cible=v3, type_liaison='proximite')
        stats = liaisons_routes.calculer([l1, l2])
        self.assertEqual(stats['ok'], 2)
        l1.refresh_from_db(); l2.refresh_from_db()
        self.assertLess(l2.distance_route_km, l1.distance_route_km)

    def test_commande_ne_recalcule_que_le_perime(self):
        l = self.liaison()
        call_command('calculer_liaisons_routieres', verbosity=0)
        l.refresh_from_db()
        premier = l.route_calculee_le
        self.assertIsNotNone(premier)
        call_command('calculer_liaisons_routieres', verbosity=0)     # réseau inchangé -> rien à faire
        l.refresh_from_db()
        self.assertEqual(l.route_calculee_le, premier)
        TronconRoute.objects.get(pk=self.t_ab.pk).save()               # le réseau change -> à recalculer
        call_command('calculer_liaisons_routieres', verbosity=0)
        l.refresh_from_db()
        self.assertGreater(l.route_calculee_le, premier)

    def test_api_et_geojson_servent_la_courbe(self):
        self.client.force_login(get_user_model().objects.create_user('u', password='p'))
        r = self.client.post(reverse('geography:api_liaison_create'), json.dumps({
            'source_id': str(self.v1.id), 'cible_id': str(self.v2.id), 'type_liaison': 'desserte'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual(len(d['trace_route']), 3)
        self.assertEqual(d['liaison']['route_statut'], 'ok')
        from apps.geography.views_liaisons_api import liaison_feature
        l = LiaisonVillage.objects.select_related(
            'village_source__fokontany__commune', 'village_cible__fokontany__commune').get(pk=d['liaison']['id'])
        self.assertEqual(len(liaison_feature(l)['geometry']['coordinates']), 3)


    def test_distance_a_vol_d_oiseau_du_premier_remplissage_est_remplacee(self):
        air = round(haversine_m(float(self.v1.longitude), float(self.v1.latitude),
                                float(self.v2.longitude), float(self.v2.latitude)) / 1000, 2)
        l = self.liaison(distance_km=Decimal(str(air)))           # ce que le remplissage automatique d'origine écrivait
        liaisons_routes.calculer([l])
        l.refresh_from_db()
        self.assertGreater(float(l.distance_km), air)              # remplacée par la distance par la route (plus longue)
        self.assertAlmostEqual(float(l.distance_km), l.distance_route_km, places=2)

    def test_valeurs_calculees_suivent_les_recalculs_mais_pas_les_saisies(self):
        auto = self.liaison()
        manuelle = self.liaison(cible=self.village('V3', 47.01, -18.0, self.t_ab, 0.5), temps_acces_minutes=777,
                                distance_km=Decimal('9.99'))
        liaisons_routes.calculer([auto, manuelle])
        premier = auto.temps_acces_minutes
        # le profil change (moyen d'accès à pied) : le temps calculé suit, la saisie manuelle reste
        for l in (auto, manuelle):
            l.moyen_acces = 'pied'
        liaisons_routes.calculer([auto, manuelle])
        auto.refresh_from_db(); manuelle.refresh_from_db()
        self.assertGreater(auto.temps_acces_minutes, premier)
        self.assertEqual(auto.temps_acces_minutes, auto.duree_route_min)
        self.assertEqual(manuelle.temps_acces_minutes, 777)
        self.assertEqual(manuelle.distance_km, Decimal('9.99'))

    def test_profil_selon_le_moyen_d_acces(self):
        moto = self.liaison(moyen_acces='moto', type_liaison='desserte')
        pied = self.liaison(moyen_acces='pied', type_liaison='proximite')
        sans = self.liaison(type_liaison='dependance')              # moyen non renseigné : moto par défaut
        liaisons_routes.calculer([moto, pied, sans])
        for l in (moto, pied, sans):
            l.refresh_from_db()
        self.assertGreater(pied.duree_route_min, 3 * moto.duree_route_min)
        self.assertEqual(sans.duree_route_min, moto.duree_route_min)
        self.assertAlmostEqual(pied.distance_route_km, moto.distance_route_km, places=2)
