from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accounts.auth_views import DesktopLoginView, KitchenLoginView
from accounts.views import StaffUserViewSet
from branches.views import BranchViewSet, DiningTableViewSet
from catalog.views import ProductCategoryViewSet, ProductViewSet
from inventory.views import (
    BranchInventoryViewSet,
    DeliveryNoteViewSet,
    StockTakeViewSet,
    StockTransferViewSet,
)
from bakery.views import ProductionOrderViewSet, RecipeViewSet
from customers.views import CustomerViewSet
from orders.views import ExpenseViewSet, OrderViewSet
from purchasing.views import PurchaseOrderViewSet, SupplierViewSet
from payments.views import CurrencyRateViewSet, CurrencyViewSet
from reports.views import (
    ReportCustomerBalancesView,
    ReportExportCsvView,
    ReportIngredientStockView,
    ReportIngredientUsageView,
    ReportProfitView,
    ReportSummaryView,
    ReportSupplierSpendView,
    ReportVATView,
)
from sync.views import SyncPingView, SyncPullView, SyncPushView

router = DefaultRouter()
router.register("users", StaffUserViewSet, basename="staffuser")
router.register("branches", BranchViewSet)
router.register("dining-tables", DiningTableViewSet, basename="dining-table")
router.register("categories", ProductCategoryViewSet)
router.register("products", ProductViewSet)
router.register("orders", OrderViewSet)
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("currencies", CurrencyViewSet)
router.register("currency-rates", CurrencyRateViewSet, basename="currency-rate")
router.register("inventory", BranchInventoryViewSet, basename="inventory")
router.register("transfers", StockTransferViewSet, basename="transfer")
router.register("delivery-notes", DeliveryNoteViewSet, basename="delivery-note")
router.register("stock-takes", StockTakeViewSet, basename="stock-take")
router.register("customers", CustomerViewSet, basename="customer")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("recipes", RecipeViewSet, basename="recipe")
router.register("production-orders", ProductionOrderViewSet, basename="production-order")

urlpatterns = [
    path("auth/desktop-login/", DesktopLoginView.as_view(), name="desktop-login"),
    path("auth/kitchen-login/", KitchenLoginView.as_view(), name="kitchen-login"),
    path("sync/ping/", SyncPingView.as_view(), name="sync-ping"),
    path("sync/pull/", SyncPullView.as_view(), name="sync-pull"),
    path("sync/push/", SyncPushView.as_view(), name="sync-push"),
    path("reports/summary/", ReportSummaryView.as_view(), name="report-summary"),
    path("reports/profit/", ReportProfitView.as_view(), name="report-profit"),
    path("reports/export-csv/", ReportExportCsvView.as_view(), name="report-export-csv"),
    path(
        "reports/customer-balances/",
        ReportCustomerBalancesView.as_view(),
        name="report-customer-balances",
    ),
    path("reports/vat/", ReportVATView.as_view(), name="report-vat"),
    path(
        "reports/ingredient-stock/",
        ReportIngredientStockView.as_view(),
        name="report-ingredient-stock",
    ),
    path(
        "reports/ingredient-usage/",
        ReportIngredientUsageView.as_view(),
        name="report-ingredient-usage",
    ),
    path(
        "reports/supplier-spend/",
        ReportSupplierSpendView.as_view(),
        name="report-supplier-spend",
    ),
    path("", include(router.urls)),
]
