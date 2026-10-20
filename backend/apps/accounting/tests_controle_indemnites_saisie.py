"""Contrôle des indemnités (621102) à la saisie comptable : plafond annuel, forfaitaire pointé, dérogation."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounting.controle_indemnites_saisie import controler_indemnite_saisie
from apps.accounting.tests_indemnites_points import FakeCache
from apps.accounting.views_saisie_workflow import _derogation_accordee
from apps.employees.permissions import can_override_saisie_controls


def fake_user(poste=None, superuser=False):
    employe = SimpleNamespace(poste=SimpleNamespace(nom_poste=poste)) if poste else None
    return SimpleNamespace(is_authenticated=True, is_superuser=superuser, employe=employe)


class DerogationPermissionTests(SimpleTestCase):
    def test_seuls_directeur_et_responsable_operationnel(self):
        self.assertTrue(can_override_saisie_controls(fake_user('Directeur')))
        self.assertTrue(can_override_saisie_controls(fake_user('Responsable opérationnel')))
        self.assertFalse(can_override_saisie_controls(fake_user('Assistant(e) admin')))
        self.assertFalse(can_override_saisie_controls(fake_user('Responsable administratif et financier')))
        self.assertFalse(can_override_saisie_controls(fake_user()))

    def test_derogation_exige_droit_motif_et_aucune_erreur_dure(self):
        ok = {'errors': [], 'derogeables': ['x'], 'peut_deroger': True}
        self.assertTrue(_derogation_accordee(ok, {'derogation_motif': 'Accord direction du 30/09'}))
        self.assertFalse(_derogation_accordee(ok, {'derogation_motif': 'court'}))
        self.assertFalse(_derogation_accordee({**ok, 'peut_deroger': False}, {'derogation_motif': 'Accord direction'}))
        self.assertFalse(_derogation_accordee({**ok, 'errors': ['Base invalide']}, {'derogation_motif': 'Accord direction'}))
        self.assertFalse(_derogation_accordee({**ok, 'derogeables': []}, {'derogation_motif': 'Accord direction'}))


class ControleBase(TestCase):
    """Fixtures communes (ouvrage, deux points d'eau, aides de saisie) : aucun test ici."""

    @classmethod
    def setUpTestData(cls):
        from apps.billing.models import PointEau, TypePointEau
        from apps.organization.models import Ouvrage, TypeOuvrage

        type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='PMH')
        cls.ouvrage = Ouvrage.objects.create(nom_ouvrage='ZzCtrlAlpha', type_ouvrage=type_ouvrage)
        bf, _ = TypePointEau.objects.get_or_create(nom_type='BF')
        now = timezone.now()
        cls.p1 = PointEau.objects.create(
            ouvrage=cls.ouvrage, type_point_eau=bf, idxls='1', nomabonne='Borne Nord', datebranchement=now)
        cls.p2 = PointEau.objects.create(
            ouvrage=cls.ouvrage, type_point_eau=bf, idxls='2', nomabonne='Borne Sud', datebranchement=now)
        cls.year = timezone.localdate().year

    def setUp(self):
        from apps.core import views_ouvrage_interventions as v
        patcher = patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache())
        patcher.start()
        self.addCleanup(patcher.stop)
        self._seq = 0

    def label(self, idxls, montant):
        return f'X Y_Indemnité RBF{idxls} {self.year}_Fft_{montant}_ZzCtrlAlpha'

    def paid(self, idxls, montant, month=2):
        from apps.accounting.models import BaseDiameX
        self._seq += 1
        return BaseDiameX.objects.create(
            id_access=self._seq, fichier_source='t.accdb', date_m=date(self.year, month, 1), date_rec=date(self.year, month, 1),
            description=self.label(idxls, montant), montant_out=montant, montant_in=0, compte_code='621102', prog='P')

    def forfait(self, point, quantite, pointe=True):
        from apps.billing.models import PaiementForfaitaire
        return PaiementForfaitaire.objects.create(
            point_eau=point, date_facture=date(self.year, 1, 15), quantite=quantite, prix_unitaire=Decimal('10000'),
            montant=Decimal('10000') * quantite, numeroDiameX='12' if pointe else None, baseDiameX='P' if pointe else None)

    def controle(self, idxls, montant):
        return controler_indemnite_saisie(self.label(idxls, montant), date(self.year, 6, 1), Decimal(montant))


