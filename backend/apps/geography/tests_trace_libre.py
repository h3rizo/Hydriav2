import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.geography.models import Commune, District, Fokontany, Region, Village
from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute
from apps.geography.services import itineraire as it
from apps.geography.services import trace_libre as svc
from apps.geography.services.reseau_routier import longueur_geodesique_m


def noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


class TraceLibreTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        self.fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        # Route principale horizontale de 4,4 km (A--B).
        self.a, self.b = noeud(47.00, -18.0), noeud(47.04, -18.0)
        coords = [[47.00, -18.0], [47.04, -18.0]]
        self.route = TronconRoute.objects.create(noeud_debut=self.a, noeud_fin=self.b, geometrie=coords,
                                                 longueur_m=longueur_geodesique_m(coords))
        # Deux villages ~1,1 km au nord de la route, à 110 m l'un de l'autre.
        self.v = self.village('Loin', 47.020, -17.990)
        self.w = self.village('Voisin', 47.021, -17.990)

    def village(self, nom, lon, lat):
        v = Village.objects.create(nom_village=nom, fokontany=self.fkt,
                                   latitude=Decimal(str(lat)), longitude=Decimal(str(lon)))
        VillageAccesRoute.objects.create(village=v, troncon=self.route, fraction=(lon - 47.0) / 0.04,
                                         distance_m=1100, longitude=Decimal(str(lon)), latitude=Decimal('-18.0'))
        return v

    def admin(self):
        self.client.force_login(get_user_model().objects.create_user('admin', password='x', is_staff=True))

    def test_liste_des_villages_isoles(self):
        d = svc.villages_a_tracer(1000)
        self.assertEqual(d['total'], 2)
        self.assertEqual({v['nom'] for v in d['villages']}, {'Loin', 'Voisin'})
        self.assertEqual(svc.villages_a_tracer(5000)['total'], 0)
        self.assertEqual(svc.villages_a_tracer(1000, 'loi')['total'], 1)

    def test_trace_relie_le_village_decoupe_la_route_et_rattache_le_voisin(self):
        r = svc.tracer(self.v.id, [(47.0205, -17.995)], 47.02, -18.0)
        t = r['troncon']
        self.assertEqual(t.source, 'manuel')
        self.assertTrue(r['reseau_principal'])
        self.assertEqual(len(t.geometrie), 3)                       # village, point intermédiaire, arrivée
        self.assertEqual(TronconRoute.objects.count(), 3)           # route coupée en 2 + tracé
        acces = VillageAccesRoute.objects.get(village=self.v)
        self.assertEqual(acces.troncon_id, t.id)
        self.assertEqual(acces.distance_m, 0)
        self.assertEqual(r['voisins_rattaches'], 1)
        voisin = VillageAccesRoute.objects.get(village=self.w)
        self.assertEqual(voisin.troncon_id, t.id)
        self.assertLess(voisin.distance_m, 300)
        # le village relié est maintenant joignable par itinéraire
        self.assertEqual(svc.villages_a_tracer(1000)['total'], 0)
        res = it.itineraire_villages(self.v.id, self.w.id)
        self.assertLess(res['distance_m'], 1000)

    def test_refuse_une_arrivee_trop_loin_du_reseau(self):
        with self.assertRaises(svc.TraceInvalide):
            svc.tracer(self.v.id, [], 47.02, -17.95)
        self.assertEqual(TronconRoute.objects.count(), 1)

    def test_refuse_categorie_et_village_invalides(self):
        with self.assertRaises(svc.TraceInvalide):
            svc.tracer(self.v.id, [], 47.02, -18.0, categorie='autoroute')
        with self.assertRaises(svc.TraceInvalide):
            svc.tracer('00000000-0000-0000-0000-000000000000', [], 47.02, -18.0)

    def test_api_droits_et_creation(self):
        url_liste = reverse('geography:api_trace_libre_liste')
        self.assertEqual(self.client.get(url_liste).status_code, 401)
        self.client.force_login(get_user_model().objects.create_user('simple', password='x'))
        self.assertEqual(self.client.get(url_liste).status_code, 403)
        self.admin()
        d = self.client.get(url_liste, {'seuil_m': 1000}).json()
        self.assertEqual(d['total'], 2)
        ctx = self.client.get(reverse('geography:api_trace_libre_contexte'), {'lon': 47.02, 'lat': -17.99}).json()
        self.assertEqual(len(ctx['troncons']['features']), 1)
        self.assertEqual(len(ctx['villages']), 2)
        r = self.client.post(reverse('geography:api_trace_libre_creer'), data=json.dumps({
            'village_id': str(self.v.id), 'waypoints': [], 'fin': [47.02, -18.0], 'categorie': 'piste'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(TronconRoute.objects.get(source='manuel').categorie, 'piste')
        mauvais = self.client.post(reverse('geography:api_trace_libre_creer'), data=json.dumps({
            'village_id': str(self.w.id), 'fin': [47.02, -17.9]}), content_type='application/json')
        self.assertEqual(mauvais.status_code, 400)
        self.assertEqual(self.client.post(reverse('geography:api_trace_libre_creer'), data='pas du json',
                                          content_type='application/json').status_code, 400)

    def test_page(self):
        url = reverse('geography:trace_libre')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.admin()
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Tracé libre')


class TraceLigneLibreTests(TestCase):
    """Route dessinée librement clic par clic : jonctions automatiques avec le réseau existant."""

    def setUp(self):
        # Route principale horizontale A--B (4,4 km) à -18,0 et route parallèle C--D plus au nord (-17,98).
        self.a, self.b = noeud(47.00, -18.0), noeud(47.04, -18.0)
        self.c, self.d = noeud(47.00, -17.98), noeud(47.04, -17.98)
        for n1, n2, coords in ((self.a, self.b, [[47.00, -18.0], [47.04, -18.0]]), (self.c, self.d, [[47.00, -17.98], [47.04, -17.98]])):
            TronconRoute.objects.create(noeud_debut=n1, noeud_fin=n2, geometrie=coords, longueur_m=longueur_geodesique_m(coords))
        self.url = reverse('geography:api_trace_libre_ligne')

    def test_impasse_libre_sans_jonction(self):
        r = svc.tracer_ligne([[47.01, -17.99], [47.012, -17.991], [47.015, -17.992]], 'piste', 'Piste test')
        self.assertEqual(len(r['troncons']), 1)
        self.assertEqual(r['jonctions'], 0)
        self.assertFalse(r['relie_reseau_principal'])
        t = r['troncons'][0]
        self.assertEqual((t.source, t.categorie, t.nom), ('manuel', 'piste', 'Piste test'))
        self.assertEqual(len(t.geometrie), 3)
        self.assertEqual(TronconRoute.objects.count(), 3)

    def test_jonction_au_depart_decoupe_la_route(self):
        # départ posé sur la route A--B (à 47.02), arrivée libre au nord
        r = svc.tracer_ligne([[47.02, -18.0], [47.02, -17.995], [47.021, -17.99]], 'route')
        self.assertEqual((r['jonctions'], r['relie_reseau_principal']), (1, True))
        self.assertEqual(TronconRoute.objects.count(), 4)           # A--B coupée en 2 + tracé + C--D
        self.assertEqual(len(r['troncons']), 1)

    def test_deux_jonctions_relient_les_deux_routes(self):
        r = svc.tracer_ligne([[47.02, -18.0], [47.025, -17.99], [47.02, -17.98]], 'communale')
        self.assertEqual(r['jonctions'], 2)
        self.assertEqual(TronconRoute.objects.count(), 5)           # chaque route coupée en 2 + le tracé
        # le réseau est maintenant connexe : on peut aller de A à D
        from apps.geography.services.coupures import _graphe
        self.assertEqual(len(_graphe()), 1)

    def test_jonction_au_milieu_coupe_le_trace_en_deux_troncons(self):
        # le tracé passe par la route C--D en son milieu : 2 tronçons créés, joints à la jonction
        r = svc.tracer_ligne([[47.02, -18.0], [47.02, -17.99], [47.02, -17.98], [47.02, -17.97]], 'piste')
        self.assertEqual(r['jonctions'], 2)
        self.assertEqual(len(r['troncons']), 2)                     # A--B -> jonction sur C--D, puis jonction -> bout libre

    def test_plusieurs_jonctions_sur_la_meme_route(self):
        r = svc.tracer_ligne([[47.01, -17.98], [47.015, -17.97], [47.03, -17.97], [47.03, -17.98]], 'piste')
        self.assertEqual(r['jonctions'], 2)
        self.assertEqual(TronconRoute.objects.filter(source='manuel').count(), 1)
        # C--D est coupée en 3 morceaux (A... jonctions à 47.01 et 47.03)
        self.assertEqual(TronconRoute.objects.exclude(source='manuel').count(), 4)       # A--B + 3 morceaux de C--D

    def test_jonction_sur_un_noeud_existant_ne_coupe_pas(self):
        r = svc.tracer_ligne([[47.04, -18.0], [47.045, -17.99], [47.05, -17.98]], 'sentier')
        self.assertEqual(r['jonctions'], 1)
        self.assertEqual(TronconRoute.objects.exclude(source='manuel').count(), 2)       # aucune coupe
        self.assertEqual(r['troncons'][0].noeud_debut_id, self.b.id)

    def test_refus(self):
        for points, categorie in (([[47.0, -17.9]], 'piste'), ([[47.0, -17.9], [47.0, -17.9]], 'piste'),
                                  ([[47.0, -17.9], [47.001, -17.9]], 'autoroute'), ([[2.3, 48.8], [2.31, 48.8]], 'piste'),
                                  ([[47.0, -17.9], ['x', 1]], 'piste')):
            with self.assertRaises(svc.TraceInvalide):
                svc.tracer_ligne(points, categorie)
        self.assertEqual(TronconRoute.objects.count(), 2)

    def test_village_voisin_rattache_au_nouveau_trace(self):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        v = Village.objects.create(nom_village='Loin', fokontany=fkt, latitude=Decimal('-17.9905'), longitude=Decimal('47.0105'))
        route = TronconRoute.objects.first()
        VillageAccesRoute.objects.create(village=v, troncon=route, fraction=0.25, distance_m=1000, longitude=Decimal('47.0105'),
                                         latitude=Decimal('-17.98'))
        r = svc.tracer_ligne([[47.01, -17.99], [47.011, -17.991]], 'sentier')
        self.assertEqual(r['voisins_rattaches'], 1)
        self.assertEqual(VillageAccesRoute.objects.get(village=v).troncon_id, r['troncons'][0].id)

    def test_api(self):
        reponse = self.client.post(self.url, json.dumps({'points': [[47.02, -18.0], [47.02, -17.99]], 'categorie': 'piste'}), content_type='application/json')
        self.assertEqual(reponse.status_code, 401)                           # non connecté
        self.client.force_login(get_user_model().objects.create_user('simple', password='x'))
        self.assertEqual(self.client.post(self.url, '{}', content_type='application/json').status_code, 403)   # pas staff
        self.client.force_login(get_user_model().objects.create_user('admin2', password='x', is_staff=True))
        ok = self.client.post(self.url, json.dumps({'points': [[47.02, -18.0], [47.02, -17.99]], 'categorie': 'piste', 'nom': 'Ma piste'}),
                              content_type='application/json')
        self.assertEqual(ok.status_code, 200)
        d = ok.json()
        self.assertTrue(d['success'])
        self.assertEqual((d['jonctions'], d['relie_reseau_principal'], d['nb_troncons']), (1, True, 1))
        self.assertEqual(TronconRoute.objects.get(nom='Ma piste').source, 'manuel')
        self.assertEqual(self.client.post(self.url, json.dumps({'points': [[47.0, -17.9]]}), content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(self.url, 'pas du json', content_type='application/json').status_code, 400)


class VillageSurLaCarteTests(TestCase):
    """Création d'un village en cliquant sur la carte : détection de la hiérarchie, cascade, création, doublons."""

    def setUp(self):
        from apps.geography.models_contours import ContourAdmin
        self.region = Region.objects.create(nom_region='Analanjirofo')
        self.district = District.objects.create(nom_district='Fénérive Est', region=self.region)
        self.commune = Commune.objects.create(nom_commune='Vohilengo', district=self.district)
        self.fokontany = Fokontany.objects.create(nom_fokontany='Ambodiampaly', commune=self.commune)
        self.autre_fkt = Fokontany.objects.create(nom_fokontany='Autre', commune=self.commune)
        carre = {'type': 'Polygon', 'coordinates': [[[47.0, -18.0], [47.1, -18.0], [47.1, -17.9], [47.0, -17.9], [47.0, -18.0]]]}
        base = dict(geometrie=carre, geometrie_simple=carre, ouest=47.0, sud=-18.0, est=47.1, nord=-17.9,
                    region_nom='Analanjirofo', district_nom='Fénérive Est')
        ContourAdmin.objects.create(niveau='region', cle='R', nom='Analanjirofo', objet_id=self.region.id, **base)
        ContourAdmin.objects.create(niveau='district', cle='D', nom='Fénérive Est', **base)            # pas de lien : retrouvé par le nom
        ContourAdmin.objects.create(niveau='commune', cle='C', nom='Vohilengo', objet_id=self.commune.id, **base)
        ContourAdmin.objects.create(niveau='fokontany', cle='F', nom='Ambodiampaly', commune_nom='Vohilengo', **base)
        # une route pour le rattachement
        a, b = noeud(47.0, -17.95), noeud(47.1, -17.95)
        self.route = TronconRoute.objects.create(noeud_debut=a, noeud_fin=b, geometrie=[[47.0, -17.95], [47.1, -17.95]],
                                                 longueur_m=longueur_geodesique_m([[47.0, -17.95], [47.1, -17.95]]))
        self.client.force_login(get_user_model().objects.create_user('staff', password='x', is_staff=True))

    def appeler(self, nom, **donnees):
        corps = {'nom': nom, 'fokontany_id': str(self.fokontany.id), 'lon': 47.05, 'lat': -17.949, **donnees}
        return self.client.post(reverse('geography:api_village_creer'), json.dumps(corps), content_type='application/json')

    def test_lieu_du_point_retrouve_toute_la_hierarchie_et_les_ids(self):
        d = self.client.get(reverse('geography:api_village_lieu'), {'lon': 47.05, 'lat': -17.95}).json()['lieu']
        self.assertEqual({k: v['nom'] for k, v in d.items()},
                         {'region': 'Analanjirofo', 'district': 'Fénérive Est', 'commune': 'Vohilengo', 'fokontany': 'Ambodiampaly'})
        self.assertEqual(d['region']['id'], str(self.region.id))
        self.assertEqual(d['district']['id'], str(self.district.id))        # retrouvé par le nom, sans lien préalable
        self.assertEqual(d['commune']['id'], str(self.commune.id))
        self.assertEqual(d['fokontany']['id'], str(self.fokontany.id))      # idem, dans la commune trouvée

    def test_lieu_hors_de_tout_contour(self):
        self.assertEqual(self.client.get(reverse('geography:api_village_lieu'), {'lon': 49.0, 'lat': -15.0}).json()['lieu'], {})

    def test_listes_en_cascade(self):
        url = reverse('geography:api_village_liste')
        self.assertEqual([i['nom'] for i in self.client.get(url, {'niveau': 'region'}).json()['items']], ['Analanjirofo'])
        self.assertEqual([i['nom'] for i in self.client.get(url, {'niveau': 'district', 'parent': str(self.region.id)}).json()['items']], ['Fénérive Est'])
        self.assertEqual([i['nom'] for i in self.client.get(url, {'niveau': 'commune', 'parent': str(self.district.id)}).json()['items']], ['Vohilengo'])
        self.assertEqual([i['nom'] for i in self.client.get(url, {'niveau': 'fokontany', 'parent': str(self.commune.id)}).json()['items']], ['Ambodiampaly', 'Autre'])
        self.assertEqual(self.client.get(url, {'niveau': 'planete'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'niveau': 'district', 'parent': 'pas-un-uuid'}).status_code, 400)

    def test_creation_rattache_au_fokontany_et_au_reseau(self):
        r = self.appeler('Nouveau village')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        v = Village.objects.get(pk=d['id'])
        self.assertEqual((v.nom_village, v.fokontany_id), ('Nouveau village', self.fokontany.id))
        self.assertAlmostEqual(float(v.latitude), -17.949, places=6)
        self.assertEqual((d['fokontany'], d['commune']), ('Ambodiampaly', 'Vohilengo'))
        acces = VillageAccesRoute.objects.get(village=v)
        self.assertEqual(acces.troncon_id, self.route.id)
        self.assertAlmostEqual(acces.distance_m, 111, delta=15)             # ~0,001° au nord de la route
        self.assertEqual(d['distance_route_m'], round(acces.distance_m))
        self.assertTrue(acces.reseau_principal)

    def test_refus_nom_vide_fokontany_absent_hors_madagascar(self):
        self.assertEqual(self.appeler('  ').status_code, 400)
        self.assertEqual(self.appeler('X', fokontany_id=None).status_code, 400)
        self.assertEqual(self.appeler('X', lon=2.3, lat=48.8).status_code, 400)
        self.assertEqual(self.client.post(reverse('geography:api_village_creer'), 'pas du json', content_type='application/json').status_code, 400)
        self.assertEqual(Village.objects.count(), 0)

    def test_doublon_de_nom_dans_le_fokontany(self):
        self.assertEqual(self.appeler('Mon Village').status_code, 200)
        r = self.appeler('mon  village'.replace('  ', ' '), lon=47.06, lat=-17.94)                  # même nom, autre endroit
        self.assertEqual(r.status_code, 400)
        self.assertIn('existe déjà', r.json()['error'])

    def test_village_proche_demande_confirmation(self):
        self.assertEqual(self.appeler('Premier').status_code, 200)
        r = self.appeler('Deuxieme', lon=47.0502)                                                  # ~20 m du premier
        self.assertEqual(r.status_code, 409)
        d = r.json()
        self.assertTrue(d['confirmation_requise'])
        self.assertEqual(d['proches'][0]['nom'], 'Premier')
        self.assertEqual(Village.objects.count(), 1)
        self.assertEqual(self.appeler('Deuxieme', lon=47.0502, confirmer_proches=True).status_code, 200)
        self.assertEqual(Village.objects.count(), 2)

    def test_creation_sans_reseau_charge(self):
        TronconRoute.objects.all().delete()
        r = self.appeler('Sans route')
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['distance_route_m'])
        self.assertFalse(VillageAccesRoute.objects.exists())

    def test_droits(self):
        self.client.logout()
        for nom_url in ('api_village_lieu', 'api_village_liste'):
            self.assertEqual(self.client.get(reverse(f'geography:{nom_url}')).status_code, 401)
        self.assertEqual(self.client.post(reverse('geography:api_village_creer'), '{}', content_type='application/json').status_code, 401)
        self.client.force_login(get_user_model().objects.create_user('simple', password='x'))
        self.assertEqual(self.appeler('X').status_code, 403)


class EditionCarteTests(TestCase):
    """Recherche de village, modification d'un village et d'un tronçon (sommets, noeuds partagés)."""

    def setUp(self):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        self.fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        self.fkt2 = Fokontany.objects.create(nom_fokontany='F2', commune=commune)
        self.v = Village.objects.create(nom_village='Ambodimanga', fokontany=self.fkt,
                                        latitude=Decimal('-17.99'), longitude=Decimal('47.02'))
        self.a, self.m, self.b = noeud(47.00, -18.0), noeud(47.02, -18.0), noeud(47.04, -18.0)
        c1, c2 = [[47.00, -18.0], [47.01, -18.0], [47.02, -18.0]], [[47.02, -18.0], [47.04, -18.0]]
        self.t1 = TronconRoute.objects.create(noeud_debut=self.a, noeud_fin=self.m, geometrie=c1, longueur_m=longueur_geodesique_m(c1))
        self.t2 = TronconRoute.objects.create(noeud_debut=self.m, noeud_fin=self.b, geometrie=c2, longueur_m=longueur_geodesique_m(c2))
        VillageAccesRoute.objects.create(village=self.v, troncon=self.t1, fraction=1.0, distance_m=1100,
                                         longitude=Decimal('47.02'), latitude=Decimal('-18.0'))
        self.client.force_login(get_user_model().objects.create_user('staff', password='x', is_staff=True))

    def post(self, nom, args, corps):
        return self.client.post(reverse(f'geography:{nom}', args=args), json.dumps(corps), content_type='application/json')

    def test_recherche_sans_accent_ni_casse(self):
        url = reverse('geography:api_village_recherche')
        for q in ('ambodi', 'AMBODI', 'ámbodimanga'):
            self.assertEqual([i['nom'] for i in self.client.get(url, {'q': q}).json()['items']], ['Ambodimanga'], q)
        self.assertEqual(self.client.get(url, {'q': 'a'}).json()['items'], [])
        self.assertEqual(self.client.get(url, {'q': 'zzz'}).json()['items'], [])

    def test_detail_village_donne_la_hierarchie(self):
        d = self.client.get(reverse('geography:api_village_detail', args=[self.v.pk])).json()['village']
        self.assertEqual(d['hierarchie']['fokontany']['id'], str(self.fkt.id))
        self.assertEqual(d['hierarchie']['commune']['nom'], 'C')

    def test_modifier_village_nom_et_fokontany_sans_deplacement(self):
        r = self.post('api_village_modifier', [self.v.pk], {'nom': 'Nouveau nom', 'fokontany_id': str(self.fkt2.id), 'lon': 47.02, 'lat': -17.99})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['deplace'])
        self.v.refresh_from_db()
        self.assertEqual((self.v.nom_village, self.v.fokontany_id), ('Nouveau nom', self.fkt2.id))
        self.assertEqual(VillageAccesRoute.objects.get(village=self.v).distance_m, 1100)

    def test_deplacer_village_recalcule_l_acces(self):
        r = self.post('api_village_modifier', [self.v.pk], {'nom': 'Ambodimanga', 'fokontany_id': str(self.fkt.id), 'lon': 47.03, 'lat': -17.999})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d['deplace'])
        self.assertAlmostEqual(d['distance_route_m'], 111, delta=15)
        self.assertEqual(VillageAccesRoute.objects.get(village=self.v).troncon_id, self.t2.id)

    def test_modifier_village_refus_et_proches(self):
        Village.objects.create(nom_village='Voisin', fokontany=self.fkt, latitude=Decimal('-17.9'), longitude=Decimal('47.03'))
        base = {'nom': 'X', 'fokontany_id': str(self.fkt.id), 'lon': 47.02, 'lat': -17.99}
        self.assertEqual(self.post('api_village_modifier', [self.v.pk], {**base, 'nom': ' '}).status_code, 400)
        self.assertEqual(self.post('api_village_modifier', [self.v.pk], {**base, 'nom': 'voisin'}).status_code, 400)
        self.assertEqual(self.post('api_village_modifier', [self.v.pk], {**base, 'lon': 2.3, 'lat': 48.8}).status_code, 400)
        self.assertEqual(self.post('api_village_modifier', [self.v.pk], {**base, 'lon': 47.0301, 'lat': -17.9}).status_code, 409)
        self.assertEqual(self.post('api_village_modifier', [self.v.pk], {**base, 'lon': 47.0301, 'lat': -17.9, 'confirmer_proches': True}).status_code, 200)

    def test_detail_troncon_signale_les_noeuds_partages(self):
        d = self.client.get(reverse('geography:api_troncon_detail', args=[self.t1.pk])).json()['troncon']
        self.assertEqual((d['debut_partage'], d['fin_partage']), (0, 1))

    def test_deplacer_un_sommet_interieur(self):
        r = self.post('api_troncon_modifier', [self.t1.pk], {'points': [[47.0, -18.0], [47.01, -17.995], [47.02, -18.0]]})
        self.assertEqual(r.status_code, 200)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.geometrie[1], [47.01, -17.995])
        self.assertGreater(self.t1.longueur_m, longueur_geodesique_m([[47.0, -18.0], [47.02, -18.0]]))
        acces = VillageAccesRoute.objects.get(village=self.v)
        self.assertAlmostEqual(acces.fraction, 0.8, places=2)          # le village est maintenant plus pres du coude
        self.assertLess(acces.distance_m, 1100)

    def test_ajouter_un_sommet_et_en_supprimer_un(self):
        self.post('api_troncon_modifier', [self.t1.pk], {'points': [[47.0, -18.0], [47.005, -18.0], [47.01, -18.0], [47.02, -18.0]]})
        self.t1.refresh_from_db()
        self.assertEqual(len(self.t1.geometrie), 4)
        self.post('api_troncon_modifier', [self.t1.pk], {'points': [[47.0, -18.0], [47.02, -18.0]]})
        self.t1.refresh_from_db()
        self.assertEqual(len(self.t1.geometrie), 2)

    def test_deplacer_un_noeud_de_jonction_entraine_les_voisins(self):
        r = self.post('api_troncon_modifier', [self.t1.pk], {'points': [[47.0, -18.0], [47.01, -18.0], [47.021, -18.002]]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['troncons_touches'], 2)
        self.m.refresh_from_db()
        self.assertEqual((float(self.m.longitude), float(self.m.latitude)), (47.021, -18.002))
        self.t2.refresh_from_db()
        self.assertEqual(self.t2.geometrie[0], [47.021, -18.002])
        self.assertEqual(self.t2.noeud_debut_id, self.m.id)

    def test_deplacer_un_noeud_sur_un_autre_fusionne(self):
        isole = noeud(47.05, -18.0)
        c = [[47.04, -18.0], [47.05, -18.0]]
        t3 = TronconRoute.objects.create(noeud_debut=self.b, noeud_fin=isole, geometrie=c, longueur_m=longueur_geodesique_m(c))
        r = self.post('api_troncon_modifier', [t3.pk], {'points': [[47.04, -18.0], [47.0, -18.0]]})
        self.assertEqual(r.status_code, 200)
        t3.refresh_from_db()
        self.assertEqual(t3.noeud_fin_id, self.a.id)
        self.assertFalse(NoeudRoute.objects.filter(pk=isole.pk).exists())

    def test_refus_troncon(self):
        for corps in ({'points': [[47.0, -18.0]]}, {'points': [[47.0, -18.0], [47.0, -18.0]]},
                      {'points': [[47.0, -18.0], [2.3, 48.8]]}, {'points': [[47.0, -18.0], [47.01, -18.0]], 'categorie': 'autoroute'},
                      {'points': [[47.0, -18.0], ['x', 1]]}):
            self.assertEqual(self.post('api_troncon_modifier', [self.t1.pk], corps).status_code, 400, corps)
        self.assertEqual(self.post('api_troncon_modifier', [self.t1.pk], {}).status_code, 400)

    def test_droits(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('geography:api_village_recherche')).status_code, 401)
        self.assertEqual(self.post('api_troncon_modifier', [self.t1.pk], {}).status_code, 401)
        self.client.force_login(get_user_model().objects.create_user('simple', password='x'))
        self.assertEqual(self.post('api_village_modifier', [self.v.pk], {}).status_code, 403)

    def test_villages_de_la_zone(self):
        url = reverse('geography:api_villages_zone')
        d = self.client.get(url, {'bbox': '47.0,-18.1,47.1,-17.9'}).json()
        self.assertEqual([v['nom'] for v in d['items']], ['Ambodimanga'])
        self.assertFalse(d['tronque'])
        self.assertEqual(self.client.get(url, {'bbox': '48,-18.1,48.1,-17.9'}).json()['items'], [])
        self.assertEqual(self.client.get(url, {'bbox': 'x'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'bbox': '40,-25,50,-10'}).status_code, 400)       # zone trop grande
        self.client.logout()
        self.assertEqual(self.client.get(url, {'bbox': '47,-18,47.1,-17.9'}).status_code, 401)
