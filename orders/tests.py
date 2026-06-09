from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from orders.models import Order, OrderStatus
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
        self.order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.PAID,
            payment_currency=currency,
            exchange_rate=Decimal("1"),
            amount_paid=Decimal("4.00"),
            total_amount=Decimal("4.00"),
            receipt_number="AVO0906261",
        )
        self.order.items.create(
            product=product,
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        self.user = User.objects.create_user(username="cashier", password="pass")
        StaffProfile.objects.create(user=self.user, branch=self.branch)
        self.client.force_login(self.user)

    def test_receipt_print_for_paid_order(self):
        response = self.client.get(f"/pos/receipt/{self.order.id}/print/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sales Receipt")
        self.assertContains(response, "Receipt #AVO0906261")
        self.assertContains(response, "Order #")
        self.assertContains(response, "Latte")
        self.assertContains(response, "US Dollar")

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

    def test_invoice_print_not_available_for_open_order(self):
        open_order = Order.objects.create(branch=self.branch, status=OrderStatus.OPEN)
        response = self.client.get(f"/invoices/{open_order.id}/print/")
        self.assertEqual(response.status_code, 404)
