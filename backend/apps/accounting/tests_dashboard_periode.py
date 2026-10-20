from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.urls import reverse

from apps.accounting.views_dashboard_periode import (
    _billing_period,
    _month_keys,
    _resolve_period,
    _stats,
)


class DashboardMultiYearPeriodTests(SimpleTestCase):
    def test_period_accepts_multiple_years(self):
        request = SimpleNamespace(GET={
            'date_debut': '2024-11-15',
            'date_fin': '2026-02-20',
        })
        start, end, _, _, error = _resolve_period(request)
        self.assertEqual(start, date(2024, 11, 15))
        self.assertEqual(end, date(2026, 2, 20))
        self.assertEqual(error, '')

    def test_month_keys_cross_year_boundary(self):
        self.assertEqual(
            _month_keys(date(2025, 11, 1), date(2026, 2, 28)),
            {(2025, 11), (2025, 12), (2026, 1), (2026, 2)},
        )

    def test_december_reading_is_billed_in_january(self):
        self.assertEqual(_billing_period(date(2025, 12, 18)), (2026, 1))

    def test_routes_are_separate_from_annual_dashboards(self):
        self.assertEqual(
            reverse('accounting:dashboard_paiements_volume_periode'),
            '/comptabilite/dashboard-paiements-volume/periode/',
        )
        self.assertEqual(
            reverse('accounting:dashboard_paiements_forfaitaire_periode'),
            '/comptabilite/dashboard-paiements-forfaitaire/periode/',
        )

    def test_stats_include_paid_water_point_count(self):
        stats = _stats([], paid_point_count=7, billed_point_count=11)
        self.assertEqual(stats['paid_point_count'], 7)
        self.assertEqual(stats['billed_point_count'], 11)
