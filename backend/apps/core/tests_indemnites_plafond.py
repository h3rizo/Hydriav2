import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from apps.core import views_ouvrage_interventions as v


class FakeCache:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, timeout=None):
        self.data[key] = value


class CapStatusTests(SimpleTestCase):
    def expl(self, montant):
        return SimpleNamespace(montant_paye=Decimal(montant))

    def test_sous_le_plafond_et_pile_au_plafond(self):
        for total in ('0', '39999', '120000'):
            status = v._rbf_cap_status(Decimal(total), 3, None)
            self.assertFalse(status['over'], total)
            self.assertFalse(status['needs_explanation'])
        self.assertEqual(v._rbf_cap_status(Decimal('120000'), 3, None)['cap'], Decimal('120000'))   # 3 x 40 000

    def test_depassement_sans_explication(self):
        status = v._rbf_cap_status(Decimal('120001'), 3, None)
        self.assertEqual((status['over'], status['excess'], status['needs_explanation'], status['explained']),
                         (True, Decimal('1'), True, False))

    def test_explication_couvre_le_montant_saisi_mais_pas_un_montant_superieur(self):
        self.assertTrue(v._rbf_cap_status(Decimal('130000'), 3, self.expl('130000'))['explained'])
        self.assertTrue(v._rbf_cap_status(Decimal('125000'), 3, self.expl('130000'))['explained'])
        stale = v._rbf_cap_status(Decimal('135000'), 3, self.expl('130000'))
        self.assertEqual((stale['explained'], stale['needs_explanation']), (False, True))

    def test_aucun_point_public_tout_paiement_depasse(self):
        status = v._rbf_cap_status(Decimal('5000'), 0, None)
        self.assertEqual((status['cap'], status['over'], status['excess']), (Decimal('0'), True, Decimal('5000')))
        self.assertFalse(v._rbf_cap_status(Decimal('0'), 0, None)['over'])


class PlafondIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.billing.models import PointEau, TypePointEau
        from apps.organization.models import Ouvrage, TypeOuvrage

        type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='PMH')
        cls.alpha = Ouvrage.objects.create(nom_ouvrage='ZzTestAlpha', type_ouvrage=type_ouvrage)
        cls.beta = Ouvrage.objects.create(nom_ouvrage='ZzTestBeta', type_ouvrage=type_ouvrage)
        cls.gamma = Ouvrage.objects.create(nom_ouvrage='ZzTestGamma', type_ouvrage=type_ouvrage)
        borne = TypePointEau.objects.create(nom_type='ZzBorne fontaine')
        prive = TypePointEau.objects.create(nom_type='ZzBranchement Privé')
        bp = TypePointEau.objects.create(nom_type='BP')
        now = timezone.now()

        def point(ouvrage, type_, **kwargs):
            defaults = {'datebranchement': now}
            defaults.update(kwargs)
            return PointEau.objects.create(ouvrage=ouvrage, type_point_eau=type_, **defaults)

        # alpha : 2 publics (comptent) + 1 prive + 1 BP + 1 arrete + 1 non branche (ne comptent pas)
        point(cls.alpha, borne); point(cls.alpha, borne)
        point(cls.alpha, prive); point(cls.alpha, bp)
        point(cls.alpha, borne, datearretbranchement=now)
        point(cls.alpha, borne, datebranchement=None)
        # beta : 1 public
        point(cls.beta, borne)
        # gamma : uniquement du prive
        point(cls.gamma, prive)

    def line(self, description, montant, day):
        from apps.accounting.models import BaseDiameX
        self._seq = getattr(self, '_seq', 0) + 1
        return BaseDiameX.objects.create(
            id_access=self._seq, fichier_source='t.accdb', date_m=day, date_rec=day, description=description,
            montant_out=montant, montant_in=0, compte_code='621102', prog='P')

    def pay(self, ouvrage_name, montant, day=None, kind='Indemnité RBF1_Trimestre_Fft'):
        year = timezone.localdate().year
        return self.line(f'X Y_{kind}_5000_Ar {ouvrage_name}', montant, day or date(year, 2, 1))

    def cards(self, ouvrages, **kwargs):
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            return v._attach_ouvrage_card_metrics(list(ouvrages), **kwargs)

    def explain(self, ouvrage, montant, plafond, points, text='Deux mois payés en retard'):
        from apps.core.models import ExplicationDepassementIndemnite
        return ExplicationDepassementIndemnite.objects.create(
            ouvrage=ouvrage, annee=timezone.localdate().year, montant_paye=Decimal(montant),
            plafond=Decimal(plafond), nb_points_publics=points, explication=text)

    # ---- points d'eau publics
    def test_points_publics_meme_definition_que_l_analyse_des_couts(self):
        counts = v._public_points_by_ouvrage([self.alpha.id, self.beta.id, self.gamma.id])
        self.assertEqual(counts.get(str(self.alpha.id)), 2)
        self.assertEqual(counts.get(str(self.beta.id)), 1)
        self.assertNotIn(str(self.gamma.id), counts)          # uniquement du prive : 0 point public

    # ---- cartes
    def test_carte_sous_le_plafond(self):
        self.pay('ZzTestAlpha', 70000)                       # plafond alpha = 2 x 40 000 = 80 000
        (alpha,) = self.cards([self.alpha])
        self.assertEqual((alpha.card_rbf_public_points, alpha.card_rbf_cap), (2, Decimal('80000')))
        self.assertFalse(alpha.card_rbf_over)
        self.assertEqual((alpha.card_rbf_needs_explanation, alpha.card_rbf_explained), (False, False))

    def test_carte_en_depassement_sans_puis_avec_explication(self):
        self.pay('ZzTestAlpha', 50000); self.pay('ZzTestAlpha', 40000)     # 90 000 > 80 000
        (alpha,) = self.cards([self.alpha])
        self.assertTrue(alpha.card_rbf_over)
        self.assertEqual(alpha.card_rbf_excess, Decimal('10000'))
        self.assertEqual((alpha.card_rbf_needs_explanation, alpha.card_rbf_explained), (True, False))

        self.explain(self.alpha, 90000, 80000, 2)
        (alpha,) = self.cards([self.alpha])
        self.assertTrue(alpha.card_rbf_over)                                # toujours un depassement...
        self.assertEqual((alpha.card_rbf_needs_explanation, alpha.card_rbf_explained), (False, True))   # ...explique

        self.pay('ZzTestAlpha', 5000)                                       # nouveau paiement : explication perimee
        (alpha,) = self.cards([self.alpha])
        self.assertEqual((alpha.card_rbf_needs_explanation, alpha.card_rbf_explained), (True, False))

    def test_explication_d_une_autre_annee_ne_couvre_pas(self):
        from apps.core.models import ExplicationDepassementIndemnite
        self.pay('ZzTestBeta', 50000)                                       # plafond beta = 40 000
        ExplicationDepassementIndemnite.objects.create(
            ouvrage=self.beta, annee=timezone.localdate().year - 1, montant_paye=Decimal('99999'),
            plafond=Decimal('40000'), nb_points_publics=1, explication='Ancienne annee')
        (beta,) = self.cards([self.beta])
        self.assertTrue(beta.card_rbf_needs_explanation)

    def test_ouvrage_sans_point_public_avec_indemnite(self):
        self.pay('ZzTestGamma', 5000)
        (gamma,) = self.cards([self.gamma])
        self.assertEqual((gamma.card_rbf_public_points, gamma.card_rbf_cap, gamma.card_rbf_over), (0, Decimal('0'), True))

    def test_pas_de_plafond_pour_les_clients(self):
        self.pay('ZzTestBeta', 50000)
        (beta,) = self.cards([self.beta], include_indemnities=False)
        self.assertEqual((beta.card_rbf_over, beta.card_rbf_needs_explanation, beta.card_rbf_current_year),
                         (False, False, Decimal('0.00')))

    # ---- statistique
    def test_statistique_des_ouvrages_en_depassement(self):
        year = timezone.localdate().year
        self.pay('ZzTestAlpha', 90000)                        # > 80 000  -> depasse, explique
        self.explain(self.alpha, 90000, 80000, 2)
        self.pay('ZzTestBeta', 50000)                         # > 40 000  -> depasse, sans explication
        self.pay('ZzTestGamma', 1000, day=date(year - 1, 5, 1))   # annee precedente : ignore
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            over, unexplained = v._rbf_over_cap_ouvrage_ids(
                [self.alpha.id, self.beta.id, self.gamma.id], year)
        self.assertEqual(over, {str(self.alpha.id), str(self.beta.id)})
        self.assertEqual(unexplained, {str(self.beta.id)})

    def test_statistique_sans_depassement(self):
        self.pay('ZzTestAlpha', 10000)
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            self.assertEqual(v._rbf_over_cap_ouvrage_ids([self.alpha.id], timezone.localdate().year), (set(), set()))

    # ---- endpoints
    def request(self, method='get', body=None, *, client=False, staff=False, user=None, query=''):
        factory = RequestFactory()
        request = (factory.post('/x' + query, data=json.dumps(body or {}), content_type='application/json')
                   if method == 'post' else factory.get('/x' + query))
        request.user = user or SimpleNamespace(
            is_authenticated=True, is_staff=staff, is_superuser=False, client=object() if client else None,
            get_full_name=lambda: 'Jean Test', get_username=lambda: 'jtest', employe=None)
        return request

    def call(self, view, ouvrage, **kwargs):
        request = self.request(**kwargs)
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()), \
                patch.object(v, '_accessible_ouvrages', return_value=type(ouvrage).objects.all()):
            response = view.__wrapped__.__wrapped__(request, ouvrage.id) if hasattr(view.__wrapped__, '__wrapped__') \
                else view.__wrapped__(request, ouvrage.id)
        return response.status_code, json.loads(response.content)

    def test_detail_contient_le_plafond_et_l_historique(self):
        self.pay('ZzTestBeta', 50000)
        self.explain(self.beta, 50000, 40000, 1, text='Reprise de deux mois en retard')
        status, data = self.call(v.details_indemnites_rbf_ouvrage, self.beta)
        self.assertEqual(status, 200)
        self.assertEqual(data['plafond'], {
            'per_point': 40000.0, 'public_points': 1, 'cap': 40000.0, 'over': True, 'excess': 10000.0,
            'explained': True, 'needs_explanation': False})
        self.assertEqual([e['text'] for e in data['explications']], ['Reprise de deux mois en retard'])

    def receive_forfait(self, ouvrage_name, montant, day):
        from apps.accounting.models import BaseDiameX
        self._seq = getattr(self, '_seq', 0) + 1
        return BaseDiameX.objects.create(
            id_access=self._seq, fichier_source='t.accdb', date_m=day, date_rec=day,
            description=f'Paiement forfaitaire_U_1_{montant}_{ouvrage_name}',
            montant_in=montant, montant_out=0, compte_code='748411', prog='P')

    def forfait_paiement(self, point, montant, day, numero='N1', base='B1'):
        from apps.billing.models import PaiementForfaitaire
        return PaiementForfaitaire.objects.create(
            point_eau=point, date_facture=day, quantite=1, prix_unitaire=montant, montant=montant,
            numeroDiameX=numero, baseDiameX=base)

    def test_detail_relie_chaque_point_a_ses_forfaitaires_pointes(self):
        from apps.billing.models import PointEau, TypePointEau
        year = timezone.localdate().year
        bf = TypePointEau.objects.create(nom_type='BF')
        point = PointEau.objects.create(ouvrage=self.beta, type_point_eau=bf, idxls='3', datebranchement=timezone.now())
        self.line('RAMIADANA Francelette_Nettoyage BF3_Fft_20000_ZzTestBeta', 7000, date(year, 4, 1))
        self.line('RAKOTO Jean_Indemnité RBF1_Trimestre_Fft_5000_Ar ZzTestBeta', 5000, date(year, 4, 2))  # point non identifie
        self.forfait_paiement(point, 4000, date(year, 3, 1))                       # pointe
        self.forfait_paiement(point, 4000, date(year, 6, 1), numero='', base='')  # non pointe
        self.forfait_paiement(point, 9999, date(year - 1, 3, 1))                   # autre annee : ignore

        status, data = self.call(v.details_indemnites_rbf_ouvrage, self.beta)
        self.assertEqual(status, 200)
        by_status = {group['status']: group for group in data['points']}
        linked = by_status['over']                       # 7 000 payes > 4 000 pointes
        self.assertEqual((linked['rbf_total'], linked['forfait_total'], linked['gap']), (7000.0, 4000.0, -3000.0))
        self.assertEqual([f['amount'] for f in linked['forfaits']], [4000.0])
        self.assertEqual((linked['unpointed_count'], linked['unpointed_total']), (1, 4000.0))
        self.assertEqual(by_status['unlinked']['forfaits'], [])
        self.assertEqual([g['status'] for g in data['points']], ['over', 'unlinked'])   # non rattaches en dernier

    def test_point_avec_indemnite_sans_forfaitaire_pointe(self):
        from apps.billing.models import PointEau, TypePointEau
        year = timezone.localdate().year
        bf = TypePointEau.objects.create(nom_type='BF')
        PointEau.objects.create(ouvrage=self.beta, type_point_eau=bf, idxls='3', datebranchement=timezone.now())
        self.line('RAMIADANA Francelette_Nettoyage BF3_Fft_20000_ZzTestBeta', 7000, date(year, 4, 1))
        _, data = self.call(v.details_indemnites_rbf_ouvrage, self.beta)
        self.assertEqual([g['status'] for g in data['points']], ['no_forfait'])

    def test_carte_compare_indemnites_et_forfaitaire(self):
        self.pay('ZzTestBeta', 30000)
        self.receive_forfait('ZzTestBeta', 20000, date(timezone.localdate().year, 2, 10))
        (beta,) = self.cards([self.beta])
        self.assertEqual((beta.card_forfait_received, beta.card_rbf_forfait_pct, beta.card_rbf_exceeds_forfait),
                         (Decimal('20000'), 150, True))

    def test_enregistrer_explication(self):
        from apps.core.models import ExplicationDepassementIndemnite
        self.pay('ZzTestBeta', 50000)
        user = get_user_model().objects.create_user('explicateur', password='x')
        user.client = None
        status, data = self.call(v.enregistrer_explication_indemnite_ouvrage, self.beta, method='post',
                                 body={'explication': '  Deux mois payés en retard, régularisés en février.  '},
                                 user=user)
        self.assertEqual((status, data['success']), (200, True))
        saved = ExplicationDepassementIndemnite.objects.get()
        self.assertEqual((saved.ouvrage_id, saved.annee, saved.montant_paye, saved.plafond, saved.nb_points_publics),
                         (self.beta.id, timezone.localdate().year, Decimal('50000'), Decimal('40000'), 1))
        self.assertEqual((saved.explication, saved.created_by_id), (
            'Deux mois payés en retard, régularisés en février.', user.id))
        self.assertEqual(data['explication']['author'], 'explicateur')

        # le depassement est desormais explique
        (beta,) = self.cards([self.beta])
        self.assertEqual((beta.card_rbf_needs_explanation, beta.card_rbf_explained), (False, True))

    def test_explication_refusee_sans_depassement_ou_trop_courte_ou_client(self):
        from apps.core.models import ExplicationDepassementIndemnite
        self.pay('ZzTestAlpha', 10000)                       # sous le plafond de 80 000
        status, data = self.call(v.enregistrer_explication_indemnite_ouvrage, self.alpha, method='post',
                                 body={'explication': 'Une explication assez longue'})
        self.assertEqual(status, 400)
        self.assertIn('Aucun depassement', data['error'])

        self.pay('ZzTestBeta', 50000)
        status, data = self.call(v.enregistrer_explication_indemnite_ouvrage, self.beta, method='post',
                                 body={'explication': 'court'})
        self.assertEqual(status, 400)
        status, _ = self.call(v.enregistrer_explication_indemnite_ouvrage, self.beta, method='post',
                              body={'explication': 'x' * 2001})
        self.assertEqual(status, 400)
        status, _ = self.call(v.enregistrer_explication_indemnite_ouvrage, self.beta, method='post',
                              body={'explication': 'Une explication assez longue'}, client=True)
        self.assertEqual(status, 403)
        self.assertEqual(ExplicationDepassementIndemnite.objects.count(), 0)


    # ---- suivi sur plusieurs annees
    def test_statistique_multi_annees(self):
        year = timezone.localdate().year
        self.pay('ZzTestBeta', 50000, day=date(year - 1, 5, 1))          # > 40 000 l'an dernier
        self.pay('ZzTestGamma', 1000, day=date(year - 4, 5, 1))          # hors de la fenetre suivie
        ids = [self.alpha.id, self.beta.id, self.gamma.id]
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            self.assertEqual(v._rbf_over_cap_ouvrage_ids(ids, year), (set(), set()))        # annee en cours seule
            over, unexplained = v._rbf_over_cap_ouvrage_ids(ids, v._rbf_tracked_years())
        self.assertEqual((over, unexplained), ({str(self.beta.id)}, {str(self.beta.id)}))

    def test_carte_signale_le_depassement_d_une_annee_precedente(self):
        year = timezone.localdate().year
        self.pay('ZzTestBeta', 50000, day=date(year - 1, 5, 1))
        (beta,) = self.cards([self.beta])
        self.assertEqual([(a['year'], a['excess'], a['explained']) for a in beta.card_rbf_past_alerts],
                         [(year - 1, Decimal('10000.00'), False)])
        self.assertFalse(beta.card_rbf_over)                      # l'annee en cours n'est pas en cause

    def test_explication_d_une_annee_precedente(self):
        from apps.core.models import ExplicationDepassementIndemnite
        year = timezone.localdate().year
        self.pay('ZzTestBeta', 50000, day=date(year - 1, 5, 1))
        user = get_user_model().objects.create_user('explicateur2', password='x')
        user.client = None
        status, data = self.call(v.details_indemnites_rbf_ouvrage, self.beta, query=f'?annee={year - 1}')
        self.assertEqual((status, data['year'], data['plafond']['over']), (200, year - 1, True))
        status, _ = self.call(v.enregistrer_explication_indemnite_ouvrage, self.beta, method='post', user=user,
                              query=f'?annee={year - 1}', body={'explication': 'Retard de paiement de 2025'})
        self.assertEqual(status, 200)
        self.assertEqual(ExplicationDepassementIndemnite.objects.get().annee, year - 1)
        (beta,) = self.cards([self.beta])
        self.assertTrue(beta.card_rbf_past_alerts[0]['explained'])
        # une annee hors fenetre retombe sur l'annee en cours
        status, data = self.call(v.details_indemnites_rbf_ouvrage, self.beta, query=f'?annee={year - 9}')
        self.assertEqual(data['year'], year)

    def test_indemnite_d_une_autre_annee_dans_le_libelle(self):
        year = timezone.localdate().year
        # libelle 2025 paye en 2026 : compte dans 2025, pas dans l'annee en cours
        self.line(f'X Y_Indemnité RBF1 {year - 1}_Fft_50000_ZzTestBeta', 50000, date(year, 2, 1))
        (beta,) = self.cards([self.beta])
        self.assertEqual(beta.card_rbf_current_year, Decimal('0.00'))
        self.assertEqual([a['year'] for a in beta.card_rbf_past_alerts], [year - 1])
