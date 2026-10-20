from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase

from .views import _is_releve_non_recouvrable


class ReleveNonRecouvrableTests(SimpleTestCase):
    def _releve(
        self,
        *,
        numero='',
        base='',
        date_releve=date(2026, 5, 15),
        date_arret=date(2026, 6, 1),
    ):
        point_eau = SimpleNamespace(
            id='point-test',
            datearretbranchement=date_arret,
        )
        return SimpleNamespace(
            point_eau=point_eau,
            datereleve=date_releve,
            numeroDiameX=numero,
            baseDiameX=base,
        )

    def test_facture_coupee_non_pointee_est_hors_recouvrement(self):
        releve = self._releve()

        self.assertTrue(
            _is_releve_non_recouvrable(
                releve,
                {'point-test': [(date(2026, 6, 1), None)]},
            )
        )

    def test_facture_coupee_pointee_redevient_recouvrable(self):
        releve = self._releve(numero='123', base='BASE-A')

        self.assertFalse(
            _is_releve_non_recouvrable(
                releve,
                {'point-test': [(date(2026, 6, 1), None)]},
            )
        )

    def test_toute_facture_non_pointee_du_point_actuellement_coupe_est_exclue(self):
        releve = self._releve(date_releve=date(2026, 4, 15))

        self.assertTrue(
            _is_releve_non_recouvrable(
                releve,
                {'point-test': [(date(2026, 6, 1), None)]},
            )
        )

    def test_facture_redevient_recouvrable_apres_remise_en_eau(self):
        releve = self._releve(date_arret=None)

        self.assertFalse(
            _is_releve_non_recouvrable(
                releve,
                {'point-test': [(date(2026, 6, 1), date(2026, 7, 1))]},
            )
        )
