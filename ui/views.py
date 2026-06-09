from accounts.branch_access import (
    filter_by_branch_field,
    filter_by_branch_participation,
    user_can_access_bakery_transfers,
    user_can_access_grv,
    user_can_access_pos,
    user_can_manage_users,
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.views.generic import DetailView, TemplateView

from inventory.models import DeliveryNote
from orders.models import Order, OrderStatus
from orders.tax import get_inclusive_tax_rate, order_receipt_tax_breakdown
from payments.models import Currency


class BaseUIView(LoginRequiredMixin, TemplateView):
    active_nav = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = self.active_nav
        return context


class DashboardView(BaseUIView):
    template_name = "ui/dashboard.html"
    active_nav = "dashboard"


class POSView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/pos.html"
    active_nav = "pos"

    def test_func(self):
        return user_can_access_pos(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["inclusive_tax_rate"] = get_inclusive_tax_rate()
        return context


class OrdersView(BaseUIView):
    template_name = "ui/orders.html"
    active_nav = "orders"


class ProductsView(BaseUIView):
    template_name = "ui/products.html"
    active_nav = "products"


class BranchesView(BaseUIView):
    template_name = "ui/branches.html"
    active_nav = "branches"


class UsersView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/users.html"
    active_nav = "users"

    def test_func(self):
        return user_can_manage_users(self.request.user)


class ReportsView(BaseUIView):
    template_name = "ui/reports.html"
    active_nav = "reports"


class PaymentRatesView(BaseUIView):
    template_name = "ui/payment_rates.html"
    active_nav = "payment_rates"


class PaymentCurrencyView(BaseUIView):
    template_name = "ui/payment_currency.html"
    active_nav = "payment_currency"


class TransfersView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/transfers.html"
    active_nav = "transfers"

    def test_func(self):
        return user_can_access_bakery_transfers(self.request.user)


class GrvView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/grv.html"
    active_nav = "grv"

    def test_func(self):
        return user_can_access_grv(self.request.user)


class RecipesView(BaseUIView):
    template_name = "ui/recipes.html"
    active_nav = "recipes"


class StockTakeView(BaseUIView):
    template_name = "ui/stock_take.html"
    active_nav = "stock_take"


class DeliveryNotePrintView(LoginRequiredMixin, DetailView):
    model = DeliveryNote
    template_name = "ui/delivery_note_print.html"
    context_object_name = "note"

    def get_queryset(self):
        queryset = DeliveryNote.objects.select_related(
            "from_branch",
            "to_branch",
        ).prefetch_related("lines__product")
        return filter_by_branch_participation(queryset, self.request.user)


class PaidOrderPrintView(LoginRequiredMixin, DetailView):
    model = Order
    context_object_name = "order"

    def get_queryset(self):
        queryset = Order.objects.select_related(
            "branch",
            "customer",
            "payment_currency",
            "fiscal_receipt",
        ).prefetch_related("items__product")
        return filter_by_branch_field(queryset, self.request.user)

    def get_object(self, queryset=None):
        order = super().get_object(queryset)
        if order.status != OrderStatus.PAID:
            raise Http404("Invoice is only available for paid orders.")
        return order

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["base_currency"] = Currency.objects.filter(is_base=True).first()
        context["auto_print"] = self.request.GET.get("auto") == "1"
        context["fiscal"] = getattr(self.object, "fiscal_receipt", None)
        context["tax_breakdown"] = order_receipt_tax_breakdown(self.object)
        return context


class ReceiptPrintView(PaidOrderPrintView):
    template_name = "ui/receipt_print.html"


class InvoicePrintView(PaidOrderPrintView):
    template_name = "ui/invoice_print.html"


class InvoicesView(BaseUIView):
    template_name = "ui/invoices.html"
    active_nav = "invoices"
