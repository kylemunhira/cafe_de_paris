from accounts.branch_access import (
    effective_branch_id,
    filter_by_branch_field,
    filter_by_branch_participation,
    user_can_access_bakery_transfers,
    user_can_access_cashier_invoices,
    user_can_access_central_invoices,
    user_can_access_fiscal_receipts,
    user_can_access_grv,
    user_can_access_kitchen,
    user_can_access_pos,
    user_can_access_stores_transfers,
    user_can_create_purchase_orders,
    user_can_manage_users,
    user_is_baker,
    user_is_branch_manager,
    user_is_cashier,
    user_is_grv_staff,
    user_is_waiter,
)
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, TemplateView
from decimal import Decimal

from branches.models import Branch
from customers.models import Customer, CustomerAccountTransaction
from customers.statement import build_customer_statement_report
from inventory.models import CentralInvoice, DeliveryNote
from inventory.services import daily_stock_take_day_end_status, day_end_stock_take_message
from orders.day_end_close import DayEndValidationError, save_day_end_close
from orders.day_end_serialization import parse_counted_by_currency
from orders.models import FiscalApprovalStatus, Order, OrderStatus, PaymentMethod
from orders.serializers import staff_display_name
from orders.tax import get_inclusive_tax_rate, order_receipt_tax_breakdown
from purchasing.models import Supplier
from purchasing.statement import build_supplier_statement_report
from payments.models import Currency
from payments.services import payment_options_for_amount


def order_change_given(order):
    """Return change in payment currency when amount tendered exceeds the bill."""
    if (
        order.amount_paid is None
        or not order.payment_currency_id
        or order.payment_method == PaymentMethod.ACCOUNT
    ):
        return None
    currency = order.payment_currency
    try:
        due = currency.convert_from_base(order.total_amount)
    except Exception:
        return None
    change = (order.amount_paid - due).quantize(Decimal("0.01"))
    return change if change > 0 else None


class CashierRestrictedAccessMixin(UserPassesTestMixin):
    """Cashiers, waiters, bakers, and GRV-only staff may only open explicitly allowed views."""

    allow_cashier = False
    allow_waiter = False
    allow_baker = False
    allow_grv_staff = False

    def test_func(self):
        user = self.request.user
        if user_is_waiter(user):
            if not self.allow_waiter:
                return False
            return self.waiter_access_allowed(user)
        if user_is_cashier(user):
            if not self.allow_cashier:
                return False
            return self.cashier_access_allowed(user)
        if user_is_baker(user):
            if not self.allow_baker:
                return False
            return self.baker_access_allowed(user)
        if user_is_grv_staff(user):
            if not self.allow_grv_staff:
                return False
            return self.grv_staff_access_allowed(user)
        return self.access_allowed(user)

    def waiter_access_allowed(self, user):
        return True

    def cashier_access_allowed(self, user):
        return True

    def baker_access_allowed(self, user):
        return True

    def grv_staff_access_allowed(self, user):
        return True

    def access_allowed(self, user):
        return True


def default_console_url(user):
    if user_is_cashier(user) or user_is_waiter(user):
        return reverse("ui:pos")
    if user_is_baker(user):
        return reverse("ui:bakery-production")
    if user_is_grv_staff(user):
        return reverse("ui:grv")
    if user_is_branch_manager(user):
        if user_can_access_pos(user):
            return reverse("ui:pos")
        return reverse("ui:orders")
    return reverse("ui:dashboard")


class BaseUIView(LoginRequiredMixin, CashierRestrictedAccessMixin, TemplateView):
    active_nav = ""

    def get_context_data(self, **kwargs):
        from accounts.branch_access import (
            get_staff_branch_id,
            user_has_global_branch_access,
        )

        context = super().get_context_data(**kwargs)
        context["active_nav"] = self.active_nav
        if self.request.user.is_authenticated:
            context["staff_branch_id"] = get_staff_branch_id(self.request.user)
            context["can_filter_any_branch"] = user_has_global_branch_access(
                self.request.user
            )
        else:
            context["staff_branch_id"] = None
            context["can_filter_any_branch"] = False
        return context


