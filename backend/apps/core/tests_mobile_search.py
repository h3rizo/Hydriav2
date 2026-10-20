import json
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from apps.core import views_mobile_search
from apps.core import views_search_evolved
from apps.core.search_mobile_formatting import has_coordinates, point_type_pictogram, without_zero_values


class MobileSearchContractTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_mobile_routes_resolve(self):
        paths = (
            reverse("core:mobile_global_search"),
            reverse("core:mobile_people"),
            reverse("core:mobile_works"),
            reverse("core:mobile_work_filters"),
            reverse("core:mobile_interventions"),
            reverse("core:mobile_intervention_postpone", args=("00000000-0000-0000-0000-000000000001",)),
            reverse("core:mobile_intervention_delete", args=("00000000-0000-0000-0000-000000000001",)),
            reverse("core:mobile_detail", args=("ouvrage", "00000000-0000-0000-0000-000000000001")),
        )
        for path in paths:
            self.assertTrue(resolve(path).func)

    def test_anonymous_request_is_rejected(self):
        request = self.factory.get("/recherche/api/mobile/search/?q=eau")
        request.user = AnonymousUser()
        response = views_mobile_search.mobile_global_search(request)
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Authentification", response.content)

    def test_intervention_edit_contract_rejects_anonymous_requests(self):
        entity_id = "00000000-0000-0000-0000-000000000001"
        options_response = self.client.get(reverse("core:options_intervention_ouvrage", args=(entity_id,)))
        update_response = self.client.post(
            reverse("core:modifier_intervention_ouvrage", args=(entity_id, entity_id)),
            data=json.dumps({"date": "2026-09-01", "status": "en_cours"}),
            content_type="application/json",
        )
        self.assertEqual(options_response.status_code, 401)
        self.assertEqual(update_response.status_code, 401)

    def test_legacy_search_api_is_not_public(self):
        response = self.client.get(reverse("core:search_api"), {"q": "eau"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_planning_is_not_selected_by_default(self):
        self.assertIn("planning", views_mobile_search.SEARCH_TYPES)
        self.assertNotIn("planning", views_mobile_search.DEFAULT_TYPES)
        self.assertEqual(len(views_mobile_search.SEARCH_TYPES), 14)

    def test_page_size_is_bounded(self):
        self.assertEqual(views_mobile_search._positive_int("500", 20, 50), 50)
        self.assertEqual(views_mobile_search._positive_int("invalid", 20, 50), 20)

    def test_mobile_result_formatting(self):
        point = SimpleNamespace(latitude=-18.8, longitude=47.5)
        incomplete_point = SimpleNamespace(latitude=-18.8, longitude=None)
        self.assertTrue(has_coordinates(point))
        self.assertFalse(has_coordinates(incomplete_point))
        self.assertEqual(point_type_pictogram("Borne fontaine"), "🚰")
        self.assertEqual(point_type_pictogram("Branchement privé"), "🏠")
        self.assertEqual(point_type_pictogram("Kiosque"), "🏪")
        self.assertEqual(point_type_pictogram("BI volume"), "🚰")
        self.assertEqual(point_type_pictogram("BP"), "🏠")
        self.assertEqual(without_zero_values({"points": 3, "equipements": 0}), {"points": 3})

    def test_point_and_equipment_results_show_coordinate_availability(self):
        point = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000001",
            idxls="42",
            nomabonne="Rakoto",
            type_point_eau=SimpleNamespace(nom_type="Borne fontaine"),
            latitude=-18.8,
            longitude=47.5,
        )
        equipment = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000002",
            nom="Réservoir principal",
            type_equipement=SimpleNamespace(nom_type="Réservoir"),
            latitude=None,
            longitude=None,
        )

        point_row = views_search_evolved._serialize_search_item(point, "point_eau")
        equipment_row = views_search_evolved._serialize_search_item(equipment, "equipement")

        self.assertEqual(point_row["title"], "IDXls: 42 · Rakoto")
        self.assertIn("🚰 Borne fontaine", point_row["subtitle"])
        self.assertIn("Coordonnées: Oui", point_row["subtitle"])
        self.assertIn("Coordonnées: Non", equipment_row["subtitle"])

    @patch("apps.core.views_mobile_search._geo_for_work", return_value={"commune": "Ambato"})
    def test_mobile_work_row_uses_declared_equipment_relation(self, _geo):
        points = MagicMock()
        points.count.return_value = 4
        equipment = MagicMock()
        equipment.count.return_value = 7
        work = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000001",
            nom_ouvrage="AEP Ambato",
            type_ouvrage=SimpleNamespace(nom_type_ouvrage="AEPG"),
            pointeau_set=SimpleNamespace(all=lambda: points),
            equipements_constitutifs=equipment,
        )

        row = views_mobile_search._mobile_work_row(work)

        self.assertEqual(row["points_count"], 4)
        self.assertEqual(row["equipment_count"], 7)
        equipment.count.assert_called_once_with()

    @patch("django.db.models.query.QuerySet.count", return_value=0)
    def test_evolved_search_builds_all_fourteen_querysets(self, _count):
        request = self.factory.get(
            "/api/search/",
            {"q": "eau", "types": ",".join(views_mobile_search.SEARCH_TYPES)},
        )
        request.user = SimpleNamespace(is_authenticated=True, is_superuser=True)
        response = views_search_evolved.search_api_evolved(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(len(payload["totals_by_type"]), 14)
