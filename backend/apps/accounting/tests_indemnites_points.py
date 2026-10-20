from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounting import indemnites_points as ip

PLAFOND = Decimal('40000')


class FakeCache:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, timeout=None):
        self.data[key] = value


class CountersTests(SimpleTestCase):
    def test_cle_du_point(self):
        self.assertEqual(ip.counter_key('o1', 'p1', '2'), 'pe:p1')
        self.assertEqual(ip.counter_key('o1', '', '2'), 'idxls:o1:2')
        self.assertEqual(ip.counter_key('o1', '', ''), 'none:o1')

    def test_cumul_par_point_et_par_annee(self):
        index = {'o1': [
            (1, 'RBF', 2026, Decimal('20000'), 'p1', '1'),
            (2, 'RBF', 2026, Decimal('25000'), 'p1', '1'),      # p1 / 2026 : 45 000
            (3, 'RBF', 2025, Decimal('30000'), 'p1', '1'),      # p1 / 2025 : 30 000
            (4, 'RBF', 2026, Decimal('5000'), 'p2', '2'),
            (5, 'PPMH', 2026, Decimal('7000'), '', ''),         # sans point
            (6, 'RBF', None, Decimal('999'), 'p1', '1'),        # sans date : ignore
        ]}
        counters, by_line = ip.build_counters(index)
        self.assertEqual(counters[('pe:p1', 2026)]['total'], Decimal('45000'))
        self.assertEqual(counters[('pe:p1', 2026)]['count'], 2)
        self.assertEqual(counters[('pe:p1', 2025)]['total'], Decimal('30000'))
        self.assertEqual(counters[('pe:p2', 2026)]['total'], Decimal('5000'))
        self.assertFalse(counters[('none:o1', 2026)]['identified'])
        self.assertEqual((by_line[1], by_line[3]), (('pe:p1', 2026), ('pe:p1', 2025)))
        self.assertNotIn(6, by_line)

    def test_ids_des_ecritures_d_un_point_pour_une_annee(self):
        index = {'o1': [
            (1, 'RBF', 2026, Decimal('20000'), 'p1', '1'),
            (2, 'RBF', 2026, Decimal('25000'), 'p1', '1'),
            (3, 'RBF', 2025, Decimal('30000'), 'p1', '1'),      # autre annee
            (4, 'RBF', 2026, Decimal('5000'), 'p2', '2'),       # autre point
            (5, 'PPMH', 2026, Decimal('7000'), '', ''),
        ]}
        self.assertEqual(sorted(ip.line_ids_for_point(index, 'pe:p1', 2026)), [1, 2])
        self.assertEqual(ip.line_ids_for_point(index, 'pe:p1', '2025'), [3])           # annee recue en texte depuis l'URL
        self.assertEqual(ip.line_ids_for_point(index, 'none:o1', 2026), [5])
        self.assertEqual(ip.line_ids_for_point(index, 'pe:inconnu', 2026), [])

    def test_plafond_par_point(self):
        mk = lambda total, identified=True: {'total': Decimal(total), 'identified': identified}
        self.assertEqual(ip.cap_status(mk('40000'), PLAFOND), {'cap': PLAFOND, 'over': False, 'excess': Decimal('0.00')})
        self.assertEqual(ip.cap_status(mk('40001'), PLAFOND), {'cap': PLAFOND, 'over': True, 'excess': Decimal('1')})
        self.assertEqual(ip.cap_status(mk('90000', False), PLAFOND), {'cap': None, 'over': False, 'excess': Decimal('0.00')})


class PointsIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.billing.models import PointEau, TypePointEau
        from apps.organization.models import Ouvrage, TypeOuvrage

        type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='PMH')
        cls.alpha = Ouvrage.objects.create(nom_ouvrage='ZzTestAlpha', type_ouvrage=type_ouvrage)
        cls.solo = Ouvrage.objects.create(nom_ouvrage='ZzTestSolo', type_ouvrage=type_ouvrage)
        bf, _ = TypePointEau.objects.get_or_create(nom_type='BF')
        now = timezone.now()
        cls.p1 = PointEau.objects.create(ouvrage=cls.alpha, type_point_eau=bf, idxls='1', nomabonne='Borne Nord', datebranchement=now)
        cls.p2 = PointEau.objects.create(ouvrage=cls.alpha, type_point_eau=bf, idxls='2', nomabonne='Borne Sud', datebranchement=now)
        cls.p_solo = PointEau.objects.create(ouvrage=cls.solo, type_point_eau=bf, idxls='1', nomabonne='Seule borne', datebranchement=now)

    def line(self, description, montant, day):
        from apps.accounting.models import BaseDiameX
        self._seq = getattr(self, '_seq', 0) + 1
        return BaseDiameX.objects.create(
            id_access=self._seq, fichier_source='t.accdb', date_m=day, date_rec=day, description=description,
            montant_out=montant, montant_in=0, compte_code='621102', prog='P')

    def index(self):
        from apps.core import views_ouvrage_interventions as v
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            return v._rbf_indemnity_lines_by_ouvrage()

    def context(self, filtered, page):
        return ip.build_context([e.id for e in filtered], page, self.index(), PLAFOND)

    def test_imputation_au_bon_point_et_depassement(self):
        year = timezone.localdate().year
        a = self.line('X Y_Indemnité RBF1 2026_Fft_20000_ZzTestAlpha', 20000, date(year, 2, 1))
        b = self.line('X Y_Indemnité RBF1 2026_Fft_25000_ZzTestAlpha', 25000, date(year, 3, 1))    # p1 : 45 000
        c = self.line('X Z_Indemnité RBF2 2026_Fft_10000_ZzTestAlpha', 10000, date(year, 3, 1))    # p2 : 10 000
        entries = [SimpleNamespace(id=x.id) for x in (a, b, c)]
        result = self.context([a, b, c], entries)

        by_id = {e.id: e.rbf_counter for e in entries}
        self.assertEqual((by_id[a.id]['total'], by_id[a.id]['over'], by_id[a.id]['excess']),
                         (Decimal('45000'), True, Decimal('5000')))
        self.assertEqual(by_id[a.id], by_id[b.id])                     # meme point, meme compteur
        self.assertEqual((by_id[c.id]['total'], by_id[c.id]['over']), (Decimal('10000'), False))
        self.assertIn('Borne Nord', by_id[a.id]['point_label'])
        self.assertEqual(by_id[a.id]['ouvrage'], 'ZzTestAlpha')

        rows = result['rows']
        self.assertEqual([r['point_label'].split(' — ')[-1] for r in rows], ['Borne Nord', 'Borne Sud'])   # dépassement en premier
        self.assertEqual(result['summary']['points'], 2)
        self.assertEqual(result['summary']['over'], 1)
        self.assertEqual(result['summary']['excess'], Decimal('5000'))

    def test_le_cumul_ignore_les_filtres_de_la_page(self):
        year = timezone.localdate().year
        a = self.line('X Y_Indemnité RBF1 2026_Fft_20000_ZzTestAlpha', 20000, date(year, 2, 1))
        self.line('X Y_Indemnité RBF1 2026_Fft_25000_ZzTestAlpha', 25000, date(year, 3, 1))   # hors filtre (autre mois)
        page = [SimpleNamespace(id=a.id)]
        result = self.context([a], page)                                                    # seul `a` est affiche
        self.assertEqual(page[0].rbf_counter['total'], Decimal('45000'))                     # mais le cumul est complet
        self.assertTrue(page[0].rbf_counter['over'])
        self.assertEqual(result['summary']['over'], 1)

    def test_annees_separees(self):
        year = timezone.localdate().year
        old = self.line('X Y_Indemnité RBF1 2025_Fft_39000_ZzTestAlpha', 39000, date(year - 1, 12, 1))
        new = self.line('X Y_Indemnité RBF1 2026_Fft_10000_ZzTestAlpha', 10000, date(year, 1, 1))
        page = [SimpleNamespace(id=old.id), SimpleNamespace(id=new.id)]
        self.context([old, new], page)
        self.assertEqual([(p.rbf_counter['year'], p.rbf_counter['total'], p.rbf_counter['over']) for p in page],
                         [(year - 1, Decimal('39000'), False), (year, Decimal('10000'), False)])

    def test_idxls_inconnu_n_est_pas_impute_au_premier_point(self):
        year = timezone.localdate().year
        x = self.line('X Y_Indemnité RBF9 2026_Fft_20000_ZzTestAlpha', 20000, date(year, 2, 1))   # IDXLS 9 n'existe pas
        page = [SimpleNamespace(id=x.id)]
        self.context([x], page)
        counter = page[0].rbf_counter
        self.assertTrue(counter['identified'])
        self.assertIn('non retrouvé', counter['point_label'])
        self.assertEqual(counter['key'], f'idxls:{self.alpha.id}:9')                # pas 'pe:<premier point>'

    def test_libelle_sans_idxls_point_unique_ou_non_identifie(self):
        year = timezone.localdate().year
        solo = self.line('_RAVO Lucie_Indemnité PPMH_U_1_5000_ZzTestSolo', 5000, date(year, 2, 1))       # 1 seul point
        multi = self.line('_RAVO Lucie_Indemnité PPMH_U_1_5000_ZzTestAlpha', 3000, date(year, 2, 1))     # 2 points possibles
        page = [SimpleNamespace(id=solo.id), SimpleNamespace(id=multi.id)]
        result = self.context([solo, multi], page)
        self.assertTrue(page[0].rbf_counter['identified'])
        self.assertIn('Seule borne', page[0].rbf_counter['point_label'])
        self.assertFalse(page[1].rbf_counter['identified'])
        self.assertEqual(page[1].rbf_counter['point_label'], "Point d'eau non identifié")
        self.assertIsNone(page[1].rbf_counter['cap'])
        self.assertEqual(result['summary']['unidentified_total'], Decimal('3000'))

    def test_ligne_hors_index_sans_compteur(self):
        page = [SimpleNamespace(id=987654321)]
        result = self.context([], page)
        self.assertFalse(hasattr(page[0], 'rbf_counter') and page[0].rbf_counter)
        self.assertEqual((result['rows'], result['summary']['points']), ([], 0))
