from datetime import datetime
from decimal import Decimal

import pytz
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.billing.models import PointEau, TypePointEau
from apps.employees.models import Employe
from apps.geography.models import Commune, District, Fokontany, Parcelle, Region, Village
from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute
from apps.geography.services.reseau_routier import longueur_geodesique_m
from apps.organization.models import Base, Organisation, Ouvrage, TypeOuvrage
from apps.planning.models import Planning

TZ = pytz.timezone('Indian/Antananarivo')
JOUR = (2026, 10, 12)


def noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


class TourneeRoutiereTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        self.fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        self.type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG')
        self.type_point = TypePointEau.objects.create(nom_type='BF')

        # Route droite de 11 km ; 4 villages posés dessus à 0, 1, 2, 3 « unités » de 0,02°.
        a, b = noeud(47.00, -18.0), noeud(47.10, -18.0)
        coords = [[47.00, -18.0], [47.10, -18.0]]
        self.route = TronconRoute.objects.create(noeud_debut=a, noeud_fin=b, geometrie=coords, categorie='route',
                                                 longueur_m=longueur_geodesique_m(coords))
        self.v = {i: self.village(i) for i in range(4)}
        self.ouvrage = {i: self.ouvrage_dans(i) for i in range(4)}

        organisation = Organisation.objects.create(nom_organisation='Org')
        self.base = Base.objects.create(nom_base='Base', organisation=organisation)
        self.agent = Employe.objects.create(nom_employe='Rakoto', surnom='Rako', base=self.base)

        self.admin = get_user_model().objects.create_superuser('admin', 'a@b.c', 'x')
        self.client.force_login(self.admin)

    def village(self, i):
        lon = 47.00 + 0.02 * i
        v = Village.objects.create(nom_village=f'V{i}', fokontany=self.fkt,
                                   latitude=Decimal('-18.0'), longitude=Decimal(str(lon)))
        VillageAccesRoute.objects.create(village=v, troncon=self.route, fraction=(lon - 47.0) / 0.10, distance_m=0,
                                         longitude=Decimal(str(lon)), latitude=Decimal('-18.0'))
        return v

    def ouvrage_dans(self, i):
        o = Ouvrage.objects.create(nom_ouvrage=f'Ouvrage {i}', type_ouvrage=self.type_ouvrage)
        parcelle = Parcelle.objects.create(reference_parcelle=f'P{i}', village=self.v[i])
        PointEau.objects.create(ouvrage=o, parcelle=parcelle, type_point_eau=self.type_point,
                                nomabonne=f'A{i}', idxls=str(i))
        return o

    def planning(self, ouvrage=None, heure=10, jour=JOUR, **kw):
        return Planning.objects.create(employe=self.agent, ouvrage=ouvrage,
                                       date=TZ.localize(datetime(*jour, heure, 0)), **kw)

    def appel(self, **params):
        base = {'employe': str(self.agent.id), 'date': '2026-10-12', 'depart': str(self.v[0].id)}
        base.update(params)
        return self.client.get(reverse('planning:api_tournee'), base)

    def test_tournee_du_jour_ordonnee(self):
        # ordre du planning en zig-zag : 3, 1, 2
        for h, i in ((8, 3), (10, 1), (14, 2)):
            self.planning(self.ouvrage[i], heure=h)
        d = self.appel(retour='0').json()
        self.assertTrue(d['success'], d)
        self.assertEqual([e['village']['nom'] for e in d['etapes']], ['V1', 'V2', 'V3'])
        self.assertEqual(d['depart']['nom'], 'V0')
        self.assertEqual(len(d['legs']), 3)
        self.assertEqual(d['legs'][0]['geometrie']['type'], 'LineString')
        self.assertGreater(d['gain_duree_min'], 0)
        self.assertLess(d['distance_km'], d['reference']['distance_km'])
        self.assertEqual(d['nb_plannings'], 3)

    def test_autres_jours_exclus_et_plannings_du_meme_lieu_regroupes(self):
        self.planning(self.ouvrage[1], heure=8)
        self.planning(self.ouvrage[1], heure=14)
        self.planning(self.ouvrage[2], jour=(2026, 10, 13))             # lendemain : exclu
        d = self.appel().json()
        self.assertEqual(len(d['etapes']), 1)
        self.assertEqual(len(d['etapes'][0]['plannings']), 2)

    def test_point_eau_cible_prime_sur_l_ouvrage(self):
        point_v3 = self.ouvrage[3].pointeau_set.first()
        self.planning(self.ouvrage[1], cible_point_eau=point_v3)
        d = self.appel().json()
        self.assertEqual([e['village']['nom'] for e in d['etapes']], ['V3'])

    def test_planning_sans_lieu_signale(self):
        self.planning(None)
        self.planning(self.ouvrage[2])
        d = self.appel().json()
        self.assertEqual(len(d['sans_lieu']), 1)
        self.assertEqual(len(d['etapes']), 1)

    def test_jour_sans_planning(self):
        d = self.appel().json()
        self.assertTrue(d['success'])
        self.assertEqual(d['etapes'], [])
        self.assertEqual(d['nb_plannings'], 0)

    def test_depart_automatique_premier_arret(self):
        self.planning(self.ouvrage[2], heure=8)
        self.planning(self.ouvrage[1], heure=10)
        d = self.client.get(reverse('planning:api_tournee'), {'employe': str(self.agent.id), 'date': '2026-10-12'}).json()
        self.assertEqual(d['depart']['origine'], 'premier arrêt')
        self.assertEqual(d['depart']['nom'], 'V2')

    def test_activites_du_village_de_depart_restent_visibles(self):
        self.planning(self.ouvrage[0], heure=8)          # au départ lui-même
        self.planning(self.ouvrage[2], heure=10)
        d = self.appel().json()
        self.assertEqual([e['village']['nom'] for e in d['etapes']], ['V2'])
        self.assertEqual(len(d['depart']['plannings']), 1)

    def test_droits(self):
        url = reverse('planning:api_tournee')
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(get_user_model().objects.create_user('simple', password='x'))
        self.assertEqual(self.client.get(url, {'employe': str(self.agent.id)}).status_code, 403)

    def test_page(self):
        r = self.client.get(reverse('planning:tournee_routiere'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Tournée de l'agent")
        self.assertContains(r, 'Rako')

    def test_prix_deplacement_expose_distance_et_duree_par_la_route(self):
        r = self.client.get(reverse('planning:api_prix_deplacement'),
                            {'point_a_id': str(self.v[0].id), 'point_b_id': str(self.v[3].id)})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIsNone(d['prix_unitaire'])
        self.assertAlmostEqual(d['distance_route_km'], 0.6 * self.route.longueur_m / 1000, delta=0.05)
        self.assertGreater(d['duree_route_min'], 0)

    def test_prix_deplacement_taxi_utilise_le_profil_voiture_et_pirogue_aucun_calcul(self):
        url = reverse('planning:api_prix_deplacement')
        taxi = self.client.get(url, {'point_a_id': str(self.v[0].id), 'point_b_id': str(self.v[3].id)}).json()
        pirogue = self.client.get(url, {'point_a_id': str(self.v[0].id), 'point_b_id': str(self.v[3].id),
                                        'moyen_transport': 'pirogue'}).json()
        self.assertEqual(taxi['profil_route'], 'voiture')
        self.assertGreater(taxi['duree_route_min'], 0)
        self.assertIsNone(pirogue['duree_route_min'])
        self.assertIsNone(pirogue['distance_route_km'])

    def test_trajet_suggere_arrivee_et_depart_de_la_base(self):
        self.base.village_depart = self.v[0]
        self.base.save()
        d = self.client.get(reverse('planning:api_trajet_suggere'),
                            {'ouvrage_id': str(self.ouvrage[2].id), 'employe_id': str(self.agent.id)}).json()
        self.assertTrue(d['success'])
        self.assertEqual(d['arrivee']['nom'], 'V2')
        self.assertEqual(d['depart_base']['village']['nom'], 'V0')
        self.assertTrue(d['depart_base']['localisee'])

    def test_trajet_suggere_base_non_localisee_ou_ouvrage_inconnu(self):
        d = self.client.get(reverse('planning:api_trajet_suggere'),
                            {'ouvrage_id': str(self.ouvrage[1].id), 'employe_id': str(self.agent.id)}).json()
        self.assertEqual(d['arrivee']['nom'], 'V1')
        self.assertFalse(d['depart_base']['localisee'])
        self.assertIsNone(d['depart_base']['village'])
        vide = self.client.get(reverse('planning:api_trajet_suggere')).json()
        self.assertIsNone(vide['arrivee'])
        self.assertIsNone(vide['depart_base'])

    def test_trajet_suggere_droits_et_identifiants_invalides(self):
        url = reverse('planning:api_trajet_suggere')
        self.assertEqual(self.client.get(url, {'ouvrage_id': 'pas-un-uuid'}).status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 401)



class AgentsDuJourTests(TourneeRoutiereTests):
    """GET /plannings/api/agents-du-jour/?date=… : agents ayant des plannings ce jour-là."""

    def appel_liste(self, date='2026-10-12'):
        return self.client.get(reverse('planning:api_agents_du_jour'), {'date': date}).json()

    def test_liste_les_agents_avec_leurs_plannings_et_villages(self):
        autre = Employe.objects.create(nom_employe='Rabe', surnom='Rabe', base=self.base)
        self.planning(self.ouvrage[1], heure=8)
        self.planning(self.ouvrage[1], heure=14)
        self.planning(self.ouvrage[2], heure=16)
        self.planning(None, heure=17)                                   # sans lieu : compté en plannings, pas en villages
        Planning.objects.create(employe=autre, ouvrage=self.ouvrage[3], date=TZ.localize(datetime(*JOUR, 9, 0)))
        d = self.appel_liste()
        self.assertTrue(d['success'])
        par_nom = {a['nom']: a for a in d['agents']}
        self.assertEqual((par_nom['Rako']['nb_plannings'], par_nom['Rako']['nb_villages']), (4, 2))
        self.assertEqual((par_nom['Rabe']['nb_plannings'], par_nom['Rabe']['nb_villages']), (1, 1))
        self.assertEqual([a['nom'] for a in d['agents']], ['Rabe', 'Rako'])     # tri alphabétique

    def test_autre_jour_et_authentification(self):
        self.planning(self.ouvrage[1], jour=(2026, 10, 13))
        self.assertEqual(self.appel_liste()['agents'], [])
        self.client.logout()
        self.assertEqual(self.client.get(reverse('planning:api_agents_du_jour')).status_code, 401)


class PositionsGpsTests(TestCase):
    """GET /plannings/api/positions-gps/?date=…&precision_max=… : positions GPS réelles des agents."""

    def setUp(self):
        from apps.employees.models import PositionGPSEmploye
        org = Organisation.objects.create(nom_organisation='Org')
        base = Base.objects.create(nom_base='Base', organisation=org)
        self.rako = Employe.objects.create(nom_employe='Rakoto', surnom='Rako', base=base)
        self.rabe = Employe.objects.create(nom_employe='Rabe', surnom='Rabe', base=base)
        self.admin = get_user_model().objects.create_superuser('admin', 'a@b.c', 'x')
        self.client.force_login(self.admin)
        self.url = reverse('planning:api_positions_gps')

        def pos(employe, heure, precision, jour=(2026, 10, 12), lon='47.5'):
            p = PositionGPSEmploye.objects.create(employe=employe, latitude=Decimal('-18.9'), longitude=Decimal(lon), precision=Decimal(precision))
            # date_enregistrement est en auto_now_add : on la fixe après création
            PositionGPSEmploye.objects.filter(pk=p.pk).update(date_enregistrement=TZ.localize(datetime(*jour, heure, 30)))
        pos(self.rako, 8, '20')
        pos(self.rako, 11, '300', lon='47.51')
        pos(self.rako, 14, '4000')                              # imprécise : écartée par défaut
        pos(self.rabe, 9, '50')
        pos(self.rabe, 9, '50', jour=(2026, 10, 13))            # autre jour

    def appel(self, **p):
        return self.client.get(self.url, {'date': '2026-10-12', **p}).json()

    def test_positions_du_jour_triees_et_filtrees_par_precision(self):
        d = self.appel()
        par_nom = {a['nom']: a for a in d['agents']}
        self.assertEqual((par_nom['Rako']['nb'], par_nom['Rako']['nb_total']), (2, 3))
        self.assertEqual([p[2] for p in par_nom['Rako']['points']], ['08:30', '11:30'])      # heure de Madagascar
        self.assertEqual(par_nom['Rako']['points'][0][:2], [47.5, -18.9])
        self.assertEqual((par_nom['Rabe']['nb'], par_nom['Rabe']['nb_total']), (1, 1))

    def test_precision_max_et_toutes(self):
        self.assertEqual({a['nom']: a['nb'] for a in self.appel(precision_max=100)['agents']}, {'Rako': 1, 'Rabe': 1})
        self.assertEqual({a['nom']: a['nb'] for a in self.appel(precision_max=0)['agents']}, {'Rako': 3, 'Rabe': 1})
        self.assertEqual(self.client.get(self.url, {'precision_max': 'x'}).status_code, 400)

    def test_authentification_et_perimetre(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        simple = get_user_model().objects.create_user('simple', password='x')
        self.client.force_login(simple)
        self.assertEqual(self.client.get(self.url, {'date': '2026-10-12'}).json()['agents'], [])    # aucun périmètre
