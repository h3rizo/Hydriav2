import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

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


class RbfYearSummaryTests(SimpleTestCase):
    lines = [
        (1, 'RBF', 2026, Decimal('20000')),
        (2, 'PPMH', 2026, Decimal('3000')),
        (3, 'RBF', 2026, Decimal('1000')),
        (4, 'RBF', 2025, Decimal('5000')),     # annee precedente : ignoree
        (5, 'BF', None, Decimal('900')),       # sans date : ignoree
    ]

    def test_seule_l_annee_demandee_compte(self):
        total, by_type, year_lines = v._rbf_year_summary(self.lines, 2026)
        self.assertEqual(total, Decimal('24000'))
        self.assertEqual([(i['type'], i['amount']) for i in by_type], [('RBF', Decimal('21000')), ('PPMH', Decimal('3000'))])
        self.assertEqual([line[0] for line in year_lines], [1, 2, 3])

    def test_aucune_ligne(self):
        self.assertEqual(v._rbf_year_summary([], 2026), (Decimal('0.00'), [], []))
        self.assertEqual(v._rbf_year_summary(self.lines, 2024)[0], Decimal('0.00'))


class IndemnitesRbfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.organization.models import Ouvrage, TypeOuvrage

        type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='PMH')
        cls.alpha = Ouvrage.objects.create(nom_ouvrage='ZzTestAlpha', type_ouvrage=type_ouvrage)
        cls.beta = Ouvrage.objects.create(nom_ouvrage='ZzTestBeta', type_ouvrage=type_ouvrage)
        cls.gamma = Ouvrage.objects.create(nom_ouvrage='ZzTestGamma', type_ouvrage=type_ouvrage)

    def line(self, description, montant, day, compte='621102', sortie=True):
        from apps.accounting.models import BaseDiameX
        self._seq = getattr(self, '_seq', 0) + 1
        return BaseDiameX.objects.create(
            id_access=self._seq, fichier_source='test.accdb', date_m=day, date_rec=day, description=description,
            montant_out=montant if sortie else 0, montant_in=0 if sortie else montant,
            compte_code=compte, prog='P')

    def seed(self):
        year = timezone.localdate().year
        self.line('MANARIASA Daniel_Indemnité RBF2 2025_Fft_20000_ZzTestAlpha', 20000, date(year, 2, 1))
        self.line('RAKOTO Jean_Indemnité RBF1_Trimestre_Fft_5000_Ar ZzTestAlpha', 5000, date(year - 1, 11, 1))
        self.line('_RAVONIARIMANANA Lucie_Indemnité PPMH_U_1_5000_ZzTestAlpha', 3000, date(year, 3, 1))
        self.line('RAMIADANA Francelette_Nettoyage BF3_Fft_20000_ZzTestBeta', 7000, date(year, 4, 1))
        self.line('X_Indemnité RBF1_Fft_5000_ZzTestAlpha', 999, date(year, 4, 1), compte='625107')   # autre compte
        return year

    def lines(self):
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            return v._rbf_indemnity_lines_by_ouvrage()

    def test_lignes_par_ouvrage_avec_annee_type_montant(self):
        year = self.seed()
        lines = self.lines()
        alpha = sorted(lines[str(self.alpha.id)], key=lambda line: line[3], reverse=True)
        self.assertEqual([(line[1], line[2], line[3]) for line in alpha],
                         [('RBF', year, Decimal('20000')), ('RBF', year - 1, Decimal('5000')), ('PPMH', year, Decimal('3000'))])
        self.assertEqual([(line[1], line[2]) for line in lines[str(self.beta.id)]], [('BF', year)])
        self.assertNotIn(str(self.gamma.id), lines)
        # l'IDXLS lu dans le libelle est conserve (RBF2 -> "2") ; pas de point d'eau en base -> id vide
        rbf2 = next(line for line in alpha if line[3] == Decimal('20000'))
        self.assertEqual((rbf2[4], rbf2[5]), ('', '2'))

    def test_ignore_autres_comptes_entrees_et_ouvrage_inconnu(self):
        year = timezone.localdate().year
        self.line('X_Indemnité RBF1_Fft_5000_ZzTestAlpha', 9999, date(year, 1, 1), compte='625107')
        self.line('X_Indemnité RBF1_Fft_5000_ZzTestAlpha', 8888, date(year, 1, 1), sortie=False)
        self.line('X_Indemnité RBF1_Fft_5000_ZzInconnuQwx', 7777, date(year, 1, 1))
        lines = self.lines()
        self.assertNotIn(str(self.alpha.id), lines)
        self.assertFalse(any(line[3] == Decimal('7777') for rows in lines.values() for line in rows))

    def test_le_cache_redonne_les_memes_valeurs(self):
        self.seed()
        cache = FakeCache()
        with patch.object(v, 'OUVRAGE_CARD_CACHE', cache):
            first = v._rbf_indemnity_lines_by_ouvrage()
            self.assertEqual(len(cache.data), 1)
            second = v._rbf_indemnity_lines_by_ouvrage()     # 2e appel : lu depuis le cache
        self.assertEqual(first, second)

    def test_cartes_ne_montrent_que_l_annee_en_cours(self):
        year = self.seed()
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            alpha, gamma = v._attach_ouvrage_card_metrics([self.alpha, self.gamma])
        self.assertEqual(alpha.card_rbf_current_year, Decimal('23000'))          # 20000 + 3000, sans l'annee precedente
        self.assertEqual(alpha.card_rbf_lines_count, 2)
        self.assertEqual([i['type'] for i in alpha.card_rbf_by_type], ['RBF', 'PPMH'])
        self.assertFalse(hasattr(alpha, 'card_rbf_total'))                        # plus de cumul
        self.assertEqual((gamma.card_rbf_current_year, gamma.card_rbf_lines_count, gamma.card_rbf_by_type),
                         (Decimal('0.00'), 0, []))

    def test_ouvrage_avec_seulement_des_paiements_anterieurs_n_affiche_rien(self):
        year = timezone.localdate().year
        self.line('R_Indemnité RBF1_Trimestre_Fft_5000_Ar ZzTestAlpha', 5000, date(year - 1, 11, 1))
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            (alpha,) = v._attach_ouvrage_card_metrics([self.alpha])
        self.assertEqual(alpha.card_rbf_current_year, Decimal('0.00'))

    def test_pas_d_indemnites_pour_les_clients(self):
        self.seed()
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            (alpha,) = v._attach_ouvrage_card_metrics([self.alpha], include_indemnities=False)
        self.assertEqual((alpha.card_rbf_current_year, alpha.card_rbf_by_type), (Decimal('0.00'), []))

    def test_une_panne_du_calcul_ne_casse_pas_les_cartes(self):
        with patch.object(v, '_rbf_indemnity_lines_by_ouvrage', side_effect=RuntimeError('boom')), \
                patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            (alpha,) = v._attach_ouvrage_card_metrics([self.alpha])
        self.assertEqual(alpha.card_rbf_current_year, Decimal('0.00'))


