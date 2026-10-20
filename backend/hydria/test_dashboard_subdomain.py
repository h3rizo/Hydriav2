from django.test import SimpleTestCase, override_settings

from apps.accounting.views import _build_dashboard_fin_filter_options


@override_settings(
    ALLOWED_HOSTS=['analyses.hydria.mg', 'compta.hydria.mg'],
    ANALYSES_SUBDOMAIN_HOSTS=['analyses.hydria.mg'],
    ACCOUNTING_SUBDOMAIN_HOSTS=['compta.hydria.mg'],
    ACCOUNTING_WORKFLOW_HOSTS=['compta.hydria.mg'],
    ACCOUNTING_SUBDOMAIN_URL='https://compta.hydria.mg',
)
class AccountingDashboardSubdomainTests(SimpleTestCase):
    def test_old_analyses_url_redirects_permanently_to_compta(self):
        response = self.client.get(
            '/comptabilite/dashboard/?annee=2026&fin_category=budget',
            HTTP_HOST='analyses.hydria.mg',
        )

        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response['Location'],
            'https://compta.hydria.mg/comptabilite/dashboard/?annee=2026&fin_category=budget',
        )

    def test_dashboard_stays_on_compta_subdomain(self):
        response = self.client.get(
            '/comptabilite/dashboard/',
            HTTP_HOST='compta.hydria.mg',
        )

        self.assertFalse(
            (response.get('Location') or '').startswith(
                'https://analyses.hydria.mg/comptabilite/dashboard/'
            )
        )


class DashboardFinFilterTests(SimpleTestCase):
    def test_options_group_fin_variants_and_keep_blank_values(self):
        options, selected, matching = _build_dashboard_fin_filter_options(
            [' Budget A ', 'budget-a', None, ''],
            ['budgeta', 'sansfinancement'],
        )

        self.assertEqual(selected, ['budgeta', 'sansfinancement'])
        self.assertEqual({option['value'] for option in options}, {'budgeta', 'sansfinancement'})
        self.assertEqual(matching, [' Budget A ', 'budget-a', None, ''])
