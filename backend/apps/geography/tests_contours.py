import json
import os
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Commune, District, Fokontany, Parcelle, Region, Village
from .models_contours import ContourAdmin
from .services import contours_communes as svc

CARRE = {'type': 'Polygon', 'coordinates': [[[47.0, -18.0], [47.1, -18.0], [47.1, -17.9], [47.0, -17.9], [47.0, -18.0]]]}
CARRE_SIMPLE = {'type': 'Polygon', 'coordinates': [[[47.0, -18.0], [47.1, -18.0], [47.1, -17.9], [47.0, -18.0]]]}


def enregistrement(cle, nom, ouest=47.0, sud=-18.0, est=47.1, nord=-17.9, **extra):
    return {'cle': cle, 'nom': nom, 'p_code': cle, 'geometrie': CARRE, 'geometrie_simple': CARRE_SIMPLE,
            'ouest': ouest, 'sud': sud, 'est': est, 'nord': nord, **extra}


class OutilsContoursTests(TestCase):
    def test_normaliser_ignore_accents_et_ponctuation(self):
        self.assertEqual(svc.normaliser('Ambohimangakely-II'), 'ambohimangakely ii')
        self.assertEqual(svc.normaliser('  Fénérive  Est '), 'fenerive est')
        self.assertEqual(svc.normaliser(None), '')

    def test_cles_dupliquees_rendues_uniques_et_stables(self):
        lignes = [{'cle': 'A'}, {'cle': 'B'}, {'cle': 'A'}, {'cle': 'A'}]
        self.assertEqual([e['cle'] for e in svc.rendre_cles_uniques(lignes)], ['A', 'B', 'A~2', 'A~3'])


class ImportContoursTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(nom_region='Analamanga')
        self.district = District.objects.create(nom_district='Ambohidratrimo', region=self.region)
        self.commune = Commune.objects.create(nom_commune='Ivato Firaisana', district=self.district)
        # même nom dans deux districts : le district départage
        self.autre_district = District.objects.create(nom_district='Autre', region=self.region)
        self.doublon = Commune.objects.create(nom_commune='Ambohitrandriana', district=self.autre_district)
        Commune.objects.create(nom_commune='Ambohitrandriana', district=self.district)

    def importer(self, niveau, lignes):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, f'{niveau}.json')
            with open(chemin, 'w', encoding='utf-8') as f:
                json.dump({'niveau': niveau, 'enregistrements': lignes}, f)
            call_command('importer_contours', chemin, verbosity=0)

    def test_import_json_idempotent_avec_rattachement(self):
        lignes = [enregistrement('1', 'Ivato-Firaisana', district_nom='Ambohidratrimo', enclave='non'),
                  enregistrement('2', 'Ailleurs', district_nom='Autre')]
        self.importer('commune', lignes)
        self.assertEqual(ContourAdmin.objects.filter(niveau='commune').count(), 2)
        k = ContourAdmin.objects.get(niveau='commune', cle='1')
        self.assertEqual(k.objet_id, self.commune.id)                 # accents / tirets ignorés
        self.assertEqual(k.enclave, 'non')
        self.assertIsNone(ContourAdmin.objects.get(niveau='commune', cle='2').objet_id)
        lignes[0]['enclave'] = 'oui'
        self.importer('commune', lignes)                              # réimport : mise à jour, pas de doublon
        self.assertEqual(ContourAdmin.objects.filter(niveau='commune').count(), 2)
        self.assertEqual(ContourAdmin.objects.get(niveau='commune', cle='1').enclave, 'oui')

    def test_le_district_departage_deux_communes_homonymes(self):
        self.importer('commune', [enregistrement('5', 'Ambohitrandriana', district_nom='Autre')])
        self.assertEqual(ContourAdmin.objects.get(cle='5').objet_id, self.doublon.id)

    def test_nom_ambigu_non_rattache(self):
        # district inconnu et deux communes homonymes en base : on ne devine pas
        self.importer('commune', [enregistrement('6', 'Ambohitrandriana', district_nom='Inconnu')])
        self.assertIsNone(ContourAdmin.objects.get(cle='6').objet_id)

    def test_regions_et_districts(self):
        self.importer('region', [enregistrement('MDG11|analamanga', 'Analamanga')])
        self.importer('district', [enregistrement('D1', 'Ambohidratrimo', region_nom='Analamanga')])
        self.assertEqual(ContourAdmin.objects.get(niveau='region').objet_id, self.region.id)
        self.assertEqual(ContourAdmin.objects.get(niveau='district').objet_id, self.district.id)


class ApiContoursTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nom_region='Analamanga')
        district = District.objects.create(nom_district='D', region=region)
        self.commune = Commune.objects.create(nom_commune='Ivato', district=district)
        fkt = Fokontany.objects.create(nom_fokontany='F', commune=self.commune)
        village = Village.objects.create(nom_village='V', fokontany=fkt, latitude=Decimal('-18'), longitude=Decimal('47.05'))
        Parcelle.objects.create(reference_parcelle='P1', village=village, nombre_habitants=120)
        Parcelle.objects.create(reference_parcelle='P2', village=village, nombre_habitants=80)
        base = dict(niveau='commune', geometrie=CARRE, geometrie_simple=CARRE_SIMPLE, ouest=47.0, sud=-18.0, est=47.1, nord=-17.9)
        ContourAdmin.objects.create(cle='1', nom='Ivato', objet_id=self.commune.id, statut_soakoja='Paiement forfaitaire', **base)
        ContourAdmin.objects.create(cle='2', nom='Loin', **{**base, 'ouest': 49.0, 'est': 49.1})
        ContourAdmin.objects.create(niveau='fokontany', cle='9', nom='Fkt', geometrie=CARRE, geometrie_simple=CARRE_SIMPLE,
                                    ouest=47.0, sud=-18.0, est=47.1, nord=-17.9)
        self.client.force_login(get_user_model().objects.create_user('u', password='x'))
        self.url = reverse('geography:api_geojson_contours')

    def appel(self, **p):
        return self.client.get(self.url, p)

    def test_validation_des_parametres(self):
        self.assertEqual(self.appel(niveau='planete').status_code, 400)
        self.assertEqual(self.appel(niveau='fokontany').status_code, 400)                 # zone obligatoire
        self.assertEqual(self.appel(niveau='commune', bbox='a,b').status_code, 400)
        self.assertEqual(self.appel(niveau='commune', zoom='x').status_code, 400)

    def test_filtre_par_zone(self):
        d = self.appel(niveau='commune').json()
        self.assertEqual(sorted(f['properties']['nom'] for f in d['features']), ['Ivato', 'Loin'])
        d = self.appel(niveau='commune', bbox='46.9,-18.1,47.2,-17.8').json()
        self.assertEqual([f['properties']['nom'] for f in d['features']], ['Ivato'])
        self.assertEqual(d['nb_total'], 2)

    def test_detail_selon_le_zoom(self):
        loin = self.appel(niveau='commune', bbox='46.9,-18.1,47.2,-17.8', zoom=6).json()['features'][0]['geometry']
        pres = self.appel(niveau='commune', bbox='46.9,-18.1,47.2,-17.8', zoom=12).json()['features'][0]['geometry']
        self.assertEqual(loin, CARRE_SIMPLE)
        self.assertEqual(pres, CARRE)

    def test_statistiques_pour_les_objets_de_la_base(self):
        p = self.appel(niveau='commune', bbox='46.9,-18.1,47.2,-17.8').json()['features'][0]['properties']
        self.assertTrue(p['en_base'])
        self.assertEqual((p['population'], p['nb_villages']), (200, 1))
        self.assertEqual(p['statut_soakoja'], 'Paiement forfaitaire')
        sans = [f for f in self.appel(niveau='commune').json()['features'] if f['properties']['nom'] == 'Loin'][0]['properties']
        self.assertFalse(sans['en_base'])
        self.assertIsNone(sans['population'])

    def test_les_anciennes_api_se_rabattent_sur_les_contours_sans_postgis(self):
        ContourAdmin.objects.create(niveau='region', cle='R|x', nom='Analamanga', geometrie=CARRE, geometrie_simple=CARRE_SIMPLE,
                                    ouest=47.0, sud=-18.0, est=47.1, nord=-17.9)
        d = self.client.get(reverse('geography:api_geojson_regions')).json()
        self.assertEqual([f['properties']['nom'] for f in d['features']], ['Analamanga'])
        sans_bbox = self.client.get(reverse('geography:api_geojson_fokontany')).json()         # 17 000 polygones : zone obligatoire
        self.assertEqual(sans_bbox['features'], [])
        avec_bbox = self.client.get(reverse('geography:api_geojson_fokontany'), {'bbox': '46.9,-18.1,47.2,-17.8'}).json()
        self.assertEqual(len(avec_bbox['features']), 1)