class DetailIndemnitesRbfTests(IndemnitesRbfTests):
    def call(self, ouvrage, *, client=False, staff=False):
        request = RequestFactory().get('/x')
        request.user = SimpleNamespace(
            is_authenticated=True, is_staff=staff, is_superuser=False, client=object() if client else None)
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()), \
                patch.object(v, '_accessible_ouvrages', return_value=type(ouvrage).objects.all()):
            response = v.details_indemnites_rbf_ouvrage.__wrapped__.__wrapped__(request, ouvrage.id)
        return response.status_code, json.loads(response.content)

    def test_detail_limite_a_l_annee_en_cours(self):
        year = self.seed()
        status, data = self.call(self.alpha)

        self.assertEqual((status, data['success'], data['compte'], data['year']), (200, True, '621102', year))
        self.assertEqual(data['summary']['total'], 23000.0)
        self.assertEqual(data['summary']['count'], 2)
        self.assertEqual([i['type'] for i in data['summary']['par_type']], ['RBF', 'PPMH'])
        self.assertEqual(len(data['rows']), 2)                       # ni l'annee precedente, ni l'autre ouvrage/compte
        self.assertTrue(all(r['date'].startswith(str(year)) for r in data['rows']))
        self.assertEqual(sum(r['amount'] for r in data['rows']), 23000.0)
        self.assertEqual([r['date'] for r in data['rows']], sorted((r['date'] for r in data['rows']), reverse=True))
        self.assertTrue(all(r['description'] and r['id_access'] for r in data['rows']))
        for cle in ('cumul', 'par_annee', 'current_year'):
            self.assertNotIn(cle, data['summary'])

    def test_ouvrage_sans_paiement_cette_annee(self):
        status, data = self.call(self.gamma)
        self.assertEqual((status, data['rows'], data['summary']['total'], data['summary']['count']), (200, [], 0.0, 0))

    def test_refuse_aux_comptes_clients(self):
        self.seed()
        status, data = self.call(self.alpha, client=True)
        self.assertEqual((status, data['success']), (403, False))
        status, _ = self.call(self.alpha, client=True, staff=True)   # un staff reste autorise
        self.assertEqual(status, 200)
