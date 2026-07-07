from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "ui"

urlpatterns = [
    path(
        "login/",
        views.StaffLoginView.as_view(),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("pos/", views.POSView.as_view(), name="pos"),
    path("kitchen/", views.KitchenView.as_view(), name="kitchen"),
    path(
        "pos/order/<int:pk>/print/",
        views.OrderSlipPrintView.as_view(),
        name="order-slip-print",
    ),
    path(
        "pos/receipt/<int:pk>/print/",
        views.ReceiptPrintView.as_view(),
        name="receipt-print",
    ),
    path(
        "pos/day-end/print/",
        views.DayEndPrintView.as_view(),
        name="day-end-print",
    ),
    path("orders/", views.OrdersView.as_view(), name="orders"),
    path("invoices/", views.InvoicesView.as_view(), name="invoices"),
    path("receipts/", views.ReceiptsView.as_view(), name="receipts"),
    path(
        "invoices/<int:pk>/print/",
        views.InvoicePrintView.as_view(),
        name="invoice-print",
    ),
    path("products/", views.ProductsView.as_view(), name="products"),
    path("menu-addons/", views.MenuAddonsView.as_view(), name="menu-addons"),
    path("ingredients/", views.IngredientsView.as_view(), name="ingredients"),
    path("product-categories/", views.ProductCategoriesView.as_view(), name="product-categories"),
    path("bakery-products/", views.BakeryProductsView.as_view(), name="bakery-products"),
    path("branches/", views.BranchesView.as_view(), name="branches"),
    path("transfers/", views.TransfersView.as_view(), name="transfers"),
    path("bakery-production/", views.BakeryProductionView.as_view(), name="bakery-production"),
    path("stores-transfers/", views.StoresTransfersView.as_view(), name="stores-transfers"),
    path("grv/", views.GrvView.as_view(), name="grv"),
    path("recipes/", views.RecipesView.as_view(), name="recipes"),
    path("stock-take/", views.StockTakeView.as_view(), name="stock-take"),
    path("expenses/", views.ExpensesView.as_view(), name="expenses"),
    path("customers/", views.CustomersView.as_view(), name="customers"),
    path("customer-accounts/", views.CustomerAccountsView.as_view(), name="customer-accounts"),
    path(
        "customer-accounts/transaction/<int:pk>/print/",
        views.CustomerAccountTransactionPrintView.as_view(),
        name="customer-statement-print",
    ),
    path(
        "customer-accounts/<int:pk>/statement/print/",
        views.CustomerFullStatementPrintView.as_view(),
        name="customer-full-statement-print",
    ),
    path("suppliers/", views.SuppliersView.as_view(), name="suppliers"),
    path("purchase-orders/", views.PurchaseOrdersView.as_view(), name="purchase-orders"),
    path(
        "transfers/delivery-note/<int:pk>/print/",
        views.DeliveryNotePrintView.as_view(),
        name="delivery-note-print",
    ),
    path(
        "transfers/invoice/<int:pk>/print/",
        views.TransferInvoicePrintView.as_view(),
        name="transfer-invoice-print",
    ),
    path("users/", views.UsersView.as_view(), name="users"),
    path("reports/", views.ReportsView.as_view(), name="reports"),
    path("reports/vat/", views.VATReportView.as_view(), name="vat-report"),
    path(
        "reports/ingredients/",
        views.IngredientReportView.as_view(),
        name="ingredient-report",
    ),
    path(
        "reports/ingredient-usage/",
        views.IngredientUsageReportView.as_view(),
        name="ingredient-usage-report",
    ),
    path(
        "reports/suppliers/",
        views.SupplierStatementView.as_view(),
        name="supplier-statement",
    ),
    path(
        "suppliers/<int:pk>/statement/print/",
        views.SupplierStatementPrintView.as_view(),
        name="supplier-statement-print",
    ),
    path("payment/rates/", views.PaymentRatesView.as_view(), name="payment-rates"),
    path(
        "payment/currency/",
        views.PaymentCurrencyView.as_view(),
        name="payment-currency",
    ),
]
