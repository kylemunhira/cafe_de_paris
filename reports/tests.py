from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from orders.models import Order, OrderItem, OrderStatus, OrderType
from reports.services import build_report_summary, export_sales_csv


class ReportServiceTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price=Decimal("4.00"),
            tax_rate=Decimal("15"),
            remaining_qty=Decimal("5"),
        )
        self.order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("8.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("4.00"),
        )

    def test_summary_includes_revenue_and_tax(self):
        today = timezone.localdate()
        report = build_report_summary(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["order_count"], 1)
        self.assertEqual(report["summary"]["total_revenue"], Decimal("8.00"))
        self.assertEqual(report["summary"]["tax_collected"], Decimal("1.20"))
        self.assertEqual(len(report["top_products"]), 1)
        self.assertEqual(report["top_products"][0]["product_name"], "Espresso")
        self.assertEqual(len(report["low_stock"]), 1)

    def test_summary_excludes_unpaid_orders(self):
        Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.OPEN,
            total_amount=Decimal("99.00"),
        )
        today = timezone.localdate()
        report = build_report_summary(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["order_count"], 1)

    def test_export_sales_csv(self):
        today = timezone.localdate()
        csv_text = export_sales_csv(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertIn("order_id,date,branch,product,category", csv_text)
        self.assertIn("Espresso", csv_text)
        self.assertIn("Avondale", csv_text)


class ReportApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="HQ", branch_type=BranchType.HQ)
        category = ProductCategory.objects.create(name="Pastries")
        product = Product.objects.create(
            name="Croissant",
            category=category,
            selling_price=Decimal("3.00"),
        )
        order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.PAID,
            total_amount=Decimal("3.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=Decimal("1"),
            price=Decimal("3.00"),
        )

    def test_summary_endpoint(self):
        today = timezone.localdate().isoformat()
        response = self.client.get(f"/api/reports/summary/?from={today}&to={today}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["order_count"], 1)

    def test_export_endpoint(self):
        today = timezone.localdate().isoformat()
        response = self.client.get(f"/api/reports/export-csv/?from={today}&to={today}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Croissant", response.content)
