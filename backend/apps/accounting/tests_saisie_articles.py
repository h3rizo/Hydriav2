from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.accounting import saisie_articles as sa


def _ligne(mode='hors_stock', q='5', recue='5', dest='ouvrage', label='Ambanja BP'):
    cible = SimpleNamespace(nom_ouvrage=label, surnom=label, nom=label, immatriculation=label)
    return {
        'designation': SimpleNamespace(nom='Tuyau'), 'mode': mode,
        'quantite': Decimal(q), 'quantite_recue': Decimal(recue), 'prix_unitaire': None,
        'destination_type': dest if mode == 'hors_stock' else '',
        'ouvrage': cible if dest == 'ouvrage' else None,
        'employe': cible if dest == 'employe' else None,
        'vehicule': cible if dest == 'vehicule' else None,
    }


class CompteConcerneTests(SimpleTestCase):
    def test_prefixes(self):
        for code in ('218100', '601', '6021', '605999'):
            self.assertTrue(sa.compte_concerne(code), code)
        for code in ('', None, '621102', '707401', '748411'):
            self.assertFalse(sa.compte_concerne(code), code)


class ComposerDetailTests(SimpleTestCase):
    def test_sans_reste_pas_de_ral(self):
        self.assertEqual(sa.composer_detail([_ligne()]), 'Ambanja BP')

    def test_reste_a_livrer(self):
        self.assertEqual(sa.composer_detail([_ligne(recue='2')]), 'Ambanja BP (RAL 3)')

    def test_regroupe_par_destination_et_ignore_le_stock(self):
        lignes = [_ligne(recue='4'), _ligne(recue='3'), _ligne(mode='stock')]
        self.assertEqual(sa.composer_detail(lignes), 'Ambanja BP (RAL 3)')

    def test_tronque_a_50(self):
        lignes = [_ligne(label='Ouvrage au nom vraiment tres tres long numero un'),
                  _ligne(label='Ouvrage au nom vraiment tres tres long numero deux')]
        self.assertLessEqual(len(sa.composer_detail(lignes)), sa.DETAIL_MAX)


class ParseArticlesTests(SimpleTestCase):
    def _parse(self, raw, designation, compte='601100', montant=Decimal('0')):
        with patch('apps.planning.models.Designation.objects') as objs:
            objs.filter.return_value.first.return_value = designation
            return sa.parse_articles(raw, MagicMock(), compte, montant)

    def test_compte_concerne_sans_article_avertit(self):
        _, errors, warnings, _ = self._parse([], None)
        self.assertEqual(errors, [])
        self.assertTrue(any('Aucun article' in w for w in warnings))

    def test_compte_non_concerne_ne_dit_rien(self):
        _, errors, warnings, rules = self._parse([], None, compte='621102')
        self.assertEqual((errors, warnings, rules), ([], [], []))

    def test_designation_inconnue(self):
        _, errors, _, _ = self._parse([{'designation_id': 'x', 'quantite': '1'}], None)
        self.assertTrue(errors)

    def test_stock_ok_et_reste(self):
        d = SimpleNamespace(nom='Tuyau')
        lignes, errors, warnings, _ = self._parse(
            [{'designation_id': 'x', 'mode': 'stock', 'quantite': '10', 'quantite_recue': '6', 'prix_unitaire': '100'}],
            d, montant=Decimal('1000'))
        self.assertEqual(errors, [])
        self.assertEqual(lignes[0]['quantite_recue'], Decimal('6'))
        self.assertTrue(any('reste a livrer' in w for w in warnings))

    def test_recue_superieure_a_la_quantite(self):
        d = SimpleNamespace(nom='Tuyau')
        _, errors, _, _ = self._parse(
            [{'designation_id': 'x', 'quantite': '2', 'quantite_recue': '3'}], d)
        self.assertTrue(errors)

    def test_hors_stock_exige_une_destination(self):
        d = SimpleNamespace(nom='Tuyau')
        _, errors, _, _ = self._parse(
            [{'designation_id': 'x', 'mode': 'hors_stock', 'quantite': '1'}], d)
        self.assertTrue(any('destination' in e for e in errors))

    def test_total_different_du_montant(self):
        d = SimpleNamespace(nom='Tuyau')
        _, _, warnings, _ = self._parse(
            [{'designation_id': 'x', 'quantite': '2', 'prix_unitaire': '500'}], d, montant=Decimal('5000'))
        self.assertTrue(any('different du montant' in w for w in warnings))


class PrixDesignationTests(SimpleTestCase):
    def _d(self, date_prix):
        return MagicMock(prix_unitaire=Decimal('10'), date_prix=date_prix)

    def test_met_a_jour_si_plus_recent_ou_vide(self):
        for date_prix in (None, date(2026, 1, 1), date(2026, 5, 1)):
            d = self._d(date_prix)
            sa._maj_prix_designation(d, Decimal('25'), date(2026, 5, 1))
            self.assertEqual(d.prix_unitaire, Decimal('25'))
            self.assertEqual(d.date_prix, date(2026, 5, 1))
            d.save.assert_called_once()

    def test_ne_touche_pas_un_prix_plus_recent(self):
        d = self._d(date(2026, 6, 1))
        sa._maj_prix_designation(d, Decimal('25'), date(2026, 5, 1))
        self.assertEqual(d.prix_unitaire, Decimal('10'))
        d.save.assert_not_called()

    def test_sans_prix_rien_ne_change(self):
        d = self._d(None)
        sa._maj_prix_designation(d, None, date(2026, 5, 1))
        d.save.assert_not_called()
