from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "ui"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="ui/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("pos/", views.POSView.as_view(), name="pos"),
    path("kitchen/", views.KitchenView.as_view(), name="kitchen"),
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
    path(
        "invoices/<int:pk>/print/",
        views.InvoicePrintView.as_view(),
        name="invoice-print",
    ),
    path("products/", views.ProductsView.as_view(), name="products"),
    path("ingredients/", views.IngredientsView.as_view(), name="ingredients"),
    path("branches/", views.BranchesView.as_view(), name="branches"),
    path("transfers/", views.TransfersView.as_view(), name="transfers"),
    path("grv/", views.GrvView.as_view(), name="grv"),
    path("recipes/", views.RecipesView.as_view(), name="recipes"),
    path("stock-take/", views.StockTakeView.as_view(), name="stock-take"),
    path("expenses/", views.ExpensesView.as_view(), name="expenses"),
    path("suppliers/", views.SuppliersView.as_view(), name="suppliers"),
    path("purchase-orders/", views.PurchaseOrdersView.as_view(), name="purchase-orders"),
    path(
        "transfers/delivery-note/<int:pk>/print/",
        views.DeliveryNotePrintView.as_view(),
        name="delivery-note-print",
    ),
    path("users/", views.UsersView.as_view(), name="users"),
    path("reports/", views.ReportsView.as_view(), name="reports"),
    path("payment/rates/", views.PaymentRatesView.as_view(), name="payment-rates"),
    path(
        "payment/currency/",
        views.PaymentCurrencyView.as_view(),
        name="payment-currency",
    ),
]