class ControleIndemniteTests(ControleBase):
    def test_dans_les_limites_aucun_blocage(self):
        self.forfait(self.p1, 4)
        self.paid('1', 20000)
        self.assertEqual(self.controle('1', 10000)['derogeables'], [])

    def test_plafond_annuel_de_40000_par_point_depasse(self):
        self.forfait(self.p1, 10)
        self.paid('1', 35000)
        messages = self.controle('1', 10000)['derogeables']
        self.assertEqual(len(messages), 1)
        self.assertIn('Plafond annuel dépassé', messages[0])

    def test_plafond_exact_autorise(self):
        self.forfait(self.p1, 4)
        self.paid('1', 30000)
        self.assertEqual(self.controle('1', 10000)['derogeables'], [])

    def test_le_plafond_est_par_point_d_eau(self):
        self.forfait(self.p1, 10)
        self.forfait(self.p2, 10)
        self.paid('1', 40000)
        self.assertEqual(self.controle('2', 10000)['derogeables'], [])        # l'autre point n'a rien reçu
        self.assertTrue(self.controle('1', 1000)['derogeables'])

    def test_point_sans_forfaitaire_pointe(self):
        messages = self.controle('1', 10000)['derogeables']
        self.assertEqual(len(messages), 1)
        self.assertIn('Aucun paiement forfaitaire pointé', messages[0])

    def test_forfaitaire_facture_mais_non_pointe_ne_couvre_pas(self):
        self.forfait(self.p1, 4, pointe=False)
        messages = self.controle('1', 10000)['derogeables']
        self.assertIn('pas encore pointée', messages[0])

    def test_forfaitaire_insuffisant(self):
        self.forfait(self.p1, 1)                                               # 1 unité : 10 000 Ar autorisés
        self.paid('1', 10000)
        messages = self.controle('1', 10000)['derogeables']
        self.assertEqual(len(messages), 1)
        self.assertIn('insuffisants', messages[0])

    def test_point_non_identifie_donne_un_avertissement_sans_bloquer(self):
        result = controler_indemnite_saisie(
            f'X Y_Indemnité RBF {self.year}_ZzCtrlInconnu', date(self.year, 6, 1), Decimal('50000'))
        self.assertEqual(result['derogeables'], [])
        self.assertTrue(result['warnings'])

    def test_une_saisie_deja_validee_compte_dans_le_cumul(self):
        from apps.accounting.models import SaisieComptable
        from apps.organization.models import Base, Compte, Journal, Organisation

        self.forfait(self.p1, 10)
        org = Organisation.objects.create(nom_organisation='ZzOrg')
        base = Base.objects.create(nom_base='ZzBase', organisation=org)
        journal = Journal.objects.create(base=base, nom_journal='ZzJ', code='ZZ')
        compte = Compte.objects.create(compte='621102', nom_compte='Indemnites', organisation=org)
        SaisieComptable.objects.create(
            base=base, journal=journal, compte=compte, compte_code='621102', date_m=date(self.year, 5, 1),
            description=self.label('1', 35000), montant_out=Decimal('35000'), statut='valide')
        self.assertTrue(self.controle('1', 10000)['derogeables'])              # 35 000 + 10 000 > 40 000


