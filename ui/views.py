from accounts.branch_access import (
    effective_branch_id,
    filter_by_branch_field,
    filter_by_branch_participation,
    user_can_access_bakery_transfers,
    user_can_access_fiscal_receipts,
    user_can_access_grv,
    user_can_access_kitchen,
    user_can_access_pos,
    user_can_access_stores_transfers,
    user_can_create_purchase_orders,
    user_can_manage_users,
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.utils import timezone
from django.views.generic import DetailView, TemplateView

from branches.models import Branch
from customers.models import Customer, CustomerAccountTransaction
from customers.statement import build_customer_statement_report
from inventory.models import DeliveryNote
from orders.day_end import build_day_end_report
from orders.models import FiscalApprovalStatus, Order, OrderStatus, PaymentMethod
from orders.serializers import staff_display_name
from orders.tax import get_inclusive_tax_rate, order_receipt_tax_breakdown
from purchasing.models import Supplier
from purchasing.statement import build_supplier_statement_report
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
        from accounts.branch_access import get_staff_branch_id

        context = super().get_context_data(**kwargs)
        context["inclusive_tax_rate"] = get_inclusive_tax_rate()
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        return context


class KitchenView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/kitchen.html"
    active_nav = "kitchen"

    def test_func(self):
        return user_can_access_kitchen(self.request.user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import get_staff_branch_id

        context = super().get_context_data(**kwargs)
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        return context


class OrdersView(BaseUIView):
    template_name = "ui/orders.html"
    active_nav = "orders"


class ProductsView(BaseUIView):
    template_name = "ui/products.html"
    active_nav = "products"


class IngredientsView(BaseUIView):
    template_name = "ui/ingredients.html"
    active_nav = "ingredients"


class BranchesView(BaseUIView):
    template_name = "ui/branches.html"
    active_nav = "branches"


class UsersView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/users.html"
    active_nav = "users"

    def test_func(self):
        return user_can_manage_users(self.request.user)


class ReportsView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/reports.html"
    active_nav = "reports"

    def test_func(self):
        return user_can_access_pos(self.request.user)


class VATReportView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/vat_report.html"
    active_nav = "vat_report"

    def test_func(self):
        return user_can_access_fiscal_receipts(self.request.user)


class SupplierStatementView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/supplier_statement.html"
    active_nav = "supplier_statement"

    def test_func(self):
        return user_can_create_purchase_orders(self.request.user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import (
            get_staff_branch_id,
            user_has_global_branch_access,
        )

        context = super().get_context_data(**kwargs)
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        context["can_filter_any_branch"] = user_has_global_branch_access(self.request.user)
        return context


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


class BakeryProductionView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/bakery_production.html"
    active_nav = "bakery_production"

    def test_func(self):
        return user_can_access_bakery_transfers(self.request.user)


class StoresTransfersView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/stores_transfers.html"
    active_nav = "stores_transfers"

    def test_func(self):
        return user_can_access_stores_transfers(self.request.user)


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


class CustomersView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/customers.html"
    active_nav = "customers"

    def test_func(self):
        return user_can_access_pos(self.request.user)


class CustomerAccountsView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/customer_accounts.html"
    active_nav = "customer_accounts"

    def test_func(self):
        return user_can_access_pos(self.request.user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import get_staff_branch_id

        context = super().get_context_data(**kwargs)
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        return context


class CustomerAccountTransactionPrintView(UserPassesTestMixin, LoginRequiredMixin, DetailView):
    model = CustomerAccountTransaction
    template_name = "ui/customer_statement_print.html"
    context_object_name = "transaction"

    def test_func(self):
        return user_can_access_pos(self.request.user)

    def get_queryset(self):
        return CustomerAccountTransaction.objects.select_related(
            "customer",
            "branch",
            "currency",
            "order",
            "recorded_by",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        txn = self.object
        context["single"] = True
        context["customer"] = txn.customer
        context["branch"] = txn.branch
        context["base_currency"] = Currency.objects.filter(is_base=True).first()
        context["printed_at"] = timezone.now()
        context["recorded_by_name"] = staff_display_name(txn.recorded_by)
        context["auto_print"] = self.request.GET.get("auto") == "1"
        context["return_url"] = self.request.GET.get("return") or ""
        return context


class CustomerFullStatementPrintView(UserPassesTestMixin, LoginRequiredMixin, DetailView):
    model = Customer
    template_name = "ui/customer_statement_print.html"
    context_object_name = "customer"

    def test_func(self):
        return user_can_access_pos(self.request.user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import get_staff_branch_id

        context = super().get_context_data(**kwargs)
        customer = self.object
        branch_id = get_staff_branch_id(self.request.user)
        branch = Branch.objects.filter(pk=branch_id).first() if branch_id else None
        if branch is None:
            latest = customer.account_transactions.select_related("branch").first()
            branch = latest.branch if latest else Branch.objects.filter(is_active=True).first()

        all_time = self.request.GET.get("all") == "1"
        try:
            statement = build_customer_statement_report(
                customer,
                from_date=self.request.GET.get("from"),
                to_date=self.request.GET.get("to"),
                branch_id=branch_id,
                all_time=all_time,
            )
        except ValueError as exc:
            raise Http404(str(exc)) from exc

        context["single"] = False
        context["branch"] = branch
        context["statement"] = statement
        context["transactions"] = statement["transactions"]
        context["opening_balance"] = statement["opening_balance"]
        context["closing_balance"] = statement["closing_balance"]
        context["total_credits"] = statement["total_credits"]
        context["total_debits"] = statement["total_debits"]
        context["statement_period"] = statement["period"]
        if statement["period"]["from"]:
            from datetime import date

            context["period_from"] = date.fromisoformat(statement["period"]["from"])
            context["period_to"] = date.fromisoformat(statement["period"]["to"])
        else:
            context["period_from"] = None
            context["period_to"] = None
        context["base_currency"] = Currency.objects.filter(is_base=True).first()
        context["printed_at"] = timezone.now()
        context["auto_print"] = self.request.GET.get("auto") == "1"
        context["return_url"] = self.request.GET.get("return") or ""
        return context


class SupplierStatementPrintView(UserPassesTestMixin, LoginRequiredMixin, DetailView):
    model = Supplier
    template_name = "ui/supplier_statement_print.html"
    context_object_name = "supplier"

    def test_func(self):
        from accounts.branch_access import user_can_manage_suppliers

        return user_can_create_purchase_orders(
            self.request.user
        ) or user_can_manage_suppliers(self.request.user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import get_staff_branch_id

        context = super().get_context_data(**kwargs)
        supplier = self.object
        branch_id = get_staff_branch_id(self.request.user) or self.request.GET.get("branch")
        branch = Branch.objects.filter(pk=branch_id).first() if branch_id else None
        if branch is None:
            latest = supplier.purchase_orders.select_related("branch").first()
            branch = latest.branch if latest else Branch.objects.filter(is_active=True).first()

        all_time = self.request.GET.get("all") == "1"
        try:
            statement = build_supplier_statement_report(
                supplier,
                from_date=self.request.GET.get("from"),
                to_date=self.request.GET.get("to"),
                branch_id=branch_id,
                all_time=all_time,
            )
        except ValueError as exc:
            raise Http404(str(exc)) from exc

        context["branch"] = branch
        context["statement"] = statement
        context["purchases"] = statement["purchases"]
        context["opening_spend"] = statement["opening_spend"]
        context["period_spend"] = statement["period_spend"]
        context["closing_spend"] = statement["closing_spend"]
        context["all_time_spend"] = statement["all_time_spend"]
        context["statement_period"] = statement["period"]
        if statement["period"]["from"]:
            from datetime import date

            context["period_from"] = date.fromisoformat(statement["period"]["from"])
            context["period_to"] = date.fromisoformat(statement["period"]["to"])
        else:
            context["period_from"] = None
            context["period_to"] = None
        context["printed_at"] = timezone.now()
        context["auto_print"] = self.request.GET.get("auto") == "1"
        context["return_url"] = self.request.GET.get("return") or ""
        return context


class SuppliersView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/suppliers.html"
    active_nav = "suppliers"

    def test_func(self):
        from accounts.branch_access import user_can_manage_suppliers

        return user_can_manage_suppliers(self.request.user)


class PurchaseOrdersView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/purchase_orders.html"
    active_nav = "purchase_orders"

    def test_func(self):
        from accounts.branch_access import user_can_create_purchase_orders

        return user_can_create_purchase_orders(self.request.user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import (
            get_staff_branch_id,
            user_has_global_branch_access,
        )

        context = super().get_context_data(**kwargs)
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        context["can_purchase_for_any_branch"] = user_has_global_branch_access(
            self.request.user
        )
        return context


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


class TransferInvoicePrintView(LoginRequiredMixin, DetailView):
    model = DeliveryNote
    template_name = "ui/transfer_invoice_print.html"
    context_object_name = "note"

    def get_queryset(self):
        queryset = DeliveryNote.objects.select_related(
            "from_branch",
            "to_branch",
            "paid_by",
        ).prefetch_related("lines__product")
        return filter_by_branch_participation(queryset, self.request.user)

    def get_object(self, queryset=None):
        note = super().get_object(queryset)
        if not note.invoice_number:
            raise Http404("Transfer invoice is only available for central stores dispatches.")
        return note

    def get_context_data(self, **kwargs):
        from payments.models import Currency

        context = super().get_context_data(**kwargs)
        context["base_currency"] = Currency.objects.filter(is_base=True).first()
        return context


class PaidOrderPrintView(LoginRequiredMixin, DetailView):
    model = Order
    context_object_name = "order"

    def get_queryset(self):
        queryset = Order.objects.select_related(
            "branch",
            "customer",
            "payment_currency",
            "fiscal_receipt",
            "created_by",
            "paid_by",
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
        context["is_proforma"] = (
            self.object.fiscal_approval_status == FiscalApprovalStatus.PENDING
        )
        context["tax_breakdown"] = order_receipt_tax_breakdown(self.object)
        context["salesperson_name"] = staff_display_name(
            self.object.paid_by or self.object.created_by
        )
        if self.object.payment_method == PaymentMethod.ACCOUNT:
            context["account_transaction"] = (
                CustomerAccountTransaction.objects.filter(order=self.object)
                .select_related("customer", "branch", "currency", "recorded_by")
                .first()
            )
        return context


class OrderSlipPrintView(LoginRequiredMixin, DetailView):
    model = Order
    template_name = "ui/order_slip_print.html"
    context_object_name = "order"

    def get_queryset(self):
        queryset = Order.objects.select_related(
            "branch",
            "customer",
            "created_by",
        ).prefetch_related("items__product")
        return filter_by_branch_field(queryset, self.request.user)

    def get_object(self, queryset=None):
        order = super().get_object(queryset)
        if order.status != OrderStatus.OPEN:
            raise Http404("Order ticket is only available for open orders.")
        return order

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["base_currency"] = Currency.objects.filter(is_base=True).first()
        context["auto_print"] = self.request.GET.get("auto") == "1"
        context["tax_breakdown"] = order_receipt_tax_breakdown(self.object)
        context["salesperson_name"] = staff_display_name(self.object.created_by)
        return context


class ReceiptPrintView(PaidOrderPrintView):
    template_name = "ui/receipt_print.html"


class DayEndPrintView(UserPassesTestMixin, LoginRequiredMixin, TemplateView):
    template_name = "ui/day_end_print.html"

    def test_func(self):
        return user_can_access_pos(self.request.user)

    def get_branch(self):
        requested = self.request.GET.get("branch")
        try:
            branch_id = effective_branch_id(self.request.user, requested)
        except ValueError as exc:
            raise Http404(str(exc)) from exc

        if branch_id is None:
            if not requested:
                raise Http404("Branch is required for the day-end report.")
            try:
                branch_id = int(requested)
            except (TypeError, ValueError) as exc:
                raise Http404("Invalid branch.") from exc

        branch = Branch.objects.filter(pk=branch_id, is_active=True).first()
        if not branch:
            raise Http404("Branch not found.")
        return branch

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        branch = self.get_branch()
        report_date = self.request.GET.get("date") or None
        counted_by_currency = {}
        for key, value in self.request.GET.items():
            if not key.startswith("counted_"):
                continue
            try:
                currency_id = int(key.split("counted_", 1)[1])
            except (TypeError, ValueError):
                continue
            counted_by_currency[currency_id] = value
        context["branch"] = branch
        context["report"] = build_day_end_report(
            branch,
            report_date,
            counted_by_currency=counted_by_currency,
        )
        context["base_currency"] = Currency.objects.filter(is_base=True).first()
        context["printed_at"] = timezone.now()
        context["auto_print"] = self.request.GET.get("auto") == "1"
        return context


class InvoicePrintView(PaidOrderPrintView):
    template_name = "ui/invoice_print.html"


class InvoicesView(BaseUIView):
    template_name = "ui/invoices.html"
    active_nav = "invoices"

    def get_context_data(self, **kwargs):
        from accounts.branch_access import user_can_approve_fiscal_receipt

        context = super().get_context_data(**kwargs)
        context["can_approve_fiscal_receipt"] = user_can_approve_fiscal_receipt(
            self.request.user
        )
        return context


class ReceiptsView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/receipts.html"
    active_nav = "receipts"

    def test_func(self):
        return user_can_access_fiscal_receipts(self.request.user)


class ExpensesView(UserPassesTestMixin, BaseUIView):
    template_name = "ui/expenses.html"
    active_nav = "expenses"

    def test_func(self):
        return user_can_access_pos(self.request.user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import get_staff_branch_id

        context = super().get_context_data(**kwargs)
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        return context
