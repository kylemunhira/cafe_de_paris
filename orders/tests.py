from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import StockTake, StockTakeStatus, StockTakeType
from orders.day_end import build_day_end_report
from orders.models import Expense, FiscalApprovalStatus, KitchenStatus, Order, OrderStatus
from orders.tax import order_receipt_tax_breakdown, split_inclusive_total
from payments.models import Currency, CurrencyRate


class OrderPayTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=category,
            selling_price=Decimal("3.50"),
        )
        self.usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
        )
        CurrencyRate.objects.create(
            currency=self.usd,
            rate=Decimal("1"),
            effective_from="2026-01-01",
        )
        self.zwl = Currency.objects.create(
            code="ZWL",
            name="Zimbabwe Dollar",
            symbol="Z$",
        )
        CurrencyRate.objects.create(
            currency=self.zwl,
            rate=Decimal("25.5"),
            effective_from="2026-06-01",
        )
        self.order = Order.objects.create(branch=self.branch)
        self.order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        self.order.recalculate_total()

    def test_pay_requires_currency(self):
        response = self.client.post(f"/api/orders/{self.order.id}/pay/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_pay_in_foreign_currency(self):
        response = self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {"currency_id": self.zwl.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertEqual(self.order.payment_currency, self.zwl)
        self.assertEqual(self.order.exchange_rate, Decimal("25.5"))
        self.assertEqual(self.order.amount_paid, Decimal("178.50"))
        self.assertEqual(response.data["payment_currency_name"], "Zimbabwe Dollar")

    def test_pay_in_base_currency(self):
        response = self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.amount_paid, Decimal("7.00"))


class KitchenOrderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=category,
            selling_price=Decimal("3.50"),
        )
        self.order = Order.objects.create(branch=self.branch)
        self.order.items.create(
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )
        self.order.recalculate_total()

    def test_start_preparing_moves_order_to_preparing(self):
        response = self.client.post(
            f"/api/orders/{self.order.id}/start-preparing/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.kitchen_status, KitchenStatus.PREPARING)
        self.assertIsNotNone(self.order.kitchen_started_at)

    def test_mark_ready_after_preparing(self):
        self.order.kitchen_status = KitchenStatus.PREPARING
        self.order.save(update_fields=["kitchen_status"])
        response = self.client.post(
            f"/api/orders/{self.order.id}/mark-ready/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.kitchen_status, KitchenStatus.READY)
        self.assertIsNotNone(self.order.kitchen_ready_at)

    def test_cannot_mark_ready_from_pending(self):
        response = self.client.post(
            f"/api/orders/{self.order.id}/mark-ready/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class InclusiveTaxBreakdownTests(TestCase):
    def test_split_inclusive_total_at_15_5_percent(self):
        breakdown = split_inclusive_total(Decimal("11.55"))
        self.assertEqual(breakdown["subtotal"], Decimal("10.00"))
        self.assertEqual(breakdown["tax"], Decimal("1.55"))
        self.assertEqual(breakdown["total"], Decimal("11.55"))

    def test_order_receipt_tax_breakdown_sums_line_items(self):
        branch = Branch.objects.create(
            name="Test",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        category = ProductCategory.objects.create(name="Coffee")
        product = Product.objects.create(
            name="Latte",
            category=category,
            selling_price=Decimal("4.00"),
        )
        order = Order.objects.create(branch=branch)
        order.items.create(product=product, quantity=Decimal("2"), price=Decimal("4.00"))
        order.items.create(product=product, quantity=Decimal("1"), price=Decimal("3.55"))

        breakdown = order_receipt_tax_breakdown(order)
        self.assertEqual(breakdown["total"], Decimal("11.55"))
        self.assertEqual(breakdown["subtotal"], Decimal("10.00"))
        self.assertEqual(breakdown["tax"], Decimal("1.55"))


User = get_user_model()


class ReceiptPrintTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.branch = Branch.objects.create(
            name="Avondale",
            code="AVO",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        category = ProductCategory.objects.create(name="Coffee")
        product = Product.objects.create(
            name="Latte",
            category=category,
            selling_price=Decimal("4.00"),
        )
        currency = Currency.objects.create(name="US Dollar", symbol="$", is_base=True)
        CurrencyRate.objects.create(
            currency=currency,
            rate=Decimal("1"),
            effective_from="2026-01-01",
        )
        self.user = User.objects.create_user(
            username="cashier",
            password="pass",
            first_name="Jane",
            last_name="Cashier",
        )
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.PAID,
            payment_currency=currency,
            exchange_rate=Decimal("1"),
            amount_paid=Decimal("4.00"),
            total_amount=Decimal("4.00"),
            receipt_number="AVO0906261",
            created_by=self.user,
            paid_by=self.user,
        )
        self.order.items.create(
            product=product,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        self.client.force_login(self.user)

    def test_receipt_print_for_paid_order(self):
        response = self.client.get(f"/pos/receipt/{self.order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sales Receipt")
        self.assertContains(response, "Receipt #AVO0906261")
        self.assertContains(response, "Order #")
        self.assertContains(response, "Latte")
        self.assertContains(response, "US Dollar")
        self.assertContains(response, "Served by Jane Cashier")
        self.assertNotContains(response, "Café de Paris")
        self.assertNotContains(response, "Harare")
        self.assertNotContains(response, "Subtotal")
        self.assertNotContains(response, "Tax (")

    def test_receipt_print_shows_branch_branding_when_fiscalized(self):
        self.branch.fiscalization_enabled = True
        self.branch.save(update_fields=["fiscalization_enabled"])
        response = self.client.get(f"/pos/receipt/{self.order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Café de Paris")
        self.assertContains(response, "Harare")
        self.assertContains(response, "Subtotal")
        self.assertContains(response, "Tax (")

    def test_order_slip_print_for_open_order(self):
        open_order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.OPEN,
            created_by=self.user,
        )
        open_order.items.create(
            product=Product.objects.get(name="Latte"),
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        response = self.client.get(f"/pos/order/{open_order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Order ticket")
        self.assertContains(response, "Served by Jane Cashier")
        self.assertContains(response, "UNPAID")
        self.assertNotContains(response, "Café de Paris")
        self.assertNotContains(response, "Harare")
        self.assertNotContains(response, "Subtotal")
        self.assertNotContains(response, "Tax (")

    def test_order_slip_print_shows_branch_branding_when_fiscalized(self):
        self.branch.fiscalization_enabled = True
        self.branch.save(update_fields=["fiscalization_enabled"])
        open_order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.OPEN,
            created_by=self.user,
        )
        open_order.items.create(
            product=Product.objects.get(name="Latte"),
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        response = self.client.get(f"/pos/order/{open_order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Café de Paris")
        self.assertContains(response, "Harare")
        self.assertContains(response, "Subtotal")
        self.assertContains(response, "Tax (")

    def test_order_slip_print_not_available_for_paid_order(self):
        response = self.client.get(f"/pos/order/{self.order.id}/print/")
        self.assertEqual(response.status_code, 404)

    def test_receipt_print_not_available_for_open_order(self):
        open_order = Order.objects.create(branch=self.branch, status=OrderStatus.OPEN)
        response = self.client.get(f"/pos/receipt/{open_order.id}/print/")
        self.assertEqual(response.status_code, 404)

    def test_invoice_print_for_paid_order(self):
        response = self.client.get(f"/invoices/{self.order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tax Invoice")
        self.assertContains(response, "AVO0906261")
        self.assertContains(response, "Latte")
        self.assertContains(response, "Amount paid")

    def test_invoice_print_shows_proforma_for_pending_fiscal(self):
        self.branch.fiscalization_enabled = True
        self.branch.save(update_fields=["fiscalization_enabled"])
        self.order.fiscal_approval_status = FiscalApprovalStatus.PENDING
        self.order.save(update_fields=["fiscal_approval_status"])
        response = self.client.get(f"/invoices/{self.order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Proforma Invoice")
        self.assertNotContains(response, "Fiscal Information")

    def test_receipt_print_shows_proforma_on_thermal_for_pending_fiscal(self):
        self.branch.fiscalization_enabled = True
        self.branch.save(update_fields=["fiscalization_enabled"])
        self.order.fiscal_approval_status = FiscalApprovalStatus.PENDING
        self.order.save(update_fields=["fiscal_approval_status"])
        response = self.client.get(f"/pos/receipt/{self.order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Proforma Receipt")
        self.assertContains(response, "PROFORMA")
        self.assertContains(response, "receipt-print.css")
        self.assertContains(response, "Proforma #AVO0906261")
        self.assertNotContains(response, "Fiscal receipt")

    def test_invoice_print_not_available_for_open_order(self):
        open_order = Order.objects.create(branch=self.branch, status=OrderStatus.OPEN)
        response = self.client.get(f"/invoices/{open_order.id}/print/")
        self.assertEqual(response.status_code, 404)


class DayEndReportTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.branch = Branch.objects.create(
            name="Highland",
            code="HIG",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        category = ProductCategory.objects.create(name="Coffee")
        self.latte = Product.objects.create(
            name="Latte",
            category=category,
            selling_price=Decimal("4.00"),
        )
        self.espresso = Product.objects.create(
            name="Espresso",
            category=category,
            selling_price=Decimal("3.50"),
        )
        self.usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
        )
        CurrencyRate.objects.create(
            currency=self.usd,
            rate=Decimal("1"),
            effective_from="2026-01-01",
        )
        self.user = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self._receipt_seq = 0

    def _create_paid_order(self, *, product, quantity, order_type="takeaway"):
        self._receipt_seq += 1
        order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.PAID,
            order_type=order_type,
            payment_currency=self.usd,
            exchange_rate=Decimal("1"),
            amount_paid=product.selling_price * quantity,
            total_amount=product.selling_price * quantity,
            receipt_number=f"HIG{self.today.strftime('%d%m%y')}{self._receipt_seq}",
            paid_at=timezone.now(),
        )
        order.items.create(
            product=product,
            quantity=quantity,
            price=product.selling_price,
        )
        return order

    def _complete_daily_stock_take(self, count_date=None):
        StockTake.objects.create(
            branch=self.branch,
            stock_take_type=StockTakeType.DAILY,
            count_date=count_date or self.today,
            status=StockTakeStatus.COMPLETED,
        )

    def test_build_day_end_report_aggregates_sales(self):
        self._create_paid_order(product=self.latte, quantity=Decimal("2"))
        self._create_paid_order(product=self.espresso, quantity=Decimal("1"), order_type="dine_in")

        report = build_day_end_report(self.branch)
        self.assertEqual(report["order_count"], 2)
        self.assertEqual(report["gross_total"], Decimal("11.50"))
        self.assertEqual(len(report["products"]), 2)
        self.assertEqual(report["tax_breakdown"]["total"], Decimal("11.50"))

    def test_build_day_end_report_with_counted_cashup(self):
        self._create_paid_order(product=self.latte, quantity=Decimal("2"))
        report = build_day_end_report(
            self.branch,
            counted_by_currency={self.usd.id: "9.00"},
        )
        self.assertTrue(report["has_counted_entries"])
        self.assertEqual(len(report["cashup_rows"]), 1)
        self.assertEqual(report["cashup_rows"][0]["expected_total"], Decimal("8.00"))
        self.assertEqual(report["cashup_rows"][0]["counted_total"], Decimal("9.00"))
        self.assertEqual(report["cashup_rows"][0]["variance"], Decimal("1.00"))
        self.assertEqual(report["variance_total"], Decimal("1.00"))

    def test_build_day_end_report_with_expenses_adjusts_cashup(self):
        self._create_paid_order(product=self.latte, quantity=Decimal("2"))
        Expense.objects.create(
            branch=self.branch,
            expense_date=self.today,
            amount=Decimal("2.00"),
            currency=self.usd,
            description="Milk",
            recorded_by=self.user,
        )
        report = build_day_end_report(
            self.branch,
            counted_by_currency={self.usd.id: "6.00"},
        )
        row = report["cashup_rows"][0]
        self.assertEqual(row["expected_total"], Decimal("8.00"))
        self.assertEqual(row["expenses_total"], Decimal("2.00"))
        self.assertEqual(row["net_expected_total"], Decimal("6.00"))
        self.assertEqual(row["variance"], Decimal("0.00"))
        self.assertEqual(len(report["expenses"]), 1)
        self.assertEqual(report["expenses"][0]["description"], "Milk")

    def test_day_end_print_view(self):
        self._create_paid_order(product=self.latte, quantity=Decimal("1"))
        self._complete_daily_stock_take()

        response = self.client.get(f"/pos/day-end/print/?branch={self.branch.id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day End Report")
        self.assertContains(response, "Latte")
        self.assertContains(response, "Orders")
        self.assertContains(response, "Highland")

    def test_day_end_print_blocked_without_daily_stock_take(self):
        self._create_paid_order(product=self.latte, quantity=Decimal("1"))

        response = self.client.get(f"/pos/day-end/print/?branch={self.branch.id}")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Completed daily stock take required", status_code=403)
        self.assertContains(response, "post variances", status_code=403)


class ExpenseApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Highland",
            code="HIG",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base=True,
        )
        CurrencyRate.objects.create(
            currency=self.usd,
            rate=Decimal("1"),
            effective_from="2026-01-01",
        )
        self.user = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.client.force_authenticate(user=self.user)

    def test_create_expense(self):
        response = self.client.post(
            "/api/expenses/",
            {
                "branch": self.branch.id,
                "expense_date": "2026-06-17",
                "amount": "15.50",
                "currency": self.usd.id,
                "description": "Petty cash — sugar",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Expense.objects.count(), 1)
        expense = Expense.objects.get()
        self.assertEqual(expense.description, "Petty cash — sugar")
        self.assertIsNone(expense.supplier)
        self.assertEqual(expense.recorded_by, self.user)

    def test_create_expense_with_supplier(self):
        from purchasing.models import Supplier

        supplier = Supplier.objects.create(name="Dairy Co")
        response = self.client.post(
            "/api/expenses/",
            {
                "branch": self.branch.id,
                "expense_date": "2026-06-17",
                "amount": "25.00",
                "currency": self.usd.id,
                "description": "Milk delivery",
                "supplier": supplier.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        expense = Expense.objects.get()
        self.assertEqual(expense.supplier, supplier)
        self.assertEqual(response.data["supplier_name"], "Dairy Co")

    def test_list_expenses_filtered_by_date(self):
        Expense.objects.create(
            branch=self.branch,
            expense_date="2026-06-17",
            amount=Decimal("10.00"),
            currency=self.usd,
            description="Today",
            recorded_by=self.user,
        )
        Expense.objects.create(
            branch=self.branch,
            expense_date="2026-06-16",
            amount=Decimal("5.00"),
            currency=self.usd,
            description="Yesterday",
            recorded_by=self.user,
        )
        response = self.client.get(
            f"/api/expenses/?branch={self.branch.id}&date=2026-06-17"
        )
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["description"], "Today")

    def test_list_expenses_filtered_by_date_range(self):
        Expense.objects.create(
            branch=self.branch,
            expense_date="2026-06-15",
            amount=Decimal("5.00"),
            currency=self.usd,
            description="Old",
            recorded_by=self.user,
        )
        Expense.objects.create(
            branch=self.branch,
            expense_date="2026-06-17",
            amount=Decimal("10.00"),
            currency=self.usd,
            description="In range",
            recorded_by=self.user,
        )
        response = self.client.get(
            f"/api/expenses/?branch={self.branch.id}&from=2026-06-16&to=2026-06-17"
        )
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["description"], "In range")


class ExpensesPageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.branch = Branch.objects.create(
            name="Highland",
            code="HIG",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.user = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)

    def test_expenses_page_requires_pos_access(self):
        response = self.client.get("/expenses/")
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.user)
        response = self.client.get("/expenses/")
        self.assertEqual(response.status_code, 200)
