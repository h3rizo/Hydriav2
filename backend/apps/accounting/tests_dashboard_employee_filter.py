from django.test import SimpleTestCase

from datetime import date
from unittest.mock import MagicMock, patch

from .dashboard_employee_filter import (
    ALLOWED_DASHBOARD_POSTES,
    _normalize_poste,
    calculate_water_point_score,
    get_water_point_score_gap_ids,
    is_closed_payment_month,
    resolve_dashboard_employee_filter,
    resolve_score_scope,
)


class DashboardEmployeeFilterTests(SimpleTestCase):
    def test_allowed_postes_are_normalized_without_accents_or_case(self):
        self.assertIn(_normalize_poste('Agent de Recouvrement'), ALLOWED_DASHBOARD_POSTES)
        self.assertIn(_normalize_poste('Agent de Maintenance'), ALLOWED_DASHBOARD_POSTES)
        self.assertIn(
            _normalize_poste('Agent de Recouvrement Superviseur Technique'),
            ALLOWED_DASHBOARD_POSTES,
        )

    def test_unrelated_poste_is_not_allowed(self):
        self.assertNotIn(_normalize_poste('Comptable'), ALLOWED_DASHBOARD_POSTES)

    @patch('apps.accounting.dashboard_employee_filter.EmployeOuvrages.objects.filter')
    def test_employee_choices_exclude_departed_employees(self, filter_mock):
        active_relations = MagicMock()
        active_relations.filter.return_value.select_related.return_value.order_by.return_value = []
        filter_mock.return_value = active_relations

        options, ouvrage_ids = resolve_dashboard_employee_filter({'ouvrage-1'})

        self.assertEqual(options, [])
        self.assertEqual(ouvrage_ids, {'ouvrage-1'})
        filter_mock.assert_called_once()
        self.assertTrue(
            filter_mock.call_args.kwargs['employe__date_debauchage__isnull']
        )

    @patch('apps.accounting.dashboard_employee_filter.EmployeOuvrages.objects.filter')
    def test_unknown_or_departed_selected_employee_is_ignored(self, filter_mock):
        active_relations = MagicMock()
        active_relations.filter.return_value.select_related.return_value.order_by.return_value = []
        filter_mock.return_value = active_relations

        options, ouvrage_ids = resolve_dashboard_employee_filter(
            {'ouvrage-1'},
            selected_employee_id='departed-employee',
        )

        self.assertEqual(options, [])
        self.assertEqual(ouvrage_ids, {'ouvrage-1'})

    def test_water_point_score_requires_full_payment(self):
        score = calculate_water_point_score(
            {'point-1', 'point-2', 'point-3', 'point-4'},
            {
                'point-1': {'expected': 100, 'paid': 100},
                'point-2': {'expected': 100, 'paid': 120},
                'point-3': {'expected': 100, 'paid': 99},
            },
        )

        self.assertEqual(score['points_acquis'], 2)
        self.assertEqual(score['points_max'], 4)
        self.assertEqual(score['points_ecart'], 2)
        self.assertEqual(score['pourcentage'], 50.0)

    def test_score_gap_ids_match_points_that_do_not_earn_score(self):
        gap_ids = get_water_point_score_gap_ids(
            {'point-1', 'point-2', 'point-3', 'point-4'},
            {
                'point-1': {'expected': 100, 'paid': 100},
                'point-2': {'expected': 100, 'paid': 120},
                'point-3': {'expected': 100, 'paid': 99},
            },
        )

        self.assertEqual(gap_ids, {'point-3', 'point-4'})

    def test_water_point_without_amount_due_does_not_earn_point(self):
        score = calculate_water_point_score(
            {'point-1'},
            {'point-1': {'expected': 0, 'paid': 0}},
        )

        self.assertEqual(score['points_acquis'], 0)
        self.assertEqual(score['points_max'], 1)

    def test_current_month_is_excluded_until_next_month(self):
        reference_date = date(2026, 7, 30)

        self.assertFalse(is_closed_payment_month(date(2026, 7, 1), reference_date))
        self.assertTrue(is_closed_payment_month(date(2026, 6, 30), reference_date))

    def test_score_scope_uses_employee_when_selected(self):
        scope = resolve_score_scope(
            employee_options=[{'id': 'employee-1', 'label': 'Agent Test'}],
            employee_id='employee-1',
            region_id='region-ignored',
        )

        self.assertEqual(scope['scope_label'], 'Score employé')
        self.assertEqual(scope['scope_name'], 'Agent Test')

    def test_score_scope_defaults_to_organisation(self):
        scope = resolve_score_scope(default_organisation_name='Hydria Test')

        self.assertEqual(scope['scope_label'], 'Score organisation')
        self.assertEqual(scope['scope_name'], 'Hydria Test')
