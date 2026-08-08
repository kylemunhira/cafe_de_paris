from decimal import Decimal
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import StockTake, StockTakeStatus, StockTakeType
from orders.day_end import build_day_end_report
from orders.models import (
    Expense,
    FiscalApprovalStatus,
    KitchenStatus,
    Order,
    OrderPayment,
    OrderStatus,
    OrderType,
    PaymentMethod,
    TenderMethod,
)
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

    def test_pos_open_unpaid_returns_all_items_for_station_staff(self):
        """POS polls status=open,unpaid and must not hide bar/kitchen lines."""
        self.client.force_authenticate(user=self.kitchen_user)
        response = self.client.get("/api/orders/?status=open,unpaid")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        item_names = sorted(item["product_name"] for item in results[0]["items"])
        self.assertEqual(item_names, ["Beer", "Burger"])

    def test_kitchen_polls_recent_cancellations_for_station(self):
        from orders.services import cancel_order

        since = timezone.now()
        bar_only = Order.objects.create(branch=self.branch, status=OrderStatus.OPEN)
        bar_only.items.create(
            product=self.bar_product,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        kitchen_only = Order.objects.create(branch=self.branch, status=OrderStatus.OPEN)
        kitchen_only.items.create(
            product=self.kitchen_product,
            quantity=Decimal("1"),
            price=Decimal("8.00"),
        )

        cancel_order(self.mixed_order)
        cancel_order(bar_only)
        cancel_order(kitchen_only)

        self.client.force_authenticate(user=self.kitchen_user)
        response = self.client.get(
            "/api/orders/?status=cancelled"
            f"&cancelled_since={quote(since.isoformat())}"
            f"&branch={self.branch.id}"
        )
        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        ids = {row["id"] for row in results}
        self.assertIn(self.mixed_order.id, ids)
        self.assertIn(kitchen_only.id, ids)
        self.assertNotIn(bar_only.id, ids)
        for row in results:
            if row["id"] == self.mixed_order.id:
                item_names = [item["product_name"] for item in row["items"]]
                self.assertEqual(item_names, ["Burger"])

    def test_bar_polls_recent_cancellations_for_station(self):
        from orders.services import cancel_order

        since = timezone.now()
        kitchen_only = Order.objects.create(branch=self.branch, status=OrderStatus.OPEN)
        kitchen_only.items.create(
            product=self.kitchen_product,
            quantity=Decimal("1"),
            price=Decimal("8.00"),
        )
        cancel_order(self.mixed_order)
        cancel_order(kitchen_only)

        self.client.force_authenticate(user=self.bar_user)
        response = self.client.get(
            "/api/orders/?status=cancelled"
            f"&cancelled_since={quote(since.isoformat())}"
            f"&branch={self.branch.id}"
        )
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.mixed_order.id, ids)
        self.assertNotIn(kitchen_only.id, ids)

    def test_unassigned_station_items_hidden_from_kitchen_stations(self):
        """No pos_station → not shown or auto-printed on kitchen/bar tablets."""
        unassigned_category = ProductCategory.objects.create(name="Kiddies")
        unassigned_product = Product.objects.create(
            name="Fish Strips",
            category=unassigned_category,
            selling_price=Decimal("6.00"),
        )
        order = Order.objects.create(branch=self.branch, status=OrderStatus.OPEN)
        order.items.create(
            product=self.kitchen_product,
            quantity=Decimal("1"),
            price=Decimal("8.00"),
        )
        order.items.create(
            product=unassigned_product,
            quantity=Decimal("1"),
            price=Decimal("6.00"),
        )
        order.recalculate_total()

        only_unassigned = Order.objects.create(branch=self.branch, status=OrderStatus.OPEN)
        only_unassigned.items.create(
            product=unassigned_product,
            quantity=Decimal("2"),
            price=Decimal("6.00"),
        )
        only_unassigned.recalculate_total()

        self.client.force_authenticate(user=self.kitchen_user)
        response = self.client.get("/api/orders/?status=open")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        ids = {row["id"] for row in results}
        self.assertIn(self.mixed_order.id, ids)
        self.assertIn(order.id, ids)
        self.assertNotIn(only_unassigned.id, ids)
        mixed_items = next(row for row in results if row["id"] == order.id)["items"]
        self.assertEqual(
            [item["product_name"] for item in mixed_items],
            ["Burger"],
        )

        self.client.force_authenticate(user=self.bar_user)
        response = self.client.get("/api/orders/?status=open")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        ids = {row["id"] for row in results}
        self.assertIn(self.mixed_order.id, ids)
        self.assertNotIn(order.id, ids)
        self.assertNotIn(only_unassigned.id, ids)

    def test_cancelled_since_excludes_older_cancellations(self):
        from orders.services import cancel_order

        cancel_order(self.mixed_order)
        since = timezone.now()
        self.client.force_authenticate(user=self.kitchen_user)
        response = self.client.get(
            "/api/orders/?status=cancelled"
            f"&cancelled_since={quote(since.isoformat())}"
            f"&branch={self.branch.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])


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

    def test_build_day_end_report_includes_account_transactions(self):
        from customers.models import Customer
        from customers.services import deposit_to_account, pay_order_from_account

        customer = Customer.objects.create(
            first_name="Jane",
            last_name="Doe",
            account_balance=Decimal("-20.00"),
        )
        deposit_to_account(
            customer=customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("10.00"),
            notes="Top up",
            recorded_by=self.user,
        )
        order = Order.objects.create(
            branch=self.branch,
            customer=customer,
            status=OrderStatus.OPEN,
        )
        order.items.create(
            product=self.latte,
            quantity=Decimal("1"),
            price=self.latte.selling_price,
        )
        order.refresh_from_db()
        pay_order_from_account(order=order, recorded_by=self.user)

        report = build_day_end_report(self.branch)
        self.assertEqual(len(report["account_transactions"]), 2)
        self.assertEqual(report["account_transactions"][0]["customer_name"], "Jane Doe")
        self.assertEqual(report["account_transactions"][0]["statement_label"], "Payment received")
        self.assertEqual(report["account_transactions"][0]["amount"], Decimal("-10.00"))
        self.assertEqual(report["account_transactions"][1]["statement_label"], "Withdrawal")
        self.assertEqual(report["account_transactions"][1]["amount"], Decimal("4.00"))
        self.assertEqual(report["account_transactions"][1]["order_id"], order.id)

    def test_build_day_end_report_groups_payments_by_currency_name(self):
        usd_cash_alt = Currency.objects.create(
            code="USD",
            name="Legacy USD Cash",
            symbol="$",
        )
        CurrencyRate.objects.create(
            currency=usd_cash_alt,
            rate=Decimal("1"),
            effective_from="2026-01-01",
        )
        order_one = self._create_paid_order(product=self.latte, quantity=Decimal("1"))
        order_two = self._create_paid_order(product=self.espresso, quantity=Decimal("1"))
        OrderPayment.objects.create(
            order=order_one,
            method=TenderMethod.CASH,
            currency=self.usd,
            amount=Decimal("4.00"),
            exchange_rate=Decimal("1"),
        )
        OrderPayment.objects.create(
            order=order_two,
            method=TenderMethod.CASH,
            currency=usd_cash_alt,
            amount=Decimal("3.50"),
            exchange_rate=Decimal("1"),
        )

        report = build_day_end_report(self.branch)
        by_name = {row["currency__name"]: row for row in report["payments_by_method"]}
        self.assertIn(self.usd.name, by_name)
        self.assertIn(usd_cash_alt.name, by_name)
        self.assertEqual(by_name[self.usd.name]["total_paid"], Decimal("4.00"))
        self.assertEqual(by_name[usd_cash_alt.name]["total_paid"], Decimal("3.50"))

    def test_day_end_print_view_includes_account_transactions(self):
        from customers.models import Customer
        from customers.services import deposit_to_account

        customer = Customer.objects.create(first_name="Jane", last_name="Doe")
        deposit_to_account(
            customer=customer,
            branch=self.branch,
            currency=self.usd,
            amount_received=Decimal("10.00"),
            recorded_by=self.user,
        )
        self._complete_daily_stock_take()

        response = self.client.get(f"/pos/day-end/print/?branch={self.branch.id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer account transactions")
        self.assertContains(response, "Jane Doe")
        self.assertContains(response, "Payment received")

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

    def test_waiter_cannot_access_day_end_api(self):
        waiter = User.objects.create_user(username="waiter", password="pass")
        StaffProfile.objects.create(
            user=waiter,
            branch=self.branch,
            role=StaffRole.WAITER,
            pos_access=True,
        )
        self._complete_daily_stock_take()
        api = APIClient()
        api.force_authenticate(user=waiter)
        response = api.get(
            f"/api/reports/day-end/?branch={self.branch.id}&date={self.today.isoformat()}"
        )
        self.assertEqual(response.status_code, 403)
        post_response = api.post(
            "/api/reports/day-end/",
            {
                "branch": self.branch.id,
                "date": self.today.isoformat(),
                "counted": {str(self.usd.id): "8.00"},
            },
            format="json",
        )
        self.assertEqual(post_response.status_code, 403)


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

    def test_waiter_cannot_manage_expenses(self):
        waiter = User.objects.create_user(username="waiter", password="pass")
        StaffProfile.objects.create(
            user=waiter,
            branch=self.branch,
            role=StaffRole.WAITER,
            pos_access=True,
        )
        self.client.force_authenticate(user=waiter)
        create_response = self.client.post(
            "/api/expenses/",
            {
                "branch": self.branch.id,
                "expense_date": "2026-06-17",
                "amount": "10.00",
                "currency": self.usd.id,
                "description": "Should be denied",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 403)
        list_response = self.client.get(
            f"/api/expenses/?branch={self.branch.id}&date=2026-06-17"
        )
        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(Expense.objects.count(), 0)


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
        self.assertContains(response, "print-expenses-btn")
        self.assertContains(response, "expenses-print-header")
        self.assertContains(response, "print-expense-date")
        self.assertContains(response, "print-printed-at")


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

    def _create_takeaway_order(self, product=None, quantity=Decimal("1")):
        product = product or self.product
        order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            kitchen_status=KitchenStatus.READY,
        )
        order.items.create(product=product, quantity=quantity, price=product.selling_price)
        order.recalculate_total()
        return order

    def test_adding_to_open_takeaway_with_existing_order_id(self):
        existing = self._create_takeaway_order()
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "order_type": OrderType.TAKEAWAY,
                "existing_order_id": existing.id,
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

    def test_existing_order_id_rejects_paid_takeaway(self):
        existing = self._create_takeaway_order()
        existing.status = OrderStatus.PAID
        existing.save(update_fields=["status"])
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "order_type": OrderType.TAKEAWAY,
                "existing_order_id": existing.id,
                "items": [{"product_id": self.latte.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("existing_order_id", response.data)

    def test_existing_order_id_rejects_dine_in_target_for_takeaway(self):
        existing = self._create_table_order("T9")
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "order_type": OrderType.TAKEAWAY,
                "existing_order_id": existing.id,
                "items": [{"product_id": self.latte.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("existing_order_id", response.data)

    def test_takeaway_without_existing_order_id_creates_new(self):
        self._create_takeaway_order()
        response = self.client.post(
            "/api/orders/",
            {
                "branch": self.branch.id,
                "order_type": OrderType.TAKEAWAY,
                "items": [{"product_id": self.latte.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Order.objects.filter(status=OrderStatus.OPEN).count(), 2)


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

    def test_cancel_unpaid_rejected_for_cashier(self):
        order = self._open_order()
        order.status = OrderStatus.UNPAID
        order.save(update_fields=["status"])
        response = self.client.post(f"/api/orders/{order.id}/cancel/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.UNPAID)

    def test_hq_admin_can_cancel_unpaid_order(self):
        User = get_user_model()
        hq_admin = User.objects.create_user(username="hqboss", password="pass")
        StaffProfile.objects.create(
            user=hq_admin,
            branch=self.branch,
            role=StaffRole.HQ_ADMIN,
        )
        order = self._open_order()
        order.status = OrderStatus.UNPAID
        order.save(update_fields=["status"])
        self.client.force_authenticate(user=hq_admin)
        response = self.client.post(f"/api/orders/{order.id}/cancel/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)

    def test_void_paid_order(self):
        order = self._open_order()
        self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        order.refresh_from_db()
        original_receipt = order.receipt_number
        self.assertTrue(order.payments.exists())

        response = self.client.post(f"/api/orders/{order.id}/void/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.UNPAID)
        self.assertIsNone(order.receipt_number)
        self.assertIsNone(order.paid_at)
        self.assertIsNone(order.paid_by)
        self.assertIsNone(order.payment_currency)
        self.assertIsNone(order.exchange_rate)
        self.assertIsNone(order.amount_paid)
        self.assertEqual(order.payment_method, "")
        self.assertFalse(order.payments.exists())
        self.assertEqual(order.cancelled_by_id, self.user.id)

        repay_response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.assertEqual(repay_response.status_code, 200, repay_response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertIsNotNone(order.receipt_number)
        self.assertNotEqual(order.receipt_number, original_receipt)
        self.assertIsNotNone(order.paid_at)
        self.assertEqual(order.paid_by_id, self.user.id)
        self.assertTrue(order.payments.exists())

    def test_list_orders_supports_comma_separated_status(self):
        open_order = self._open_order()
        unpaid_order = self._open_order()
        unpaid_order.status = OrderStatus.UNPAID
        unpaid_order.save(update_fields=["status"])
        paid_order = self._open_order()
        self.client.post(
            f"/api/orders/{paid_order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )

        response = self.client.get("/api/orders/?status=open,unpaid")
        self.assertEqual(response.status_code, 200)
        ids = {order["id"] for order in response.data["results"]}
        self.assertIn(open_order.id, ids)
        self.assertIn(unpaid_order.id, ids)
        self.assertNotIn(paid_order.id, ids)

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
            account_balance=Decimal("-20.00"),
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
        self.assertEqual(customer.account_balance, Decimal("-13.00"))

        response = self.client.post(f"/api/orders/{order.id}/void/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        customer.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.UNPAID)
        self.assertEqual(order.payment_method, "")
        self.assertEqual(customer.account_balance, Decimal("-20.00"))
        self.assertTrue(
            customer.account_transactions.filter(
                transaction_type=CustomerAccountTransactionType.REFUND,
                order=order,
            ).exists()
        )

        repay_response = self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"payment_method": "account"},
            format="json",
        )
        self.assertEqual(repay_response.status_code, 200, repay_response.data)
        customer.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.payment_method, PaymentMethod.ACCOUNT)
        self.assertEqual(customer.account_balance, Decimal("-13.00"))
        self.assertEqual(
            customer.account_transactions.filter(
                transaction_type=CustomerAccountTransactionType.PAYMENT,
                order=order,
            ).count(),
            2,
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


class OrderItemRemoveTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username="cashier", password="pass")
        self.hq_admin = User.objects.create_user(username="hqboss", password="pass")
        self.other_user = User.objects.create_user(username="other", password="pass")
        self.branch = Branch.objects.create(
            name="Test Branch",
            code="TST",
            location="Harare",
            branch_type=BranchType.BRANCH,
        )
        StaffProfile.objects.create(user=self.user, branch=self.branch, pos_access=True)
        StaffProfile.objects.create(
            user=self.hq_admin,
            branch=self.branch,
            role=StaffRole.HQ_ADMIN,
        )
        self.client.force_authenticate(user=self.hq_admin)
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

    def _open_order_with_items(self):
        order = Order.objects.create(branch=self.branch)
        first = order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        second = order.items.create(
            product=self.latte,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        order.recalculate_total()
        return order, first, second

    def test_remove_one_rejected_for_cashier(self):
        order, first, _second = self._open_order_with_items()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            f"/api/orders/{order.id}/items/{first.id}/remove-one/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        first.refresh_from_db()
        self.assertEqual(first.quantity, Decimal("2"))

    def test_remove_item_requires_hq_admin(self):
        order, first, _second = self._open_order_with_items()
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(
            f"/api/orders/{order.id}/items/{first.id}/remove-one/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_hq_admin_remove_one_decrements_quantity(self):
        order, first, _second = self._open_order_with_items()
        response = self.client.post(
            f"/api/orders/{order.id}/items/{first.id}/remove-one/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(first.quantity, Decimal("1"))
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(Decimal(response.data["total_amount"]), Decimal("7.50"))

    def test_hq_admin_remove_last_item_cancels_order(self):
        order, _first, second = self._open_order_with_items()
        order.items.filter(product=self.product).delete()
        order.recalculate_total()
        response = self.client.post(
            f"/api/orders/{order.id}/items/{second.id}/remove-one/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertEqual(order.items.count(), 0)

    def test_remove_one_rejected_for_paid_order(self):
        order, first, _second = self._open_order_with_items()
        order.status = OrderStatus.PAID
        order.save(update_fields=["status"])
        response = self.client.post(
            f"/api/orders/{order.id}/items/{first.id}/remove-one/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("open orders", response.data["detail"].lower())


class OrderItemTransferTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username="transfer_cashier", password="pass")
        self.other_user = User.objects.create_user(username="no_pos", password="pass")
        self.branch = Branch.objects.create(
            name="Transfer Branch",
            code="TRF",
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

    def _open_dine_in(self, table_number, lines):
        order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.DINE_IN,
            table_number=table_number,
            created_by=self.user,
        )
        created = []
        for product, quantity, price in lines:
            created.append(
                order.items.create(product=product, quantity=quantity, price=price)
            )
        order.recalculate_total()
        return order, created

    def test_transfer_partial_lines_creates_destination_order(self):
        order, items = self._open_dine_in(
            "T1",
            [
                (self.product, Decimal("2"), Decimal("3.50")),
                (self.latte, Decimal("1"), Decimal("4.00")),
            ],
        )
        first, second = items
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {"item_ids": [second.id], "table_number": "T2"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)
        self.assertEqual(order.table_number, "T1")
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total_amount, Decimal("7.00"))

        destination = Order.objects.get(pk=response.data["destination_order"]["id"])
        self.assertEqual(destination.table_number, "T2")
        self.assertEqual(destination.status, OrderStatus.OPEN)
        self.assertEqual(destination.items.count(), 1)
        self.assertEqual(destination.items.get().pk, second.pk)
        self.assertEqual(destination.total_amount, Decimal("4.00"))

    def test_transfer_merges_into_existing_open_table_order(self):
        source, source_items = self._open_dine_in(
            "T1",
            [(self.product, Decimal("1"), Decimal("3.50"))],
        )
        destination, dest_items = self._open_dine_in(
            "T2",
            [(self.latte, Decimal("1"), Decimal("4.00"))],
        )
        response = self.client.post(
            f"/api/orders/{source.id}/transfer-items/",
            {"item_ids": [source_items[0].id], "table_number": "T2"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.status, OrderStatus.CANCELLED)
        self.assertEqual(destination.pk, response.data["destination_order"]["id"])
        self.assertEqual(destination.items.count(), 2)
        self.assertEqual(
            set(destination.items.values_list("pk", flat=True)),
            {source_items[0].pk, dest_items[0].pk},
        )

    def test_transfer_all_lines_to_empty_table_reassigns_order(self):
        order, items = self._open_dine_in(
            "T1",
            [
                (self.product, Decimal("1"), Decimal("3.50")),
                (self.latte, Decimal("1"), Decimal("4.00")),
            ],
        )
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {"item_ids": [items[0].id, items[1].id], "table_number": "T9"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)
        self.assertEqual(order.table_number, "T9")
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(
            response.data["source_order"]["id"],
            response.data["destination_order"]["id"],
        )

    def test_transfer_rejects_same_table(self):
        order, items = self._open_dine_in(
            "T1",
            [(self.product, Decimal("1"), Decimal("3.50"))],
        )
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {"item_ids": [items[0].id], "table_number": "T1"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_transfer_dine_in_without_table_to_destination_table(self):
        order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.DINE_IN,
            table_number="",
            created_by=self.user,
        )
        first = order.items.create(
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )
        second = order.items.create(
            product=self.latte,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        order.recalculate_total()
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {"item_ids": [second.id], "table_number": "T9"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)
        self.assertEqual(order.items.count(), 1)

        destination = Order.objects.get(pk=response.data["destination_order"]["id"])
        self.assertEqual(destination.order_type, OrderType.DINE_IN)
        self.assertEqual(destination.table_number, "T9")
        self.assertEqual(destination.items.get().pk, second.pk)
        self.assertEqual(first.order_id, order.pk)

    def test_transfer_takeaway_partial_lines_creates_destination_order(self):
        order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            created_by=self.user,
        )
        first = order.items.create(
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )
        second = order.items.create(
            product=self.latte,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        order.recalculate_total()
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {"item_ids": [second.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total_amount, Decimal("7.00"))

        destination = Order.objects.get(pk=response.data["destination_order"]["id"])
        self.assertEqual(destination.order_type, OrderType.TAKEAWAY)
        self.assertEqual(destination.status, OrderStatus.OPEN)
        self.assertEqual(destination.items.count(), 1)
        self.assertEqual(destination.items.get().pk, second.pk)
        self.assertEqual(destination.total_amount, Decimal("4.00"))

    def test_transfer_takeaway_merges_into_existing_order(self):
        source = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            created_by=self.user,
        )
        source_item = source.items.create(
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )
        source.recalculate_total()
        destination = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            created_by=self.user,
        )
        dest_item = destination.items.create(
            product=self.latte,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        destination.recalculate_total()
        response = self.client.post(
            f"/api/orders/{source.id}/transfer-items/",
            {
                "item_ids": [source_item.id],
                "destination_order_id": destination.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.status, OrderStatus.CANCELLED)
        self.assertEqual(destination.items.count(), 2)
        self.assertEqual(
            set(destination.items.values_list("pk", flat=True)),
            {source_item.pk, dest_item.pk},
        )

    def test_transfer_takeaway_rejects_same_order(self):
        order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
        )
        item = order.items.create(
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {"item_ids": [item.id], "destination_order_id": order.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_transfer_requires_pos_access(self):
        order, items = self._open_dine_in(
            "T1",
            [(self.product, Decimal("1"), Decimal("3.50"))],
        )
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {"item_ids": [items[0].id], "table_number": "T2"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_transfer_dine_in_all_lines_to_takeaway_converts_order(self):
        order, items = self._open_dine_in(
            "T1",
            [
                (self.product, Decimal("1"), Decimal("3.50")),
                (self.latte, Decimal("1"), Decimal("4.00")),
            ],
        )
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {
                "item_ids": [items[0].id, items[1].id],
                "destination_order_type": "takeaway",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)
        self.assertEqual(order.order_type, OrderType.TAKEAWAY)
        self.assertEqual(order.table_number, "")
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(
            response.data["source_order"]["id"],
            response.data["destination_order"]["id"],
        )

    def test_transfer_dine_in_partial_lines_to_new_takeaway(self):
        order, items = self._open_dine_in(
            "T1",
            [
                (self.product, Decimal("1"), Decimal("3.50")),
                (self.latte, Decimal("1"), Decimal("4.00")),
            ],
        )
        first, second = items
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {
                "item_ids": [second.id],
                "destination_order_type": "takeaway",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)
        self.assertEqual(order.order_type, OrderType.DINE_IN)
        self.assertEqual(order.table_number, "T1")
        self.assertEqual(order.items.count(), 1)

        destination = Order.objects.get(pk=response.data["destination_order"]["id"])
        self.assertEqual(destination.order_type, OrderType.TAKEAWAY)
        self.assertEqual(destination.table_number, "")
        self.assertEqual(destination.items.get().pk, second.pk)
        self.assertEqual(first.order_id, order.pk)

    def test_transfer_takeaway_all_lines_to_empty_table_converts_order(self):
        order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            created_by=self.user,
        )
        items = [
            order.items.create(
                product=self.product,
                quantity=Decimal("1"),
                price=Decimal("3.50"),
            ),
            order.items.create(
                product=self.latte,
                quantity=Decimal("1"),
                price=Decimal("4.00"),
            ),
        ]
        order.recalculate_total()
        response = self.client.post(
            f"/api/orders/{order.id}/transfer-items/",
            {
                "item_ids": [items[0].id, items[1].id],
                "destination_order_type": "dine_in",
                "table_number": "T5",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)
        self.assertEqual(order.order_type, OrderType.DINE_IN)
        self.assertEqual(order.table_number, "T5")
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(
            response.data["source_order"]["id"],
            response.data["destination_order"]["id"],
        )

    def test_transfer_takeaway_partial_lines_to_occupied_table(self):
        source = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            created_by=self.user,
        )
        source_item = source.items.create(
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )
        source.recalculate_total()
        destination, dest_items = self._open_dine_in(
            "T2",
            [(self.latte, Decimal("1"), Decimal("4.00"))],
        )
        response = self.client.post(
            f"/api/orders/{source.id}/transfer-items/",
            {
                "item_ids": [source_item.id],
                "destination_order_type": "dine_in",
                "table_number": "T2",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.status, OrderStatus.CANCELLED)
        self.assertEqual(destination.order_type, OrderType.DINE_IN)
        self.assertEqual(destination.items.count(), 2)
        self.assertEqual(
            set(destination.items.values_list("pk", flat=True)),
            {source_item.pk, dest_items[0].pk},
        )

    def test_transfer_dine_in_to_existing_takeaway(self):
        source, source_items = self._open_dine_in(
            "T1",
            [(self.product, Decimal("1"), Decimal("3.50"))],
        )
        destination = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            created_by=self.user,
        )
        dest_item = destination.items.create(
            product=self.latte,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        destination.recalculate_total()
        response = self.client.post(
            f"/api/orders/{source.id}/transfer-items/",
            {
                "item_ids": [source_items[0].id],
                "destination_order_type": "takeaway",
                "destination_order_id": destination.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.status, OrderStatus.CANCELLED)
        self.assertEqual(destination.items.count(), 2)
        self.assertEqual(
            set(destination.items.values_list("pk", flat=True)),
            {source_items[0].pk, dest_item.pk},
        )


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
            account_balance=Decimal("-50.00"),
        )
        self.staff = Customer.objects.create(
            first_name="Staff",
            last_name="Member",
            account_type=CustomerAccountType.STAFF,
            account_balance=Decimal("-50.00"),
        )
        self.regular = Customer.objects.create(
            first_name="Reg",
            last_name="Ular",
            account_type=CustomerAccountType.REGULAR,
            account_balance=Decimal("-50.00"),
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
        self.assertEqual(self.family.account_balance, Decimal("-49.00"))

    def test_customer_serializer_includes_account_type(self):
        response = self.client.get(f"/api/customers/{self.family.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["account_type"], "family")
        self.assertEqual(response.data["account_type_display"], "Family")
