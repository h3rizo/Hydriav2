from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytz
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.billing import frais_trajets
from apps.billing.models import PointEau, TypePointEau
from apps.employees.models import Employe
from apps.geography.models import Commune, District, Fokontany, Parcelle, Region, Village
from apps.geography.models_routes import NoeudRoute, TronconRoute, VillageAccesRoute
from apps.geography.services.reseau_routier import longueur_geodesique_m
from apps.organization.models import Base, Organisation, Ouvrage, TypeOuvrage
from apps.planning.models import Deplacement, Designation, Planning, PlanningDetail, PlanningDetailDeplacement, TypeDesignation

TZ = pytz.timezone('Indian/Antananarivo')


def noeud(lon, lat):
    return NoeudRoute.objects.create(longitude=Decimal(str(lon)), latitude=Decimal(str(lat)))


class FraisTrajetsTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nom_region='R')
        district = District.objects.create(nom_district='D', region=region)
        commune = Commune.objects.create(nom_commune='C', district=district)
        self.fkt = Fokontany.objects.create(nom_fokontany='F', commune=commune)
        # Route de 11 km ; villages V0..V3 à 0, 1, 2, 3 « unités » de 0,02° (~2,2 km).
        a, b = noeud(47.00, -18.0), noeud(47.10, -18.0)
        coords = [[47.00, -18.0], [47.10, -18.0]]
        self.route = TronconRoute.objects.create(noeud_debut=a, noeud_fin=b, geometrie=coords, categorie='nationale',
                                                 longueur_m=longueur_geodesique_m(coords))
        self.v = {i: self.village(i) for i in range(4)}
        self.type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG')
        self.type_point = TypePointEau.objects.create(nom_type='BF')
        self.ouvrage = {i: self.ouvrage_dans(i) for i in range(4)}

        org = Organisation.objects.create(nom_organisation='Org')
        self.base = Base.objects.create(nom_base='Base', organisation=org)
        self.agent = Employe.objects.create(nom_employe='Rakoto', surnom='Rako', base=self.base)
        self.designation = Designation.objects.create(
            nom='Frais de déplacement', type_designation=TypeDesignation.objects.create(nom='Avance'))
        self.admin = get_user_model().objects.create_superuser('admin', 'a@b.c', 'x')

    def village(self, i):
        lon = 47.00 + 0.02 * i
        v = Village.objects.create(nom_village=f'V{i}', fokontany=self.fkt, latitude=Decimal('-18.0'), longitude=Decimal(str(lon)))
        VillageAccesRoute.objects.create(village=v, troncon=self.route, fraction=(lon - 47.0) / 0.10, distance_m=0,
                                         longitude=Decimal(str(lon)), latitude=Decimal('-18.0'))
        return v

    def ouvrage_dans(self, i):
        o = Ouvrage.objects.create(nom_ouvrage=f'Ouvrage {i}', type_ouvrage=self.type_ouvrage)
        parcelle = Parcelle.objects.create(reference_parcelle=f'P{i}', village=self.v[i])
        PointEau.objects.create(ouvrage=o, parcelle=parcelle, type_point_eau=self.type_point, nomabonne=f'A{i}', idxls=str(i))
        return o

    def frais(self, i_ouvrage=None, trajet=None, a=None, b=None, pu=5000, moyen='taxi-brousse', jour=(2026, 10, 12), heure=9):
        planning = Planning.objects.create(employe=self.agent, ouvrage=self.ouvrage[i_ouvrage] if i_ouvrage is not None else None,
                                           date=TZ.localize(datetime(*jour, heure, 0)))
        detail = PlanningDetail.objects.create(planning=planning, designation=self.designation, quantity=1,
                                               pu=Decimal(pu), montant=Decimal(pu))
        if trajet or a or b:
            PlanningDetailDeplacement.objects.create(
                planning_detail=detail, trajet=trajet or 'aller', point_a=self.v[a] if a is not None else None,
                point_b=self.v[b] if b is not None else None, moyen_transport=moyen)
        return PlanningDetail.objects.select_related('planning__employe__base__village_depart').get(pk=detail.pk)

    def localiser_base(self, i=0):
        self.base.latitude_depart, self.base.longitude_depart = Decimal('-18.0'), self.v[i].longitude
        self.base.save()
        self.agent.refresh_from_db()

    def test_trajet_saisi_distance_et_duree(self):
        d = self.frais(a=0, b=3, trajet='aller')
        info = frais_trajets.analyser([d])['lignes'][d.id]
        self.assertEqual((info['source'], info['de'], info['vers']), ('saisi', 'V0', 'V3'))
        self.assertAlmostEqual(info['distance_km'], 0.6 * self.route.longueur_m / 1000, delta=0.1)
        self.assertGreater(info['duree_min'], 0)

    def test_trajet_estime_depuis_la_base_pour_aller_et_retour(self):
        self.localiser_base(0)
        aller = self.frais(i_ouvrage=2, trajet=None)
        # une ligne sans trajet saisi : par défaut c'est un aller
        info = frais_trajets.analyser([aller])['lignes'][aller.id]
        self.assertEqual((info['source'], info['de'], info['vers']), ('estime', 'Base', 'V2'))      # base placée par GPS : libellé = nom de la base
        self.assertAlmostEqual(info['distance_km'], 0.4 * self.route.longueur_m / 1000, delta=0.1)
        retour = self.frais(i_ouvrage=2, trajet='retour')
        retour_info = frais_trajets.analyser([retour])['lignes'][retour.id]
        self.assertEqual((retour_info['de'], retour_info['vers']), ('V2', 'Base'))

    def test_base_non_localisee_signalee(self):
        d = self.frais(i_ouvrage=2)
        info = frais_trajets.analyser([d])['lignes'][d.id]
        self.assertIsNone(info['source'])
        self.assertEqual([a['code'] for a in info['alertes']], ['base_non_localisee'])

    def test_planning_sans_lieu(self):
        self.localiser_base()
        d = self.frais(i_ouvrage=None)
        info = frais_trajets.analyser([d])['lignes'][d.id]
        self.assertEqual([a['code'] for a in info['alertes']], ['lieu_inconnu'])

    def test_prix_compare_au_prix_habituel(self):
        Deplacement.objects.create(point_a=self.v[0], point_b=self.v[3], moyen_transport='taxi-brousse',
                                   prix_unitaire=Decimal('5000'), date_prix=date(2026, 9, 1))
        normal = self.frais(a=0, b=3, trajet='aller', pu=5200)
        cher = self.frais(a=3, b=0, trajet='retour', pu=9000)     # sens inverse : même prix de référence
        bas = self.frais(a=0, b=3, trajet='aller', pu=1500)
        res = frais_trajets.analyser([normal, cher, bas])['lignes']
        self.assertEqual(res[normal.id]['alertes'], [])
        self.assertEqual(res[normal.id]['prix_reference'], 5000)
        self.assertEqual([a['code'] for a in res[cher.id]['alertes']], ['prix_eleve'])
        self.assertEqual(res[cher.id]['ecart_pct'], 80)
        self.assertEqual([a['code'] for a in res[bas.id]['alertes']], ['prix_bas'])

    def test_journee_chargee(self):
        # quatre trajets DISTINCTS de ~5 à 7 min en voiture : on abaisse le seuil à 15 min pour le test
        lignes = [self.frais(a=0, b=3, trajet='aller'), self.frais(a=3, b=0, trajet='retour'),
                  self.frais(a=0, b=2, trajet='aller'), self.frais(a=2, b=0, trajet='retour')]
        with patch.object(frais_trajets, 'JOURNEE_MAX_MIN', 15):
            res = frais_trajets.analyser(lignes)
        self.assertEqual(len(res['jours']), 1)
        self.assertEqual(res['jours'][0]['nb_trajets'], 4)
        self.assertTrue(res['jours'][0]['chargee'])
        self.assertIn('journee_chargee', [a['code'] for a in res['lignes'][lignes[0].id]['alertes']])
        self.assertEqual(res['resume']['jours_charges'], 1)

    def test_pirogue_sans_calcul_routier(self):
        d = self.frais(a=0, b=3, trajet='aller', moyen='pirogue')
        info = frais_trajets.analyser([d])['lignes'][d.id]
        self.assertIsNone(info['duree_min'])
        self.assertEqual(info['source'], 'saisi')

    def test_api_retour_frais_inclut_le_controle_sans_changer_les_montants(self):
        self.localiser_base(0)
        self.frais(i_ouvrage=2, pu=4000)
        self.frais(a=0, b=3, trajet='aller', pu=6000)
        self.client.force_login(self.admin)
        r = self.client.get(reverse('billing:api_frais_deplacement_employe'),
                            {'employe_id': str(self.agent.id), 'mois': 10, 'annee': 2026})
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertTrue(d['success'])
        self.assertEqual(d['total'], 2)
        self.assertEqual(sorted(f['montant'] for f in d['frais']), [4000.0, 6000.0])      # montants inchangés
        self.assertEqual({f['trajet_info']['source'] for f in d['frais']}, {'estime', 'saisi'})
        self.assertEqual(d['controle']['resume']['nb_lignes'], 2)
        self.assertEqual(d['controle']['resume']['nb_estimees'], 1)

    def test_ecran_charge(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('billing:retour_frais_deplacement'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Trajet routier')
        self.assertContains(r, 'controle-resume')

    def test_un_trajet_repete_le_meme_jour_n_est_compte_qu_une_fois(self):
        # 8 lignes pour le même trajet le même jour (plusieurs billets / désignations) = UN seul temps de route
        lignes = [self.frais(a=0, b=3, trajet='aller', heure=6 + i) for i in range(8)]
        une = frais_trajets.analyser(lignes[:1])['jours'][0]['duree_min']
        res = frais_trajets.analyser(lignes)
        self.assertEqual(res['jours'][0]['duree_min'], une)
        self.assertEqual((res['jours'][0]['nb_lignes'], res['jours'][0]['nb_trajets']), (8, 1))
        self.assertEqual(res['resume']['duree_min'], une)
        with patch.object(frais_trajets, 'JOURNEE_MAX_MIN', 15):
            self.assertFalse(frais_trajets.analyser(lignes)['jours'][0]['chargee'])

