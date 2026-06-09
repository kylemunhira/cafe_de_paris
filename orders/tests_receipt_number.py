from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from orders.models import BranchReceiptSequence, Order, OrderStatus
from orders.services import ReceiptNumberError, allocate_receipt_number
from payments.models import Currency, CurrencyRate


class ReceiptNumberAllocationTests(TestCase):
    def setUp(self):
        self.highland = Branch.objects.create(
            name="Highland",
            code="HIG",
            branch_type=BranchType.BRANCH,
        )
        self.churchill = Branch.objects.create(
            name="Churchill",
            code="CHU",
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

    @patch("orders.services.timezone.localdate")
    def test_allocate_receipt_number_format(self, mock_localdate):
        mock_localdate.return_value = timezone.datetime(2026, 6, 9).date()

        first = allocate_receipt_number(self.highland)
        second = allocate_receipt_number(self.highland)
        churchill = allocate_receipt_number(self.churchill)

        self.assertEqual(first, "HIG0906261")
        self.assertEqual(second, "HIG0906262")
        self.assertEqual(churchill, "CHU0906261")

    def test_allocate_requires_three_letter_code(self):
        branch = Branch.objects.create(name="No Code Branch")
        with self.assertRaises(ReceiptNumberError):
            allocate_receipt_number(branch)

    def test_daily_counter_resets_on_new_date(self):
        state = BranchReceiptSequence.objects.create(
            branch=self.highland,
            sequence_date=timezone.datetime(2026, 6, 8).date(),
            daily_count=12,
        )

        with patch("orders.services.timezone.localdate") as mock_localdate:
            mock_localdate.return_value = timezone.datetime(2026, 6, 9).date()
            receipt_number = allocate_receipt_number(self.highland)

        self.assertEqual(receipt_number, "HIG0906261")
        state.refresh_from_db()
        self.assertEqual(state.daily_count, 1)

    def test_pay_assigns_receipt_number(self):
        client = APIClient()
        order = Order.objects.create(branch=self.highland)
        order.items.create(
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()

        with patch("orders.services.timezone.localdate") as mock_localdate:
            mock_localdate.return_value = timezone.datetime(2026, 6, 9).date()
            response = client.post(
                f"/api/orders/{order.id}/pay/",
                {"currency_id": self.usd.id},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.receipt_number, "HIG0906261")
        self.assertEqual(response.data["receipt_number"], "HIG0906261")

    def test_pay_without_branch_code_fails(self):
        client = APIClient()
        branch = Branch.objects.create(name="Unconfigured")
        order = Order.objects.create(branch=branch)
        order.items.create(
            product=self.product,
            quantity=Decimal("1"),
            price=Decimal("3.50"),
        )
        order.recalculate_total()

        response = client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("3-letter receipt code", response.data["detail"])
