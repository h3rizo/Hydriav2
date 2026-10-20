from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.accounting.views_dashboard_forfaitaire import _get_tranches_realisees_qs


class DashboardForfaitaireTranchesModalTests(SimpleTestCase):
    @patch('apps.accounting.views_dashboard_forfaitaire.PaiementForfaitaire.objects')
    def test_controle_annuel_compte_aussi_les_factures_non_echues(self, objects):
        queryset = MagicMock()
        objects.filter.return_value = queryset
        points_eau = [MagicMock()]

        result = _get_tranches_realisees_qs(points_eau, 2026)

        objects.filter.assert_called_once_with(
            point_eau__in=points_eau,
            date_facture__year=2026,
        )
        queryset.filter.assert_not_called()
        self.assertIs(result, queryset)

    @patch('apps.accounting.views_dashboard_forfaitaire.PaiementForfaitaire.objects')
    def test_controle_trimestriel_conserve_la_periode_sans_filtre_du_jour(self, objects):
        queryset = MagicMock()
        filtered_queryset = MagicMock()
        objects.filter.return_value = queryset
        queryset.filter.return_value = filtered_queryset
        points_eau = [MagicMock()]
        debut = date(2026, 7, 1)
        fin = date(2026, 9, 30)

        result = _get_tranches_realisees_qs(
            points_eau,
            2026,
            trimestre_debut=debut,
            trimestre_fin=fin,
        )

        objects.filter.assert_called_once_with(
            point_eau__in=points_eau,
            date_facture__year=2026,
        )
        queryset.filter.assert_called_once_with(
            date_facture__gte=debut,
            date_facture__lte=fin,
        )
        self.assertIs(result, filtered_queryset)
