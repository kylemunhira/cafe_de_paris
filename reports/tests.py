from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from branches.models import Branch, BranchType
from bakery.models import Recipe
from catalog.models import Product, ProductCategory
from orders.models import Expense, Order, OrderItem, OrderStatus, OrderType
from orders.tax import split_inclusive_total
from reports.services import build_profit_report, build_report_summary, export_sales_csv


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
        self.assertEqual(
            report["summary"]["tax_collected"],
            split_inclusive_total(Decimal("8.00"))["tax"],
        )
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


class ProfitReportTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.category = ProductCategory.objects.create(name="Pastries")
        self.ingredient = Product.objects.create(
            name="Flour",
            category=self.category,
            selling_price=Decimal("1.00"),
        )
        self.product = Product.objects.create(
            name="Croissant",
            category=self.category,
            selling_price=Decimal("3.00"),
        )
        Recipe.objects.create(
            product=self.product,
            ingredient=self.ingredient,
            quantity_required=Decimal("0.25"),
        )
        self.order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("6.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=Decimal("2"),
            price=Decimal("3.00"),
        )

    def test_profit_report_calculates_cogs_and_margin(self):
        today = timezone.localdate()
        report = build_profit_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["total_revenue"], Decimal("6.00"))
        self.assertEqual(report["summary"]["total_cogs"], Decimal("0.50"))
        self.assertEqual(report["summary"]["gross_profit"], Decimal("5.50"))
        self.assertEqual(report["summary"]["gross_profit_percent"], Decimal("91.67"))
        self.assertEqual(len(report["by_product"]), 1)
        self.assertEqual(report["by_product"][0]["product_name"], "Croissant")
        self.assertEqual(report["by_product"][0]["gp_percent"], Decimal("91.67"))

    def test_profit_report_includes_operating_expenses(self):
        from payments.models import Currency

        currency = Currency.objects.create(code="USD", name="US Dollar", symbol="$")
        today = timezone.localdate()
        Expense.objects.create(
            branch=self.branch,
            expense_date=today,
            amount=Decimal("2.00"),
            currency=currency,
            description="Sugar",
        )
        report = build_profit_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["operating_expenses"], Decimal("2.00"))
        self.assertEqual(report["summary"]["net_profit"], Decimal("3.50"))

    def test_profit_report_flags_products_without_recipe(self):
        Product.objects.create(
            name="Coffee",
            category=self.category,
            selling_price=Decimal("4.00"),
        )
        order = Order.objects.create(
            branch=self.branch,
            status=OrderStatus.PAID,
            total_amount=Decimal("4.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=Product.objects.get(name="Coffee"),
            quantity=Decimal("1"),
            price=Decimal("4.00"),
        )
        today = timezone.localdate()
        report = build_profit_report(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
        )
        self.assertEqual(report["summary"]["products_without_recipe"], 1)
        self.assertEqual(report["summary"]["revenue_without_recipe"], Decimal("4.00"))


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

    def test_profit_endpoint(self):
        today = timezone.localdate().isoformat()
        response = self.client.get(f"/api/reports/profit/?from={today}&to={today}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("gross_profit", response.data["summary"])
        self.assertIn("by_product", response.data)