class StaffLoginView(auth_views.LoginView):
    template_name = "ui/login.html"

    def get_success_url(self):
        from accounts.branch_access import user_can_access_dashboard

        if self.request.user.is_authenticated and not user_can_access_dashboard(
            self.request.user
        ):
            return default_console_url(self.request.user)
        return super().get_success_url()


class DashboardView(BaseUIView):
    template_name = "ui/dashboard.html"
    active_nav = "dashboard"

    def dispatch(self, request, *args, **kwargs):
        from accounts.branch_access import user_can_access_dashboard

        if request.user.is_authenticated and not user_can_access_dashboard(
            request.user
        ):
            return redirect(default_console_url(request.user))
        return super().dispatch(request, *args, **kwargs)

    def access_allowed(self, user):
        from accounts.branch_access import user_can_access_dashboard

        return user_can_access_dashboard(user)


class POSView(BaseUIView):
    template_name = "ui/pos.html"
    active_nav = "pos"
    allow_cashier = True
    allow_waiter = True

    def access_allowed(self, user):
        return user_can_access_pos(user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import (
            get_staff_branch_id,
            user_can_collect_payment,
            user_can_manage_dining_tables,
            user_can_manage_fiscal_day,
        )

        context = super().get_context_data(**kwargs)
        context["inclusive_tax_rate"] = get_inclusive_tax_rate()
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        context["can_manage_fiscal_day"] = user_can_manage_fiscal_day(
            self.request.user
        )
        context["can_manage_dining_tables"] = user_can_manage_dining_tables(
            self.request.user
        )
        context["can_collect_payment"] = user_can_collect_payment(self.request.user)
        context["can_stock_take"] = user_can_collect_payment(self.request.user)
        context["can_record_customer_payment"] = user_can_collect_payment(
            self.request.user
        )
        return context


class KitchenView(BaseUIView):
    template_name = "ui/kitchen.html"
    active_nav = "kitchen"

    def access_allowed(self, user):
        return user_can_access_kitchen(user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import get_staff_branch_id, get_staff_kitchen_station

        context = super().get_context_data(**kwargs)
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        station = get_staff_kitchen_station(self.request.user)
        context["kitchen_station"] = station
        if station:
            try:
                context["kitchen_station_display"] = (
                    self.request.user.staff_profile.get_kitchen_station_display()
                )
            except Exception:
                context["kitchen_station_display"] = station.title()
        else:
            context["kitchen_station_display"] = ""
        return context


class OrdersView(BaseUIView):
    template_name = "ui/orders.html"
    active_nav = "orders"


class ProductsView(BaseUIView):
    template_name = "ui/products.html"
    active_nav = "products"

    def get_context_data(self, **kwargs):
        from catalog.constants import BAKERY_CATEGORIES

        context = super().get_context_data(**kwargs)
        context["product_list_mode"] = "menu"
        context["page_heading"] = "List Products"
        context["page_description"] = (
            "Menu items made to order at branches. "
            "Bakery goods are managed under Bakery Products and sold on POS."
        )
        context["bakery_category_names"] = sorted(BAKERY_CATEGORIES)
        return context


class MenuAddonsView(BaseUIView):
    template_name = "ui/menu_addons.html"
    active_nav = "menu_addons"


class IngredientsView(BaseUIView):
    template_name = "ui/ingredients.html"
    active_nav = "ingredients"


class ProductCategoriesView(BaseUIView):
    template_name = "ui/product_categories.html"
    active_nav = "product_categories"


class BakeryProductsView(BaseUIView):
    template_name = "ui/products.html"
    active_nav = "bakery_products"

    def get_context_data(self, **kwargs):
        from catalog.constants import BAKERY_CATEGORIES

        context = super().get_context_data(**kwargs)
        context["product_list_mode"] = "bakery"
        context["page_heading"] = "Bakery Products"
        context["page_description"] = (
            "Finished goods and components manufactured at the central bakery."
        )
        context["bakery_category_names"] = sorted(BAKERY_CATEGORIES)
        return context


class BranchesView(BaseUIView):
    template_name = "ui/branches.html"
    active_nav = "branches"


class UsersView(BaseUIView):
    template_name = "ui/users.html"
    active_nav = "users"

    def access_allowed(self, user):
        return user_can_manage_users(user)


class ReportsView(BaseUIView):
    template_name = "ui/reports.html"
    active_nav = "reports"

    def access_allowed(self, user):
        return user_can_access_pos(user)


class DayEndReportPageView(BaseUIView):
    template_name = "ui/day_end_report.html"
    active_nav = "day_end_report"

    def access_allowed(self, user):
        return user_can_access_pos(user)


class VATReportView(BaseUIView):
    template_name = "ui/vat_report.html"
    active_nav = "vat_report"

    def access_allowed(self, user):
        return user_can_access_fiscal_receipts(user)


class IngredientReportView(BaseUIView):
    template_name = "ui/ingredient_report.html"
    active_nav = "ingredient_report"


class IngredientUsageReportView(BaseUIView):
    template_name = "ui/ingredient_usage_report.html"
    active_nav = "ingredient_usage_report"


class SupplierStatementView(BaseUIView):
    template_name = "ui/supplier_statement.html"
    active_nav = "supplier_statement"

    def access_allowed(self, user):
        return user_can_create_purchase_orders(user)

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


class TransfersView(BaseUIView):
    template_name = "ui/transfers.html"
    active_nav = "transfers"
    allow_baker = True

    def baker_access_allowed(self, user):
        return user_can_access_bakery_transfers(user)

    def access_allowed(self, user):
        return user_can_access_bakery_transfers(user)


class BakeryProductionView(BaseUIView):
    template_name = "ui/bakery_production.html"
    active_nav = "bakery_production"
    allow_baker = True

    def baker_access_allowed(self, user):
        return user_can_access_bakery_transfers(user)

    def access_allowed(self, user):
        return user_can_access_bakery_transfers(user)


class StoresTransfersView(BaseUIView):
    template_name = "ui/stores_transfers.html"
    active_nav = "stores_transfers"

    def access_allowed(self, user):
        return user_can_access_stores_transfers(user)


class CentralInvoicesView(BaseUIView):
    template_name = "ui/central_invoices.html"
    active_nav = "central_invoices"

    def access_allowed(self, user):
        return user_can_access_central_invoices(user)


class GrvView(BaseUIView):
    template_name = "ui/grv.html"
    active_nav = "grv"
    allow_grv_staff = True

    def grv_staff_access_allowed(self, user):
        return user_can_access_grv(user)

    def access_allowed(self, user):
        return user_can_access_grv(user)


class RecipesView(BaseUIView):
    template_name = "ui/recipes.html"
    active_nav = "recipes"


class StockTakeView(BaseUIView):
    template_name = "ui/stock_take.html"
    active_nav = "stock_take"
    allow_cashier = True
    allow_baker = True

    def access_allowed(self, user):
        from accounts.branch_access import user_can_access_management_console

        return user_can_access_management_console(user)

    def cashier_access_allowed(self, user):
        return user_can_access_pos(user)

    def baker_access_allowed(self, user):
        return user_can_access_bakery_transfers(user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import (
            get_staff_branch_id,
            user_has_global_branch_access,
        )

        context = super().get_context_data(**kwargs)
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        context["can_filter_any_branch"] = user_has_global_branch_access(
            self.request.user
        )
        return context


class StockAdjustView(BaseUIView):
    template_name = "ui/stock_adjust.html"
    active_nav = "stock_adjust"

    def access_allowed(self, user):
        from accounts.branch_access import user_can_access_management_console

        return user_can_access_management_console(user)

    def get_context_data(self, **kwargs):
        from catalog.constants import BAKERY_SELLABLE_CATEGORIES

        context = super().get_context_data(**kwargs)
        context["bakery_sellable_categories"] = sorted(BAKERY_SELLABLE_CATEGORIES)
        return context


class CustomersView(BaseUIView):
    template_name = "ui/customers.html"
    active_nav = "customers"

    def access_allowed(self, user):
        return user_can_access_pos(user)


class CustomerAccountsView(BaseUIView):
    template_name = "ui/customer_accounts.html"
    active_nav = "customer_accounts"
    allow_cashier = True

    def access_allowed(self, user):
        return user_can_access_pos(user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import get_staff_branch_id

        context = super().get_context_data(**kwargs)
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        return context


class CustomerAccountTransactionPrintView(
    CashierRestrictedAccessMixin, LoginRequiredMixin, DetailView
):
    model = CustomerAccountTransaction
    template_name = "ui/customer_statement_print.html"
    context_object_name = "transaction"
    allow_cashier = True

    def access_allowed(self, user):
        return user_can_access_pos(user)

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


class CustomerFullStatementPrintView(
    CashierRestrictedAccessMixin, LoginRequiredMixin, DetailView
):
    model = Customer
    template_name = "ui/customer_statement_print.html"
    context_object_name = "customer"
    allow_cashier = True

    def access_allowed(self, user):
        return user_can_access_pos(user)

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


class SupplierStatementPrintView(
    CashierRestrictedAccessMixin, LoginRequiredMixin, DetailView
):
    model = Supplier
    template_name = "ui/supplier_statement_print.html"
    context_object_name = "supplier"

    def access_allowed(self, user):
        from accounts.branch_access import user_can_manage_suppliers

        return user_can_create_purchase_orders(
            user
        ) or user_can_manage_suppliers(user)

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


class SuppliersView(BaseUIView):
    template_name = "ui/suppliers.html"
    active_nav = "suppliers"

    def access_allowed(self, user):
        from accounts.branch_access import user_can_manage_suppliers

        return user_can_manage_suppliers(user)


class PurchaseOrdersView(BaseUIView):
    template_name = "ui/purchase_orders.html"
    active_nav = "purchase_orders"

    def access_allowed(self, user):
        from accounts.branch_access import user_can_create_purchase_orders

        return user_can_create_purchase_orders(user)

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
        from orders.tax import get_inclusive_tax_rate

        context["inclusive_tax_rate"] = get_inclusive_tax_rate()
        return context


class DeliveryNotePrintView(CashierRestrictedAccessMixin, LoginRequiredMixin, DetailView):
    model = DeliveryNote
    template_name = "ui/delivery_note_print.html"
    context_object_name = "note"
    allow_baker = True
    allow_grv_staff = True

    def baker_access_allowed(self, user):
        return user_can_access_bakery_transfers(user)

    def grv_staff_access_allowed(self, user):
        return user_can_access_grv(user)

    def get_queryset(self):
        queryset = DeliveryNote.objects.select_related(
            "from_branch",
            "to_branch",
        ).prefetch_related("lines__product")
        return filter_by_branch_participation(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_80mm"] = (
            self.object.from_branch.branch_type == "bakery"
            and self.request.GET.get("paper") == "80mm"
        )
        return context


class TransferInvoicePrintView(CashierRestrictedAccessMixin, LoginRequiredMixin, DetailView):
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


class CentralInvoicePrintView(CashierRestrictedAccessMixin, LoginRequiredMixin, DetailView):
    model = CentralInvoice
    template_name = "ui/central_invoice_print.html"
    context_object_name = "invoice"

    def get_queryset(self):
        queryset = CentralInvoice.objects.select_related(
            "from_branch",
            "customer",
            "paid_by",
        ).prefetch_related("lines__product")
        return filter_by_branch_field(queryset, self.request.user, branch_field="from_branch")

    def get_context_data(self, **kwargs):
        from payments.models import Currency

        context = super().get_context_data(**kwargs)
        context["base_currency"] = Currency.objects.filter(is_base=True).first()
        return context


class PaidOrderPrintView(CashierRestrictedAccessMixin, LoginRequiredMixin, DetailView):
    model = Order
    context_object_name = "order"
    allow_cashier = True

    def get_queryset(self):
        queryset = Order.objects.select_related(
            "branch",
            "customer",
            "payment_currency",
            "fiscal_receipt",
            "created_by",
            "paid_by",
        ).prefetch_related("items__product", "payments__currency")
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
        context["payment_options"] = payment_options_for_amount(
            context["tax_breakdown"]["total"]
        )
        context["change_given"] = order_change_given(self.object)
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


class OrderSlipPrintView(CashierRestrictedAccessMixin, LoginRequiredMixin, DetailView):
    model = Order
    template_name = "ui/order_slip_print.html"
    context_object_name = "order"
    allow_cashier = True

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
        context["payment_options"] = payment_options_for_amount(
            context["tax_breakdown"]["total"]
        )
        context["salesperson_name"] = staff_display_name(self.object.created_by)
        return context


class ReceiptPrintView(PaidOrderPrintView):
    template_name = "ui/receipt_print.html"


class DayEndPrintView(CashierRestrictedAccessMixin, LoginRequiredMixin, TemplateView):
    template_name = "ui/day_end_print.html"
    allow_cashier = True

    def access_allowed(self, user):
        from accounts.branch_access import user_can_collect_payment

        return user_can_collect_payment(user)

    def cashier_access_allowed(self, user):
        from accounts.branch_access import user_can_collect_payment

        return user_can_collect_payment(user)

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

    def get(self, request, *args, **kwargs):
        branch = self.get_branch()
        report_date = request.GET.get("date") or timezone.localdate().isoformat()
        status_info = daily_stock_take_day_end_status(branch, report_date)
        if not status_info["completed"]:
            return render(
                request,
                "ui/day_end_blocked.html",
                {
                    "branch": branch,
                    "count_date": report_date,
                    "draft_in_progress": status_info["draft_in_progress"],
                    "message": day_end_stock_take_message(
                        branch,
                        report_date,
                        completed=False,
                        draft_in_progress=status_info["draft_in_progress"],
                    ),
                },
                status=403,
            )
        try:
            from orders.day_end_close import validate_fiscal_counted_currencies

            validate_fiscal_counted_currencies(
                branch, parse_counted_by_currency(request.GET)
            )
        except DayEndValidationError as exc:
            return HttpResponseBadRequest(str(exc))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        branch = self.get_branch()
        report_date = self.request.GET.get("date") or None
        counted_by_currency = parse_counted_by_currency(self.request.GET)
        close, report = save_day_end_close(
            branch,
            report_date,
            counted_by_currency=counted_by_currency,
            user=self.request.user,
        )
        context["branch"] = branch
        context["report"] = report
        context["day_end_close"] = close
        context["base_currency"] = Currency.objects.filter(is_base=True).first()
        context["printed_at"] = timezone.now()
        context["auto_print"] = self.request.GET.get("auto") == "1"
        return context


class InvoicePrintView(PaidOrderPrintView):
    template_name = "ui/invoice_print.html"

    def cashier_access_allowed(self, user):
        return user_can_access_cashier_invoices(user)


class InvoicesView(BaseUIView):
    template_name = "ui/invoices.html"
    active_nav = "invoices"
    allow_cashier = True

    def cashier_access_allowed(self, user):
        return user_can_access_cashier_invoices(user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import user_can_approve_fiscal_receipt

        context = super().get_context_data(**kwargs)
        context["can_approve_fiscal_receipt"] = user_can_approve_fiscal_receipt(
            self.request.user
        )
        return context


class ReceiptsView(BaseUIView):
    template_name = "ui/receipts.html"
    active_nav = "receipts"
    allow_cashier = True

    def cashier_access_allowed(self, user):
        return user_can_access_fiscal_receipts(user)

    def access_allowed(self, user):
        return user_can_access_fiscal_receipts(user)


class ExpensesView(BaseUIView):
    template_name = "ui/expenses.html"
    active_nav = "expenses"

    def access_allowed(self, user):
        return user_can_access_pos(user)

    def get_context_data(self, **kwargs):
        from accounts.branch_access import get_staff_branch_id

        context = super().get_context_data(**kwargs)
        context["staff_branch_id"] = get_staff_branch_id(self.request.user)
        return context
