import itertools
import random
from decimal import Decimal

from django.test import TestCase

from apps.geography.models import Commune, District, Fokontany, Region, Village
from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute
from apps.geography.services import tournees
from apps.geography.services.reseau_routier import longueur_geodesique_m


def noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


class OrdreOptimalTests(TestCase):
    """Partie algorithmique pure (sans base de données)."""

    def matrice_aleatoire(self, n, graine):
        rnd = random.Random(graine)
        pts = [(rnd.random(), rnd.random()) for _ in range(n + 1)]
        return lambda a, b: ((pts[a][0] - pts[b][0]) ** 2 + (pts[a][1] - pts[b][1]) ** 2) ** 0.5

    def test_held_karp_egale_la_recherche_exhaustive(self):
        for n, retour in ((5, True), (6, False), (7, True)):
            cout = self.matrice_aleatoire(n, n)
            etapes = list(range(1, n + 1))
            exact = tournees.ordre_optimal(0, etapes, cout, retour)
            brute = min(itertools.permutations(etapes), key=lambda p: tournees._longueur(0, p, cout, retour))
            self.assertAlmostEqual(tournees._longueur(0, exact, cout, retour),
                                   tournees._longueur(0, brute, cout, retour), places=9)

    def test_heuristique_pour_les_longues_tournees(self):
        n = tournees.MAX_EXACT + 4
        cout = self.matrice_aleatoire(n, 42)
        etapes = list(range(1, n + 1))
        ordre = tournees.ordre_optimal(0, etapes, cout, True)
        self.assertEqual(sorted(ordre), etapes)                      # toutes les étapes, une seule fois
        aleatoire = tournees._longueur(0, etapes, cout, True)
        self.assertLess(tournees._longueur(0, ordre, cout, True), aleatoire)

    def test_cas_limites(self):
        self.assertEqual(tournees.ordre_optimal(0, [], lambda a, b: 1), [])
        self.assertEqual(tournees.ordre_optimal(0, [7], lambda a, b: 1), [7])


class TourneeReseauTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        self.fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        # Une route droite de ~11 km ; les villages sont posés dessus à 0, 1, 2, 3, 4 « unités » (1 unité = 0,02°).
        a, b = noeud(47.00, -18.0), noeud(47.10, -18.0)
        coords = [[47.00, -18.0], [47.10, -18.0]]
        self.route = TronconRoute.objects.create(noeud_debut=a, noeud_fin=b, geometrie=coords, categorie='route',
                                                 longueur_m=longueur_geodesique_m(coords))
        self.v = {i: self.village(f'V{i}', i) for i in range(5)}
        # un tronçon isolé, hors du réseau principal
        c, d = noeud(46.0, -17.0), noeud(46.01, -17.0)
        iso = TronconRoute.objects.create(noeud_debut=c, noeud_fin=d, geometrie=[[46.0, -17.0], [46.01, -17.0]],
                                          longueur_m=1000)
        w = Village.objects.create(nom_village='Isolé', fokontany=self.fkt,
                                   latitude=Decimal('-17.0'), longitude=Decimal('46.0'))
        VillageAccesRoute.objects.create(village=w, troncon=iso, fraction=0.0, distance_m=0,
                                         longitude=Decimal('46.0'), latitude=Decimal('-17.0'), reseau_principal=False)
        self.isole = w

    def village(self, nom, i):
        lon = 47.00 + 0.02 * i
        v = Village.objects.create(nom_village=nom, fokontany=self.fkt,
                                   latitude=Decimal('-18.0'), longitude=Decimal(str(lon)))
        VillageAccesRoute.objects.create(village=v, troncon=self.route, fraction=(lon - 47.0) / 0.10, distance_m=0,
                                         longitude=Decimal(str(lon)), latitude=Decimal('-18.0'))
        return v

    def ids(self, *positions):
        return [self.v[i].id for i in positions]

    def test_ordre_optimal_et_gain_par_rapport_a_l_ordre_du_planning(self):
        # ordre « naturel » du planning : 3, 1, 4, 2 (allers-retours inutiles)
        r = tournees.calculer(self.v[0].id, self.ids(3, 1, 4, 2), retour=True)
        self.assertEqual(set(r['ordre']), set(self.ids(1, 2, 3, 4)))
        # Plusieurs ordres ont le même coût optimal (aller jusqu'au bout puis revenir) : on vérifie le coût.
        self.assertAlmostEqual(r['distance_m'], 2 * 0.8 * self.route.longueur_m, delta=1)
        self.assertGreater(r['gain_distance_m'], 0)
        self.assertGreater(r['gain_duree_s'], 0)
        self.assertEqual(len(r['legs']), 5)                       # 4 étapes + retour au départ
        self.assertEqual(r['legs'][-1]['vers'], self.v[0].id)
        self.assertGreater(len(r['legs'][0]['geometrie']), 1)

    def test_sans_retour(self):
        r = tournees.calculer(self.v[0].id, self.ids(3, 1, 2), retour=False)
        self.assertEqual(r['ordre'], self.ids(1, 2, 3))
        self.assertEqual(len(r['legs']), 3)

    def test_depart_au_milieu(self):
        r = tournees.calculer(self.v[2].id, self.ids(0, 4, 3, 1), retour=True)
        self.assertEqual(set(r['ordre']), set(self.ids(0, 1, 3, 4)))
        # Coût optimal : couvrir tout le segment [V0, V4] une fois aller, une fois retour, sans zigzag inutile.
        self.assertAlmostEqual(r['distance_m'], 2 * 0.8 * self.route.longueur_m, delta=1)

    def test_etape_inaccessible_signalee_et_exclue(self):
        r = tournees.calculer(self.v[0].id, self.ids(2, 1) + [self.isole.id])
        self.assertEqual(r['inaccessibles'], [self.isole.id])
        self.assertEqual(set(r['ordre']), set(self.ids(1, 2)))

    def test_depart_non_rattache_et_doublons(self):
        sans_gps = Village.objects.create(nom_village='SansGPS', fokontany=self.fkt)
        with self.assertRaises(tournees.TourneeInvalide):
            tournees.calculer(sans_gps.id, self.ids(1))
        r = tournees.calculer(self.v[0].id, self.ids(1, 1, 0, 2))      # doublon et départ ignorés
        self.assertEqual(sorted(r['ordre']), sorted(self.ids(1, 2)))

    def test_critere_et_limites(self):
        with self.assertRaises(tournees.TourneeInvalide):
            tournees.calculer(self.v[0].id, self.ids(1), critere='peu importe')
        r = tournees.calculer(self.v[0].id, self.ids(2, 1), critere='distance')
        self.assertEqual(r['critere'], 'distance')
