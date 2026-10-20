from datetime import date, datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.accounting.views_dashboard_forfaitaire import _resolve_point_cut_state


class DashboardForfaitaireCutStateTests(SimpleTestCase):
    reference_date = date(2026, 8, 30)

    def test_latest_remise_wins_over_stale_legacy_cut_date(self):
        point = SimpleNamespace(
            datearretbranchement=datetime(2026, 3, 1, 12, 0),
        )
        latest_event = SimpleNamespace(
            type_evenement='remise',
            date_evenement=date(2026, 4, 1),
        )

        self.assertEqual(
            _resolve_point_cut_state(
                point,
                latest_event=latest_event,
                reference_date=self.reference_date,
            ),
            (False, None),
        )

    def test_latest_coupure_marks_point_as_cut(self):
        point = SimpleNamespace(datearretbranchement=None)
        latest_event = SimpleNamespace(
            type_evenement='coupure',
            date_evenement=date(2026, 5, 10),
        )

        self.assertEqual(
            _resolve_point_cut_state(
                point,
                latest_event=latest_event,
                reference_date=self.reference_date,
            ),
            (True, date(2026, 5, 10)),
        )

    def test_legacy_cut_date_is_used_only_without_events(self):
        point = SimpleNamespace(
            datearretbranchement=datetime(2026, 2, 15, 9, 0),
        )

        self.assertEqual(
            _resolve_point_cut_state(
                point,
                reference_date=self.reference_date,
            ),
            (True, date(2026, 2, 15)),
        )

    def test_future_legacy_cut_date_is_not_applied_to_reference_date(self):
        point = SimpleNamespace(
            datearretbranchement=datetime(2026, 10, 1, 9, 0),
        )

        self.assertEqual(
            _resolve_point_cut_state(
                point,
                reference_date=self.reference_date,
            ),
            (False, None),
        )
