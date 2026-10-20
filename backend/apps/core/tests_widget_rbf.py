from decimal import Decimal

from django.test import SimpleTestCase

from apps.core import widget_rbf

CAP = Decimal("40000")


def line(amount, year=2026, point="p1", kind="RBF"):
    return (1, kind, year, Decimal(amount), point, "1")


class WidgetRbfTests(SimpleTestCase):
    def test_totals_ignore_other_years_unknown_points_and_out_of_scope(self):
        lines = {"o1": [line(20000), line(25000), line(5000, year=2025), line(9000, point=""),
                        line(7000, point="p2")]}
        self.assertEqual(widget_rbf.totals_by_point(lines, 2026, {"p1"}), {"p1": Decimal("45000")})

    def test_over_cap_is_strictly_above_forty_thousand(self):
        over, _ = widget_rbf.classify({"p1": Decimal("40000"), "p2": Decimal("40001")}, {"p1": 9, "p2": 9}, CAP)
        self.assertEqual([i["point_id"] for i in over], ["p2"])
        self.assertEqual(over[0]["excess"], Decimal("1"))

    def test_rbf_without_effective_payment_is_flagged(self):
        _, unpaid = widget_rbf.classify({"p1": Decimal("5000")}, {}, CAP)
        self.assertEqual([(i["point_id"], i["paid"]) for i in unpaid], [("p1", 0)])

    def test_rbf_up_to_ten_thousand_per_effective_payment_is_fine(self):
        _, unpaid = widget_rbf.classify(
            {"p1": Decimal("20000"), "p2": Decimal("20001")}, {"p1": 2, "p2": 2}, CAP)
        self.assertEqual([i["point_id"] for i in unpaid], ["p2"])

    def test_one_payment_of_four_periods_justifies_forty_thousand(self):
        # Paiement unique de 4 x le tarif forfaitaire (quantité 4) : 4 périodes, 40 000 Ar de RBF justifiés.
        self.assertEqual(widget_rbf.periods_of(4), 4)
        self.assertEqual(widget_rbf.periods_of(0), 1)
        self.assertEqual(widget_rbf.periods_of(None), 1)
        _, unpaid = widget_rbf.classify(
            {"p1": Decimal("20000"), "p2": Decimal("40000"), "p3": Decimal("40001")},
            {"p1": 4, "p2": 4, "p3": 4}, CAP)
        self.assertEqual([i["point_id"] for i in unpaid], ["p3"])

    def test_sorted_by_excess_desc(self):
        over, _ = widget_rbf.classify({"a": Decimal("50000"), "b": Decimal("90000")}, {}, CAP)
        self.assertEqual([i["point_id"] for i in over], ["b", "a"])


class SplitModaliteCommuneTests(SimpleTestCase):
    def test_composite_and_plain_values(self):
        from apps.core.views_widget import _split_modalite_commune as split
        self.assertEqual(split('sans_tarif|abc'), ('sans_tarif', 'abc'))
        self.assertEqual(split('forfait|none'), ('forfait', 'none'))
        self.assertEqual(split('abc'), (None, 'abc'))
        self.assertEqual(split('inconnue|abc'), (None, 'inconnue|abc'))
        self.assertEqual(split(''), (None, ''))


class WidgetExplicationHrefTests(SimpleTestCase):
    def test_href_keeps_active_filters_only(self):
        from django.test import RequestFactory
        from apps.core.views_widget import _widget_explication_href as href

        pid = "3f2b1c9e-8a4d-4b6e-9c1a-2d7e5f0a1b34"
        request = RequestFactory().get("/", {"commune_id": "c1", "district_id": "all", "employe_id": ""})
        url = href(request, "rbf_points_sans_paiement_effectif", pid)
        self.assertEqual(url, f"/widget/explication/rbf_points_sans_paiement_effectif/{pid}/?commune_id=c1")
        bare = href(RequestFactory().get("/"), "rbf_points_depassement_plafond", pid)
        self.assertEqual(bare, f"/widget/explication/rbf_points_depassement_plafond/{pid}/")


class RbfTopTests(SimpleTestCase):
    def test_top_groups_sorts_by_excess_and_scales_bars(self):
        from apps.core.views_widget import _rbf_top

        rows = [
            {"ouvrage": "A", "excess": Decimal("10000")},
            {"ouvrage": "A", "excess": Decimal("20000")},
            {"ouvrage": "B", "excess": Decimal("15000")},
        ]
        top = _rbf_top(rows, "ouvrage")
        self.assertEqual([(g["name"], g["count"], g["pct"]) for g in top], [("A", 2, 100), ("B", 1, 50)])
        self.assertEqual(_rbf_top([], "ouvrage"), [])