class ContourDeCommuneTests(TestCase):
    """Contour de la commune choisie et de ses voisines, pour la page de détail d'une commune."""

    def setUp(self):
        region = Region.objects.create(nom_region='Analanjirofo')
        district = District.objects.create(nom_district='Fénérive Est', region=region)
        self.commune = Commune.objects.create(nom_commune='Vohilengo', district=district)
        base = dict(niveau='commune', geometrie=CARRE, geometrie_simple=CARRE_SIMPLE)
        ContourAdmin.objects.create(cle='1', nom='Vohilengo', district_nom='Fénérive Est', statut_soakoja='Gestion mixte',
                                    ouest=47.0, sud=-18.0, est=47.1, nord=-17.9, **base)
        ContourAdmin.objects.create(cle='2', nom='Voisine', district_nom='Fénérive Est', ouest=47.1, sud=-18.0, est=47.2, nord=-17.9, **base)
        ContourAdmin.objects.create(cle='3', nom='Loin', district_nom='Autre', ouest=49.0, sud=-18.0, est=49.1, nord=-17.9, **base)
        # homonyme dans un autre district : ne doit pas être choisi
        ContourAdmin.objects.create(cle='4', nom='Vohilengo', district_nom='Farafangana', ouest=47.0, sud=-23.0, est=47.1, nord=-22.9, **base)

    def test_trouve_le_contour_par_nom_et_district_sans_lien_prealable(self):
        self.assertEqual(svc.contour_commune(self.commune).cle, '1')

    def test_le_lien_objet_id_prime(self):
        ContourAdmin.objects.filter(cle='4').update(objet_id=self.commune.id)
        self.assertEqual(svc.contour_commune(self.commune).cle, '4')

    def test_polygones_commune_et_voisines(self):
        features = svc.polygones_commune(self.commune)
        self.assertEqual([(f['properties']['nom'], f['properties']['selected']) for f in features],
                         [('Vohilengo', True), ('Voisine', False)])                  # 'Loin' et l'homonyme exclus
        self.assertEqual(features[0]['properties']['details'], ['Statut Soakoja : Gestion mixte'])
        self.assertEqual(features[0]['geometry'], CARRE)

    def test_commune_sans_contour(self):
        autre = Commune.objects.create(nom_commune='Inconnue', district=self.commune.district)
        self.assertEqual(svc.polygones_commune(autre), [])


class ContoursPagesDetailTests(TestCase):
    """Contours pour les pages village, ouvrage et district."""

    def setUp(self):
        self.region = Region.objects.create(nom_region='Analanjirofo')
        self.district = District.objects.create(nom_district='Fénérive Est', region=self.region)
        self.commune = Commune.objects.create(nom_commune='Vohilengo', district=self.district)
        self.fokontany = Fokontany.objects.create(nom_fokontany='Ambodimanga', commune=self.commune)
        self.village = Village.objects.create(nom_village='V', fokontany=self.fokontany, latitude=Decimal('-17.95'), longitude=Decimal('47.05'))
        carre = dict(geometrie=CARRE, geometrie_simple=CARRE_SIMPLE, ouest=47.0, sud=-18.0, est=47.1, nord=-17.9)
        ContourAdmin.objects.create(niveau='district', cle='D|fenerive est', nom='Fénérive Est', region_nom='Analanjirofo',
                                    district_pcode='MDG11', **carre)
        ContourAdmin.objects.create(niveau='commune', cle='1', nom='Vohilengo', district_nom='Fénérive Est', district_pcode='MDG11',
                                    statut_soakoja='Gestion mixte', **carre)
        ContourAdmin.objects.create(niveau='commune', cle='2', nom='Autre commune', district_nom='Fénérive Est', district_pcode='MDG11', **carre)
        ContourAdmin.objects.create(niveau='commune', cle='3', nom='Ailleurs', district_nom='Autre', district_pcode='MDG99', **carre)
        ContourAdmin.objects.create(niveau='fokontany', cle='10', nom='Ambodimanga', commune_nom='Vohilengo', **carre)
        ContourAdmin.objects.create(niveau='fokontany', cle='11', nom='Ambodimanga', commune_nom='Une autre commune', **carre)

    def test_contour_du_fokontany_departage_par_la_commune(self):
        self.assertEqual(svc.contour_fokontany(self.fokontany).cle, '10')

    def test_fokontany_sans_contour(self):
        autre = Fokontany.objects.create(nom_fokontany='Inconnu', commune=self.commune)
        self.assertIsNone(svc.contour_fokontany(autre))

    def test_contour_du_district_par_nom_et_region(self):
        self.assertEqual(svc.contour_district(self.district).cle, 'D|fenerive est')

    def test_contours_village_commune_puis_fokontany_selectionne(self):
        features = svc.contours_village(self.village)
        self.assertEqual([(f['properties']['role'], f['properties']['selected']) for f in features],
                         [('commune', False), ('fokontany', True)])

    def test_contours_des_communes_desservies_sans_doublon(self):
        features = svc.contours_communes_de([self.commune, self.commune, None])
        self.assertEqual([f['properties']['nom'] for f in features], ['Vohilengo'])

    def test_contours_district_et_ses_communes_seulement(self):
        features = svc.contours_district(self.district)
        self.assertEqual(features[0]['properties']['role'], 'district')
        self.assertEqual(sorted(f['properties']['nom'] for f in features[1:]), ['Autre commune', 'Vohilengo'])   # pas 'Ailleurs'

    def test_page_district_expose_la_carte(self):
        self.client.force_login(get_user_model().objects.create_superuser('adm', 'a@b.c', 'x'))
        reponse = self.client.get(reverse('geography:district_detail', args=[self.district.pk]))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.context['carte_contours']['features']), 3)
        self.assertContains(reponse, 'district-contours-map')

    def test_page_district_sans_contour_n_affiche_pas_de_carte(self):
        autre = District.objects.create(nom_district='Sans contour', region=self.region)
        self.client.force_login(get_user_model().objects.create_superuser('adm2', 'a@b.c', 'x'))
        reponse = self.client.get(reverse('geography:district_detail', args=[autre.pk]))
        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, 'district-contours-map')
