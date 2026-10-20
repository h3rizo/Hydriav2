from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.inventory import views


class ApiAdjustStockTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("apps.inventory.views.FicheStock.objects.create")
    @patch("apps.inventory.views.StockMovement.objects.create")
    @patch("apps.inventory.views._filter_stocks_by_scope")
    def test_adjust_stock_creates_fiche_stock_entry(
        self,
        mock_filter_stocks_by_scope,
        mock_stock_movement_create,
        mock_fiche_stock_create,
    ):
        stock = SimpleNamespace(
            designation=SimpleNamespace(nom="Coude mixte filete PEHD25"),
            base=SimpleNamespace(nom_base="Base test"),
            current_quantity=Decimal("10"),
            save=MagicMock(),
            utilisateur=None,
            rapproche=False,
            inventory_date=None,
        )
        mock_filter_stocks_by_scope.return_value.get.return_value = stock

        request = self.factory.post(
            "/stocks/api/adjust-stock/00000000-0000-0000-0000-000000000001/",
            data={
                "adjust_type": "add",
                "quantity": "5",
                "reference": "AJ-001",
                "notes": "",
            },
        )
        request.user = SimpleNamespace(
            is_authenticated=True,
            employe=SimpleNamespace(),
        )

        response = views.api_adjust_stock(request, "00000000-0000-0000-0000-000000000001")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(stock.current_quantity, Decimal("15"))
        stock.save.assert_called_once()
        mock_stock_movement_create.assert_called_once()
        mock_fiche_stock_create.assert_called_once_with(
            operation_date=mock_fiche_stock_create.call_args.kwargs["operation_date"],
            operation_type="ajustement",
            quantity=Decimal("5"),
            designation=stock.designation,
            base=stock.base,
            employee=request.user.employe,
            notes="Ajustement manuel: 10 -> 15",
        )

    @patch("apps.inventory.views.FicheStock.objects.create")
    @patch("apps.inventory.views.StockMovement.objects.create")
    @patch("apps.inventory.views._filter_stocks_by_scope")
    def test_adjust_stock_set_uses_delta_in_fiche_stock(
        self,
        mock_filter_stocks_by_scope,
        mock_stock_movement_create,
        mock_fiche_stock_create,
    ):
        stock = SimpleNamespace(
            designation=SimpleNamespace(nom="Adaptateur filete PVC25"),
            base=SimpleNamespace(nom_base="Base test"),
            current_quantity=Decimal("10"),
            save=MagicMock(),
            utilisateur=None,
            rapproche=False,
            inventory_date=None,
        )
        mock_filter_stocks_by_scope.return_value.get.return_value = stock

        request = self.factory.post(
            "/stocks/api/adjust-stock/00000000-0000-0000-0000-000000000001/",
            data={
                "adjust_type": "set",
                "quantity": "3",
                "reference": "AJ-SET-001",
                "notes": "",
            },
        )
        request.user = SimpleNamespace(
            is_authenticated=True,
            employe=SimpleNamespace(),
        )

        response = views.api_adjust_stock(request, "00000000-0000-0000-0000-000000000001")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(stock.current_quantity, Decimal("3"))
        stock.save.assert_called_once()
        mock_stock_movement_create.assert_called_once_with(
            designation=stock.designation,
            base=stock.base,
            movement_type="ajustement",
            quantity=Decimal("-7"),
            movement_date=mock_stock_movement_create.call_args.kwargs["movement_date"],
            reference="AJ-SET-001",
            notes="Ajustement manuel: 10 -> 3",
        )
        mock_fiche_stock_create.assert_called_once_with(
            operation_date=mock_fiche_stock_create.call_args.kwargs["operation_date"],
            operation_type="ajustement",
            quantity=Decimal("-7"),
            designation=stock.designation,
            base=stock.base,
            employee=request.user.employe,
            notes="Ajustement manuel: 10 -> 3",
        )


class FicheStockDeleteTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("apps.inventory.views.get_object_or_404")
    @patch("apps.inventory.views._filter_bases_by_scope")
    def test_delete_requires_directeur_permission(
        self,
        mock_filter_bases_by_scope,
        mock_get_object_or_404,
    ):
        request = self.factory.post(
            "/stocks/fiches-stock/00000000-0000-0000-0000-000000000001/delete/",
        )
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            employe=SimpleNamespace(
                poste=SimpleNamespace(nom_poste="Magasinier"),
                base_id="base-1",
            ),
        )

        response = views.fiche_stock_delete(request, "00000000-0000-0000-0000-000000000001")

        self.assertEqual(response.status_code, 403)
        mock_filter_bases_by_scope.assert_not_called()
        mock_get_object_or_404.assert_not_called()
