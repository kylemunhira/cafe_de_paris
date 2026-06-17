from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accounts.auth_views import DesktopLoginView
from accounts.views import StaffUserViewSet
from branches.views import BranchViewSet
from catalog.views import ProductCategoryViewSet, ProductViewSet
from inventory.views import (
    BranchInventoryViewSet,
    DeliveryNoteViewSet,
    StockTakeViewSet,
    StockTransferViewSet,
)
from bakery.views import RecipeViewSet
from orders.views import ExpenseViewSet, OrderViewSet
from purchasing.views import PurchaseOrderViewSet, SupplierViewSet
from payments.views import CurrencyRateViewSet, CurrencyViewSet
from reports.views import ReportExportCsvView, ReportProfitView, ReportSummaryView
from sync.views import SyncPingView, SyncPullView, SyncPushView

router = DefaultRouter()
router.register("users", StaffUserViewSet, basename="staffuser")
router.register("branches", BranchViewSet)
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
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("recipes", RecipeViewSet, basename="recipe")

urlpatterns = [
    path("auth/desktop-login/", DesktopLoginView.as_view(), name="desktop-login"),
    path("sync/ping/", SyncPingView.as_view(), name="sync-ping"),
    path("sync/pull/", SyncPullView.as_view(), name="sync-pull"),
    path("sync/push/", SyncPushView.as_view(), name="sync-push"),
    path("reports/summary/", ReportSummaryView.as_view(), name="report-summary"),
    path("reports/profit/", ReportProfitView.as_view(), name="report-profit"),
    path("reports/export-csv/", ReportExportCsvView.as_view(), name="report-export-csv"),
    path("", include(router.urls)),
]
