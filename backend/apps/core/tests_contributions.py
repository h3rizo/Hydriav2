from decimal import Decimal
from types import SimpleNamespace

import pytz
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.contributions import POIDS_CATEGORIES, _evenements
from apps.core.models import ContributionTerrain
from apps.core.views_contributions import calculer_classement

tz_madagascar = pytz.timezone('Indian/Antananarivo')

PE = 'billing.PointEau'
EQ = 'infrastructure.EquipementConstitutif'


def pe(**kw):
    base = dict(nomabonne='', numeroteleph=None, contactabonne=None, latitude=None, longitude=None, photos=None)
    base.update(kw)
    return SimpleNamespace(**base)


def resume(evenements):
    return sorted((e['categorie'], e['action'], e['quantite']) for e in evenements)


class EvenementsContributionTests(SimpleTestCase):
    def test_creation_compte_chaque_donnee_apportee(self):
        obj = pe(nomabonne='Rakoto', numeroteleph='0341234567', latitude=-17.1, longitude=49.4,
                 photos=[{'url': 'a'}, {'url': 'b'}])
        self.assertEqual(resume(_evenements(PE, obj, None)), [
            ('gps', 'ajout', 1), ('nom_abonne', 'ajout', 1), ('photo', 'ajout', 2), ('telephone', 'ajout', 1)])

    def test_gps_deux_champs_comptent_une_seule_intervention(self):
        avant = dict(nomabonne='X', numeroteleph=None, contactabonne=None, latitude=None, longitude=None, photos=None)
        obj = pe(nomabonne='X', latitude=-17.1, longitude=49.4)
        self.assertEqual(resume(_evenements(PE, obj, avant)), [('gps', 'ajout', 1)])

    def test_correction_compte_comme_modification(self):
        avant = dict(nomabonne='Rakoto', numeroteleph=None, contactabonne=None, latitude=None, longitude=None, photos=None)
        obj = pe(nomabonne='Rakoto Jean')
        self.assertEqual(resume(_evenements(PE, obj, avant)), [('nom_abonne', 'modification', 1)])

    def test_meme_valeur_ne_cree_rien(self):
        avant = dict(nomabonne='Rakoto', numeroteleph='034', contactabonne=None, latitude=-17.1, longitude=49.4, photos=[1])
        obj = pe(nomabonne=' Rakoto ', numeroteleph='034', latitude=-17.1000001, longitude=49.4, photos=[1])
        self.assertEqual(_evenements(PE, obj, avant), [])

    def test_vide_et_none_sont_equivalents(self):
        avant = dict(nomabonne='X', numeroteleph=None, contactabonne=None, latitude=None, longitude=None, photos=None)
        self.assertEqual(_evenements(PE, pe(nomabonne='X', numeroteleph=''), avant), [])

    def test_photos_ajoutees_et_supprimees(self):
        avant = dict(nomabonne='X', numeroteleph=None, contactabonne=None, latitude=None, longitude=None, photos=[1, 2])
        self.assertEqual(resume(_evenements(PE, pe(nomabonne='X', photos=[1, 2, 3, 4, 5]), avant)),
                         [('photo', 'ajout', 3)])
        self.assertEqual(resume(_evenements(PE, pe(nomabonne='X', photos=[1]), avant)),
                         [('photo', 'suppression', 1)])

    def test_volume_citerne_equipement(self):
        avant = dict(latitude=None, longitude=None, photos=None, volume_m3=None)
        obj = SimpleNamespace(latitude=None, longitude=None, photos=None, volume_m3=Decimal('10.00'))
        self.assertEqual(resume(_evenements(EQ, obj, avant)), [('volume_citerne', 'ajout', 1)])
        avant['volume_m3'] = Decimal('10.00')
        obj.volume_m3 = Decimal('15.00')
        self.assertEqual(resume(_evenements(EQ, obj, avant)), [('volume_citerne', 'modification', 1)])


class ClassementContributionsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('chef', password='x', is_staff=True)
        maintenant = timezone.now()
        for categorie, action, quantite in [('photo', 'ajout', 3), ('gps', 'ajout', 1), ('gps', 'modification', 1)]:
            ContributionTerrain.objects.create(
                user=self.admin, modele='pointeau', objet_id='1', categorie=categorie,
                action=action, quantite=quantite, date=maintenant)
        ContributionTerrain.objects.create(
            user=self.admin, modele='pointeau', objet_id='1', categorie='photo', action='suppression',
            quantite=9, date=maintenant)

    def test_calcul_ignore_les_suppressions(self):
        jour = timezone.now().astimezone(tz_madagascar).date()
        classement = calculer_classement(jour, jour)
        self.assertEqual(len(classement), 1)
        self.assertEqual(classement[0]['interventions'], 3)
        self.assertEqual(classement[0]['corrections'], 1)
        self.assertEqual(classement[0]['par_categorie']['photo'], 3)
        self.assertEqual(classement[0]['points'], 3 * POIDS_CATEGORIES['photo'] + 2 * POIDS_CATEGORIES['gps'])

    def test_page_reservee_a_la_direction(self):
        self.client.force_login(User.objects.create_user('simple', password='x'))
        self.assertEqual(self.client.get('/contributions/classement/').status_code, 403)
        self.client.force_login(self.admin)
        reponse = self.client.get('/contributions/classement/?format=json')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['classement'][0]['interventions'], 3)
