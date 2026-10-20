from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from inspect import unwrap

from django.test import RequestFactory, SimpleTestCase

from .views_ouvrage_interventions import (
    _calculate_ouvrage_contribution_score,
    supprimer_intervention_ouvrage,
)


class OuvrageContributionScoreTests(SimpleTestCase):
    def test_five_points_require_a_contribution_and_no_unfinished_activity(self):
        score = _calculate_ouvrage_contribution_score([
            {"contribution_count": 2, "unfinished_count": 0},
            {"contribution_count": 1, "unfinished_count": 1},
            {"contribution_count": 0, "unfinished_count": 0},
        ])

        self.assertEqual(score["points"], 5)
        self.assertEqual(score["max_points"], 15)
        self.assertEqual(score["percentage"], 33.3)

    @patch("apps.core.views_ouvrage_interventions.is_directeur_poste", return_value=False)
    def test_delete_intervention_is_forbidden_for_non_director(self, _is_director):
        request = RequestFactory().post("/suppression/")
        request.user = SimpleNamespace(is_authenticated=True)

        response = unwrap(supprimer_intervention_ouvrage)(request, uuid4(), uuid4())

        self.assertEqual(response.status_code, 403)