class ApprobationSaisieTests(ControleBase):
    """Liste « à valider » et approbation par la direction (mêmes données que le contrôle)."""

    def setUp(self):
        super().setUp()
        import json
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory
        from apps.accounting import views_saisie_workflow as v
        from apps.accounting.models import SaisieComptable
        from apps.organization.models import Base, Compte, Journal, Organisation

        self.json, self.v, self.rf = json, v, RequestFactory()
        self.user = get_user_model().objects.create_user('dir_test', password='x')
        org = Organisation.objects.create(nom_organisation='ZzOrgA')
        self.base = Base.objects.create(nom_base='ZzBaseA', organisation=org)
        self.journal = Journal.objects.create(base=self.base, nom_journal='ZzJA', code='ZA')
        self.compte = Compte.objects.create(compte='621102', nom_compte='Indemnites', organisation=org)
        self.forfait(self.p1, 10)
        self.paid('1', 35000)
        self.saisie = SaisieComptable.objects.create(
            base=self.base, journal=self.journal, compte=self.compte, compte_code='621102',
            date_m=date(self.year, 6, 1), description=self.label('1', 10000), montant_out=Decimal('10000'),
            statut='a_corriger')
        for name in ('_get_scoped_saisie_queryset',):
            patcher = patch.object(v, name, lambda user: SaisieComptable.objects.all())
            patcher.start(); self.addCleanup(patcher.stop)
        for name, model in (('_get_scoped_bases_queryset', Base), ('_get_scoped_journaux_queryset', Journal),
                            ('_get_scoped_comptes_queryset', Compte)):
            patcher = patch.object(v, name, lambda user, m=model: m.objects.all())
            patcher.start(); self.addCleanup(patcher.stop)

    def call(self, view, method='get', data=None, director=True):
        request = getattr(self.rf, method)('/x/', data=self.json.dumps(data or {}), content_type='application/json') \
            if method == 'post' else self.rf.get('/x/')
        request.user = self.user
        with patch.object(self.v, 'can_override_saisie_controls', return_value=director):
            response = view(request)
        return response.status_code, self.json.loads(response.content)

    def test_la_liste_contient_la_saisie_bloquee_par_un_controle(self):
        status, body = self.call(self.v.api_saisie_comptable_pending)
        self.assertEqual(status, 200)
        self.assertEqual([e['id'] for e in body['entries']], [str(self.saisie.id)])
        self.assertIn('Plafond annuel dépassé', body['entries'][0]['controles'][0])

    def test_liste_interdite_aux_autres_postes(self):
        self.assertEqual(self.call(self.v.api_saisie_comptable_pending, director=False)[0], 403)

    def test_approbation_exige_un_motif(self):
        status, body = self.call(self.v.api_saisie_comptable_approve, 'post', {'id': str(self.saisie.id), 'motif': 'ok'})
        self.assertEqual(status, 400)
        self.saisie.refresh_from_db()
        self.assertEqual(self.saisie.statut, 'a_corriger')

    def test_approbation_valide_et_trace_la_derogation(self):
        status, body = self.call(self.v.api_saisie_comptable_approve, 'post',
                                 {'id': str(self.saisie.id), 'motif': 'Accord de la direction'})
        self.assertEqual(status, 200)
        self.saisie.refresh_from_db()
        self.assertEqual(self.saisie.statut, 'valide')
        self.assertFalse(self.saisie.conforme)
        self.assertTrue(any('Derogation accordee' in r and 'Accord de la direction' in r
                            for r in self.saisie.regles_appliquees))
        self.assertEqual(self.call(self.v.api_saisie_comptable_pending)[1]['entries'], [])

    def test_approbation_interdite_aux_autres_postes(self):
        status, _ = self.call(self.v.api_saisie_comptable_approve, 'post',
                              {'id': str(self.saisie.id), 'motif': 'Accord de la direction'}, director=False)
        self.assertEqual(status, 403)

    def test_une_saisie_avec_erreur_dure_n_est_pas_approuvable(self):
        self.saisie.description = ''
        self.saisie.save()
        self.assertEqual(self.call(self.v.api_saisie_comptable_pending)[1]['entries'], [])
        status, _ = self.call(self.v.api_saisie_comptable_approve, 'post',
                              {'id': str(self.saisie.id), 'motif': 'Accord de la direction'})
        self.assertEqual(status, 400)


class JournalFermeTests(SimpleTestCase):
    def test_journaux_fermes_reconnus_par_leur_nom(self):
        from apps.accounting.views_saisie_workflow import _journal_ferme
        ferme = lambda nom: _journal_ferme(SimpleNamespace(nom_journal=nom))
        self.assertTrue(ferme('Banque recettes Tana (fermé)'))
        self.assertTrue(ferme('Banque EPI (ferme)'))
        self.assertTrue(ferme('Banque EPI (FERMÉ)'))
        self.assertFalse(ferme('Banque Tana'))
        self.assertFalse(ferme('Caisse Fermeture annuelle'))      # « fermeture » n'est pas « fermé »
        self.assertFalse(ferme(None))
