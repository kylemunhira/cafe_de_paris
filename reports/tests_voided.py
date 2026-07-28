from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from orders.models import Order, OrderStatus
from payments.models import Currency, CurrencyRate
from reports.voided import build_voided_cancelled_report


class VoidedCancelledReportTests(TestCase):
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
        self.today = timezone.localdate()
        category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=category,
            selling_price=Decimal("3.50"),
        )
        self.tea = Product.objects.create(
            name="Tea",
            category=category,
            selling_price=Decimal("2.00"),
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

    def _open_order(self, product=None, quantity=Decimal("2")):
        order = Order.objects.create(branch=self.branch, table_number="T5")
        order.items.create(
            product=product or self.product,
            quantity=quantity,
            price=(product or self.product).selling_price,
        )
        order.recalculate_total()
        return order

    def test_cancelled_order_items_in_report(self):
        order = self._open_order()
        self.client.post(f"/api/orders/{order.id}/cancel/", {}, format="json")

        report = build_voided_cancelled_report(report_date=self.today.isoformat())
        self.assertEqual(report["summary"]["cancelled_order_count"], 1)
        self.assertEqual(report["summary"]["cancelled_item_count"], 1)
        self.assertEqual(report["summary"]["cancelled_amount"], Decimal("7.00"))
        self.assertEqual(report["summary"]["voided_item_count"], 0)

        row = report["rows"][0]
        self.assertEqual(row["action_type"], "cancelled")
        self.assertEqual(row["product_name"], "Espresso")
        self.assertEqual(row["quantity"], Decimal("2"))
        self.assertEqual(row["line_total"], Decimal("7.00"))
        self.assertEqual(row["table_number"], "T5")

    def test_voided_order_items_in_report(self):
        order = self._open_order()
        self.client.post(
            f"/api/orders/{order.id}/pay/",
            {"currency_id": self.usd.id},
            format="json",
        )
        self.client.post(f"/api/orders/{order.id}/void/", {}, format="json")

        report = build_voided_cancelled_report(report_date=self.today.isoformat())
        self.assertEqual(report["summary"]["voided_order_count"], 1)
        self.assertEqual(report["summary"]["voided_item_count"], 1)
        self.assertEqual(report["summary"]["voided_amount"], Decimal("7.00"))
        self.assertEqual(report["summary"]["cancelled_item_count"], 0)

        row = report["rows"][0]
        self.assertEqual(row["action_type"], "voided")
        self.assertEqual(row["order_status"], OrderStatus.UNPAID)

    def test_report_filters_by_branch(self):
        other_branch = Branch.objects.create(
            name="Other",
            code="OTH",
            location="Bulawayo",
            branch_type=BranchType.BRANCH,
        )
        local_order = self._open_order()
        self.client.post(f"/api/orders/{local_order.id}/cancel/", {}, format="json")

        remote_order = Order.objects.create(branch=other_branch)
        remote_order.items.create(
            product=self.tea,
            quantity=Decimal("1"),
            price=Decimal("2.00"),
        )
        remote_order.recalculate_total()
        self.client.post(f"/api/orders/{remote_order.id}/cancel/", {}, format="json")

        report = build_voided_cancelled_report(
            report_date=self.today.isoformat(),
            branch_id=self.branch.id,
        )
        self.assertEqual(report["summary"]["cancelled_order_count"], 1)
        self.assertEqual(len(report["rows"]), 1)
        self.assertEqual(report["rows"][0]["product_name"], "Espresso")

    def test_report_search_filters_products(self):
        order = self._open_order(product=self.tea, quantity=Decimal("1"))
        self.client.post(f"/api/orders/{order.id}/cancel/", {}, format="json")

        report = build_voided_cancelled_report(
            report_date=self.today.isoformat(),
            search="tea",
        )
        self.assertEqual(len(report["rows"]), 1)
        self.assertEqual(report["rows"][0]["product_name"], "Tea")

        empty = build_voided_cancelled_report(
            report_date=self.today.isoformat(),
            search="espresso",
        )
        self.assertEqual(empty["rows"], [])

    def test_voided_cancelled_api_endpoint(self):
        order = self._open_order()
        self.client.post(f"/api/orders/{order.id}/cancel/", {}, format="json")

        response = self.client.get(
            f"/api/reports/voided-cancelled/?date={self.today.isoformat()}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("rows", response.data)
        self.assertIn("summary", response.data)
        self.assertEqual(response.data["summary"]["cancelled_order_count"], 1)
