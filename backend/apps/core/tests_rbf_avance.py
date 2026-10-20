from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.core import rbf_avance

POINT = SimpleNamespace(id="p1", ouvrage_id="o1")


def verdict(montant, periodes=0, payees=(), en_cours=(), when=date(2026, 5, 10)):
    with mock.patch("apps.core.widget_rbf.effective_payment_counts", return_value={"p1": periodes} if periodes else {}), \
         mock.patch.object(rbf_avance, "lignes_diamex", return_value=list(payees)), \
         mock.patch.object(rbf_avance, "avances_en_cours", return_value=list(en_cours)):
        return rbf_avance.evaluer(POINT, Decimal(montant), when)


def ok_of(result):
    return {c["code"]: c["ok"] for c in result["controles"]}


class EvaluerAvanceRbfTests(SimpleTestCase):
    def test_autorise_quand_pointe_sans_doublon(self):
        r = verdict(10000, periodes=1)
        self.assertTrue(r["autorise"])

    def test_refuse_sans_paiement_pointe(self):
        r = verdict(10000, periodes=0)
        self.assertFalse(r["autorise"])
        self.assertFalse(ok_of(r)["pointe"])

    def test_refuse_quand_capacite_epuisee_par_diamex_et_avances(self):
        # 2 périodes = 20 000 Ar : 10 000 payés (T1) + 10 000 avancés (T2) -> plus rien pour T3
        r = verdict(10000, periodes=2, payees=[(Decimal(10000), date(2026, 2, 3))],
                    en_cours=[(Decimal(10000), date(2026, 4, 20))], when=date(2026, 8, 1))
        self.assertFalse(ok_of(r)["pointe"])
        self.assertTrue(ok_of(r)["doublon"])

    def test_doublon_meme_trimestre_diamex(self):
        r = verdict(10000, periodes=2, payees=[(Decimal(10000), date(2026, 4, 3))], when=date(2026, 6, 30))
        self.assertFalse(ok_of(r)["doublon"])
        self.assertFalse(r["autorise"])

    def test_doublon_meme_trimestre_avance_en_cours(self):
        r = verdict(10000, periodes=2, en_cours=[(Decimal(10000), date(2026, 5, 2))], when=date(2026, 5, 10))
        self.assertFalse(ok_of(r)["doublon"])

    def test_autre_trimestre_pas_doublon(self):
        r = verdict(10000, periodes=2, payees=[(Decimal(10000), date(2026, 1, 15))], when=date(2026, 5, 10))
        self.assertTrue(r["autorise"])

    def test_plafond_annuel(self):
        # 5 périodes pointées mais plafond 40 000 : 30 000 déjà payés + 20 000 demandés dépasse
        r = verdict(20000, periodes=5, payees=[(Decimal(30000), date(2026, 1, 15))], when=date(2026, 8, 1))
        self.assertFalse(ok_of(r)["plafond"])
        self.assertFalse(r["autorise"])

    def test_montant_nul_refuse(self):
        self.assertFalse(verdict(0, periodes=1)["autorise"])

    def test_trimestre(self):
        self.assertEqual([rbf_avance.trimestre(date(2026, m, 1)) for m in (1, 3, 4, 6, 7, 9, 10, 12)],
                         [1, 1, 2, 2, 3, 3, 4, 4])


class EvaluerLotTests(SimpleTestCase):
    def _detail(self, did, jour, montant=10000, point="p1"):
        from datetime import datetime
        planning = SimpleNamespace(date=datetime(2026, 5, jour, 12, 0))
        return SimpleNamespace(id=did, planning=planning, created_at=datetime(2026, 5, jour), point_eau_id=point,
                               point_eau=SimpleNamespace(id=point, ouvrage_id="o1") if point else None,
                               montant=Decimal(montant))

    def _lot(self, details, periodes=2):
        with mock.patch("apps.core.widget_rbf.effective_payment_counts", return_value={"p1": periodes}), \
             mock.patch.object(rbf_avance, "lignes_diamex", return_value=[]), \
             mock.patch.object(rbf_avance, "avances_en_cours", return_value=[]):
            return rbf_avance.evaluer_lot(details)

    def test_premiere_ligne_autorisee_la_suivante_du_meme_trimestre_est_un_doublon(self):
        r = self._lot([self._detail(2, 20), self._detail(1, 5)])
        self.assertTrue(r[1]["autorise"])
        self.assertFalse(r[2]["autorise"])
        self.assertFalse(ok_of(r[2])["doublon"])

    def test_ligne_sans_point_refusee(self):
        r = self._lot([self._detail(1, 5, point=None)])
        self.assertFalse(r[1]["autorise"])

    def test_ordre_independant_de_la_liste_fournie(self):
        a = self._lot([self._detail(1, 5), self._detail(2, 20)])
        b = self._lot([self._detail(2, 20), self._detail(1, 5)])
        self.assertEqual({k: v["autorise"] for k, v in a.items()}, {k: v["autorise"] for k, v in b.items()})
