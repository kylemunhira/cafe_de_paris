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
from orders.models import Expense, FiscalApprovalStatus, KitchenStatus, Order, OrderStatus, OrderType
from orders.tax import order_receipt_tax_breakdown, split_inclusive_total
from payments.models import Currency, CurrencyRate


class OrderPayTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username="cashier", password="pass")
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.client.force_authenticate(user=self.user)
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
        self.assertEqual(self.order.payment_method, "cash")
        self.assertEqual(self.order.payments.count(), 1)
        payment = self.order.payments.get()
        self.assertEqual(payment.method, "cash")
        self.assertEqual(payment.amount, Decimal("7.00"))

    def test_split_payment_on_non_fiscal_branch(self):
        response = self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {
                "payment_method": "multi",
                "payments": [
                    {"currency_id": self.usd.id, "amount": "5.00"},
                    {"currency_id": self.zwl.id, "amount": "51.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertEqual(self.order.payment_method, "multi")
        self.assertEqual(self.order.amount_paid, Decimal("7.00"))
        amounts = {
            payment.currency_id: payment.amount for payment in self.order.payments.all()
        }
        self.assertEqual(amounts, {
            self.usd.id: Decimal("5.00"),
            self.zwl.id: Decimal("51.00"),
        })
        self.assertEqual(len(response.data["payments"]), 2)

    def test_split_payment_rejects_underpayment(self):
        response = self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {
                "payments": [
                    {"currency_id": self.usd.id, "amount": "5.00"},
                    {"currency_id": self.zwl.id, "amount": "25.50"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.OPEN)

    def test_split_payment_allows_overpayment_as_change(self):
        response = self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {
                "payments": [
                    {"currency_id": self.usd.id, "amount": "10.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertEqual(self.order.amount_paid, Decimal("10.00"))
        self.assertEqual(self.order.payments.get().amount, Decimal("7.00"))
        self.assertEqual(response.data.get("change_given"), "3.00")
        self.assertEqual(response.data.get("change_given_base"), "3.00")

    def test_split_payment_blocked_on_fiscal_branch(self):
        self.branch.fiscalization_enabled = True
        self.branch.save(update_fields=["fiscalization_enabled"])
        response = self.client.post(
            f"/api/orders/{self.order.id}/pay/",
            {
                "payments": [
                    {"currency_id": self.usd.id, "amount": "5.00"},
                    {"currency_id": self.zwl.id, "amount": "51.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("non-fiscal", response.data["detail"].lower())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.OPEN)

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


class KitchenStationFilterTests(TestCase):
    def setUp(self):
        from accounts.models import StaffProfile, StaffRole
        from catalog.models import PosStation
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        self.bar_category = ProductCategory.objects.create(
            name="Drinks",
            pos_station=PosStation.BAR,
        )
        self.kitchen_category = ProductCategory.objects.create(
            name="Mains",
            pos_station=PosStation.KITCHEN,
        )
        self.bar_product = Product.objects.create(
            name="Beer",
            category=self.bar_category,
            selling_price=Decimal("4.00"),
        )
        self.kitchen_product = Product.objects.create(
            name="Burger",
            category=self.kitchen_category,
            selling_price=Decimal("8.00"),
        )
        self.mixed_order = Order.objects.create(branch=self.branch, status=OrderStatus.OPEN)
        self.mixed_order.items.create(
            product=self.bar_product,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        self.mixed_order.items.create(
            product=self.kitchen_product,
            quantity=Decimal("1"),
            price=Decimal("8.00"),
        )
        self.mixed_order.recalculate_total()

        self.kitchen_user = User.objects.create_user(username="kitchenchef", password="pass")
        StaffProfile.objects.create(
            user=self.kitchen_user,
            branch=self.branch,
            role=StaffRole.STAFF,
            kitchen_station=PosStation.KITCHEN,
        )
        self.bar_user = User.objects.create_user(username="barstaff", password="pass")
        StaffProfile.objects.create(
            user=self.bar_user,
            branch=self.branch,
            role=StaffRole.STAFF,
            kitchen_station=PosStation.BAR,
        )

    def test_kitchen_staff_only_sees_kitchen_items(self):
        self.client.force_authenticate(user=self.kitchen_user)
        response = self.client.get("/api/orders/?status=open")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        item_names = [item["product_name"] for item in results[0]["items"]]
        self.assertEqual(item_names, ["Burger"])

    def test_bar_staff_only_sees_bar_items(self):
        self.client.force_authenticate(user=self.bar_user)
        response = self.client.get("/api/orders/?status=open")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        item_names = [item["product_name"] for item in results[0]["items"]]
        self.assertEqual(item_names, ["Beer"])


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

    def test_order_slip_print_shows_payment_options(self):
        zwg = Currency.objects.create(code="ZWG", name="ZiG", symbol="ZiG")
        CurrencyRate.objects.create(
            currency=zwg,
            rate=Decimal("25.5"),
            effective_from="2026-06-01",
        )
        open_order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.OPEN,
            created_by=self.user,
        )
        open_order.items.create(
            product=Product.objects.get(name="Latte"),
            quantity=Decimal("1"),
            price=Decimal("20.00"),
        )
        response = self.client.get(f"/pos/order/{open_order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment options")
        self.assertContains(response, "US Dollar")
        self.assertContains(response, "ZiG")
        self.assertContains(response, "510.00")

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
        self.assertContains(response, "cafe-de-paris-logo.png")

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

    def test_day_end_api_requires_completed_stock_take(self):
        self._create_paid_order(product=self.latte, quantity=Decimal("1"))
        api = APIClient()
        api.force_authenticate(user=self.user)

        response = api.get(
            f"/api/reports/day-end/?branch={self.branch.id}&date={self.today.isoformat()}"
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["completed"])

    def test_day_end_api_returns_report(self):
        self._create_paid_order(product=self.latte, quantity=Decimal("1"))
        self._complete_daily_stock_take()
        api = APIClient()
        api.force_authenticate(user=self.user)

        response = api.get(
            f"/api/reports/day-end/?branch={self.branch.id}&date={self.today.isoformat()}&counted_{self.usd.id}=8.00"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["report"]["order_count"], 1)
        self.assertTrue(response.data["report"]["has_counted_entries"])

    def test_fiscal_day_end_rejects_mixed_currency_codes(self):
        self.branch.fiscalization_enabled = True
        self.branch.save(update_fields=["fiscalization_enabled"])
        zwg = Currency.objects.create(code="ZWG", name="ZiG Cash", symbol="ZWG")
        CurrencyRate.objects.create(
            currency=zwg,
            rate=Decimal("30"),
            effective_from="2026-01-01",
        )
        self._complete_daily_stock_take()
        api = APIClient()
        api.force_authenticate(user=self.user)

        response = api.post(
            "/api/reports/day-end/",
            {
                "branch": self.branch.id,
                "date": self.today.isoformat(),
                "counted": {
                    str(self.usd.id): "10.00",
                    str(zwg.id): "100.00",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("same currency code", response.data["detail"].lower())

    def test_fiscal_day_end_allows_same_currency_code(self):
        self.branch.fiscalization_enabled = True
        self.branch.save(update_fields=["fiscalization_enabled"])
        bank_usd = Currency.objects.create(code="USD", name="BANKUSD", symbol="USD$")
        CurrencyRate.objects.create(
            currency=bank_usd,
            rate=Decimal("1"),
            effective_from="2026-01-01",
        )
        self._complete_daily_stock_take()
        api = APIClient()
        api.force_authenticate(user=self.user)

        response = api.post(
            "/api/reports/day-end/",
            {
                "branch": self.branch.id,
                "date": self.today.isoformat(),
                "counted": {
                    str(self.usd.id): "10.00",
                    str(bank_usd.id): "5.00",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("saved"))


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


class TableOrderCombineTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username="cashier", password="pass")
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.client.force_authenticate(user=self.user)
        category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=category,
            selling_price=Decimal("3.50"),
        )
        self.latte = Product.objects.create(
            name="Latte",
            category=category,
            selling_price=Decimal("4.00"),
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

    def _create_table_order(self, table_number, product=None, quantity=Decimal("1")):
        product = product or self.product
        order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.DINE_IN,
            table_number=table_number,
            kitchen_status=KitchenStatus.READY,
        )
        order.items.create(product=product, quantity=quantity, price=product.selling_price)
        order.recalculate_total()
        return order

    def test_adding_to_occupied_table_appends_items(self):
        existing = self._create_table_order("T1")
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "order_type": OrderType.DINE_IN,
                "table_number": "T1",
                "items": [{"product_id": self.latte.id, "quantity": "2"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["id"], existing.id)
        self.assertEqual(Order.objects.filter(status=OrderStatus.OPEN).count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.items.count(), 2)
        self.assertEqual(existing.total_amount, Decimal("11.50"))
        self.assertEqual(existing.kitchen_status, KitchenStatus.PENDING)

    def test_paying_table_order_consolidates_siblings(self):
        first = self._create_table_order("T2")
        second = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.DINE_IN,
            table_number="T2",
        )
        second.items.create(product=self.latte, quantity=Decimal("1"), price=self.latte.selling_price)
        second.recalculate_total()

        response = self.client.post(
            f"/api/orders/{first.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.status, OrderStatus.PAID)
        self.assertEqual(first.total_amount, Decimal("7.50"))
        self.assertFalse(Order.objects.filter(pk=second.pk).exists())
        self.assertEqual(Order.objects.filter(status=OrderStatus.OPEN, table_number="T2").count(), 0)


class OrderCancelVoidTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username="cashier", password="pass")
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.client.force_authenticate(user=self.user)
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

    def _open_order(self):
        order = Order.objects.create(branch=self.branch)
        order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()
        return order

    def test_cancel_open_order(self):
        order = self._open_order()
        response = self.client.post(f"/api/orders/{order.id}/cancel/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertIsNotNone(order.cancelled_at)
        self.assertEqual(order.cancelled_by_id, self.user.id)

    def test_cannot_pay_cancelled_order(self):
        order = self._open_order()
        self.client.post(f"/api/orders/{order.id}/cancel/", {}, format="json")
        response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cancel_paid_order_rejected(self):
        order = self._open_order()
        self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        response = self.client.post(f"/api/orders/{order.id}/cancel/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)

    def test_void_paid_order(self):
        order = self._open_order()
        self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        response = self.client.post(f"/api/orders/{order.id}/void/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertIsNotNone(order.receipt_number)
        self.assertIsNotNone(order.paid_at)
        self.assertEqual(order.cancelled_by_id, self.user.id)

    def test_void_open_order_rejected(self):
        order = self._open_order()
        response = self.client.post(f"/api/orders/{order.id}/void/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)

    def test_void_fiscalised_order_rejected(self):
        order = self._open_order()
        self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        order.fiscal_approval_status = FiscalApprovalStatus.APPROVED
        order.save(update_fields=["fiscal_approval_status"])
        response = self.client.post(f"/api/orders/{order.id}/void/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Fiscalised", response.data["detail"])
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)

    def test_void_account_paid_order_refunds_balance(self):
        from customers.models import Customer, CustomerAccountTransactionType

        customer = Customer.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            account_balance=Decimal("20.00"),
        )
        order = Order.objects.create(branch=self.branch, customer=customer)
        order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()
        pay_response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"payment_method": "account"},
            format="json",
        )
        self.assertEqual(pay_response.status_code, 200, pay_response.data)
        customer.refresh_from_db()
        self.assertEqual(customer.account_balance, Decimal("13.00"))

        response = self.client.post(f"/api/orders/{order.id}/void/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        customer.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertEqual(customer.account_balance, Decimal("20.00"))
        self.assertTrue(
            customer.account_transactions.filter(
                transaction_type=CustomerAccountTransactionType.REFUND,
                order=order,
            ).exists()
        )

    def test_void_restores_recipe_materials(self):
        from bakery.models import Recipe
        from inventory.models import BranchInventory

        ingredients = ProductCategory.objects.create(name="Ingredients")
        beans = Product.objects.create(
            name="Coffee Beans",
            category=ingredients,
            selling_price=Decimal("0"),
        )
        Recipe.objects.create(
            product=self.product,
            ingredient=beans,
            quantity_required=Decimal("0.02"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=beans,
            quantity=Decimal("1.00"),
        )
        order = self._open_order()
        pay_response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(pay_response.status_code, 200, pay_response.data)
        stock = BranchInventory.objects.get(branch=self.branch, product=beans)
        self.assertEqual(stock.quantity, Decimal("0.96"))

        response = self.client.post(f"/api/orders/{order.id}/void/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("1.00"))


class FamilyStaffCostPriceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username="cashier2", password="pass")
        self.branch = Branch.objects.create(
            name="Cost Branch",
            code="CST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        self.client.force_authenticate(user=self.user)

        from bakery.models import Recipe
        from catalog.constants import INGREDIENTS_CATEGORY
        from customers.models import Customer, CustomerAccountType

        coffee = ProductCategory.objects.create(name="Coffee")
        ingredients = ProductCategory.objects.create(name=INGREDIENTS_CATEGORY)
        self.product = Product.objects.create(
            name="Latte",
            category=coffee,
            selling_price=Decimal("5.00"),
        )
        self.no_recipe_product = Product.objects.create(
            name="Bottled Water",
            category=coffee,
            selling_price=Decimal("1.50"),
        )
        milk = Product.objects.create(
            name="Milk",
            category=ingredients,
            selling_price=Decimal("2.00"),
        )
        Recipe.objects.create(
            product=self.product,
            ingredient=milk,
            quantity_required=Decimal("0.50"),
        )
        # recipe cost = 0.50 * 2.00 = 1.00
        self.expected_cost = Decimal("1.00")
        self.milk = milk

        from inventory.models import BranchInventory

        BranchInventory.objects.create(
            branch=self.branch,
            product=milk,
            quantity=Decimal("100.00"),
        )

        self.family = Customer.objects.create(
            first_name="Fam",
            last_name="Ily",
            account_type=CustomerAccountType.FAMILY,
            account_balance=Decimal("50.00"),
        )
        self.staff = Customer.objects.create(
            first_name="Staff",
            last_name="Member",
            account_type=CustomerAccountType.STAFF,
            account_balance=Decimal("50.00"),
        )
        self.regular = Customer.objects.create(
            first_name="Reg",
            last_name="Ular",
            account_type=CustomerAccountType.REGULAR,
            account_balance=Decimal("50.00"),
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

    def test_family_order_uses_recipe_cost(self):
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "customer": self.family.id,
                "order_type": "takeaway",
                "items": [{"product_id": self.product.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["items"][0]["price"]), self.expected_cost)
        self.assertEqual(Decimal(response.data["total_amount"]), self.expected_cost)

    def test_staff_order_uses_recipe_cost(self):
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "customer": self.staff.id,
                "order_type": "takeaway",
                "items": [{"product_id": self.product.id, "quantity": "2"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["items"][0]["price"]), self.expected_cost)
        self.assertEqual(Decimal(response.data["total_amount"]), Decimal("2.00"))

    def test_regular_customer_uses_selling_price(self):
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "customer": self.regular.id,
                "order_type": "takeaway",
                "items": [{"product_id": self.product.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["items"][0]["price"]), Decimal("5.00"))

    def test_family_no_recipe_falls_back_to_selling_price(self):
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "customer": self.family.id,
                "order_type": "takeaway",
                "items": [{"product_id": self.no_recipe_product.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["items"][0]["price"]), Decimal("1.50"))

    def test_link_family_customer_reprices_open_order(self):
        create = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "order_type": "takeaway",
                "items": [{"product_id": self.product.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        self.assertEqual(Decimal(create.data["items"][0]["price"]), Decimal("5.00"))
        order_id = create.data["id"]

        link = self.client.patch(
            f"/api/orders/{order_id}/",
            {"customer": self.family.id},
            format="json",
        )
        self.assertEqual(link.status_code, 200, link.data)
        self.assertEqual(Decimal(link.data["items"][0]["price"]), self.expected_cost)
        self.assertEqual(Decimal(link.data["total_amount"]), self.expected_cost)

        unlink = self.client.patch(
            f"/api/orders/{order_id}/",
            {"customer": None},
            format="json",
        )
        self.assertEqual(unlink.status_code, 200, unlink.data)
        self.assertEqual(Decimal(unlink.data["items"][0]["price"]), Decimal("5.00"))

    def test_account_payment_deducts_cost_total(self):
        create = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "customer": self.family.id,
                "order_type": "takeaway",
                "items": [{"product_id": self.product.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        order_id = create.data["id"]

        pay = self.client.post(
            f"/api/orders/{order_id}/pay/",
            {"payment_method": "account"},
            format="json",
        )
        self.assertEqual(pay.status_code, 200, pay.data)
        self.family.refresh_from_db()
        self.assertEqual(self.family.account_balance, Decimal("49.00"))

    def test_customer_serializer_includes_account_type(self):
        response = self.client.get(f"/api/customers/{self.family.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["account_type"], "family")
        self.assertEqual(response.data["account_type_display"], "Family")
