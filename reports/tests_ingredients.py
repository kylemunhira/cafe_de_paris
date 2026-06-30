from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from bakery.models import ProductionOrder, ProductionOrderStatus, Recipe
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import BranchInventory
from orders.models import Order, OrderItem, OrderStatus, OrderType
from reports.ingredients import build_ingredient_stock_report, build_ingredient_usage_report


class IngredientStockReportTests(TestCase):
    def setUp(self):
        self.branch_a = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.branch_b = Branch.objects.create(
            name="Bakery",
            branch_type=BranchType.BAKERY,
        )
        self.ingredients = ProductCategory.objects.create(name="Ingredients")
        self.flour = Product.objects.create(
            name="Flour",
            category=self.ingredients,
            selling_price=Decimal("2.50"),
        )
        self.milk = Product.objects.create(
            name="Milk",
            category=self.ingredients,
            selling_price=Decimal("1.20"),
            is_active=False,
        )
        BranchInventory.objects.create(
            branch=self.branch_a,
            product=self.flour,
            quantity=Decimal("100"),
        )
        BranchInventory.objects.create(
            branch=self.branch_b,
            product=self.flour,
            quantity=Decimal("40"),
        )
        BranchInventory.objects.create(
            branch=self.branch_a,
            product=self.milk,
            quantity=Decimal("5"),
        )

    def test_report_lists_stock_and_cost_per_branch(self):
        report_a = build_ingredient_stock_report(
            branch_id=self.branch_a.id,
            active_only=False,
        )
        report_b = build_ingredient_stock_report(
            branch_id=self.branch_b.id,
            active_only=False,
        )

        self.assertEqual(report_a["summary"]["ingredient_count"], 2)
        self.assertEqual(report_a["summary"]["branch_count"], 1)
        self.assertEqual(report_a["summary"]["total_stock_value"], Decimal("256.00"))

        flour_avondale = next(
            row for row in report_a["rows"] if row["ingredient_name"] == "Flour"
        )
        self.assertEqual(flour_avondale["quantity"], Decimal("100"))
        self.assertEqual(flour_avondale["unit_cost"], Decimal("2.50"))
        self.assertEqual(flour_avondale["stock_value"], Decimal("250.00"))

        flour_bakery = next(
            row for row in report_b["rows"] if row["ingredient_name"] == "Flour"
        )
        self.assertEqual(flour_bakery["quantity"], Decimal("40"))
        self.assertEqual(flour_bakery["stock_value"], Decimal("100.00"))

        milk_avondale = next(
            row for row in report_a["rows"] if row["ingredient_name"] == "Milk"
        )
        self.assertEqual(milk_avondale["quantity"], Decimal("5"))
        self.assertEqual(milk_avondale["stock_value"], Decimal("6.00"))

    def test_report_filters_by_branch_and_active(self):
        report = build_ingredient_stock_report(branch_id=self.branch_a.id, active_only=True)

        self.assertEqual(report["summary"]["branch_count"], 1)
        self.assertEqual(report["summary"]["ingredient_count"], 1)
        self.assertEqual(len(report["rows"]), 1)
        self.assertEqual(report["rows"][0]["ingredient_name"], "Flour")

    def test_low_stock_filter(self):
        report = build_ingredient_stock_report(
            branch_id=self.branch_a.id,
            active_only=False,
            low_stock_only=True,
            low_stock_threshold="10",
        )

        names = {row["ingredient_name"] for row in report["rows"]}
        self.assertEqual(names, {"Milk"})

    def test_api_endpoint(self):
        client = APIClient()
        response = client.get("/api/reports/ingredient-stock/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("rows", response.data)
        self.assertIn("summary", response.data)


class IngredientUsageReportTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        self.bakery = Branch.objects.create(
            name="Bakery",
            branch_type=BranchType.BAKERY,
        )
        self.ingredients = ProductCategory.objects.create(name="Ingredients")
        self.pastries = ProductCategory.objects.create(name="Pastries")
        self.flour = Product.objects.create(
            name="Flour",
            category=self.ingredients,
            selling_price=Decimal("2.00"),
        )
        self.butter = Product.objects.create(
            name="Butter",
            category=self.ingredients,
            selling_price=Decimal("3.00"),
        )
        self.croissant = Product.objects.create(
            name="Croissant",
            category=self.pastries,
            selling_price=Decimal("3.50"),
        )
        Recipe.objects.create(
            product=self.croissant,
            ingredient=self.flour,
            quantity_required=Decimal("0.50"),
        )
        Recipe.objects.create(
            product=self.croissant,
            ingredient=self.butter,
            quantity_required=Decimal("0.10"),
        )

    def test_usage_from_sales_per_branch_and_day(self):
        order = Order.objects.create(
            branch=self.branch,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.PAID,
            total_amount=Decimal("7.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.croissant,
            quantity=Decimal("2"),
            price=Decimal("3.50"),
        )

        report = build_ingredient_usage_report(
            report_date=self.today.isoformat(),
            branch_id=self.branch.id,
        )

        self.assertEqual(report["date"], self.today.isoformat())
        self.assertEqual(report["summary"]["ingredient_count"], 2)
        self.assertEqual(report["summary"]["total_quantity_used"], Decimal("1.20"))
        self.assertEqual(report["summary"]["total_usage_cost"], Decimal("2.60"))

        flour = next(row for row in report["rows"] if row["ingredient_name"] == "Flour")
        self.assertEqual(flour["from_sales"], Decimal("1.00"))
        self.assertEqual(flour["from_production"], Decimal("0"))
        self.assertEqual(flour["quantity_used"], Decimal("1.00"))
        self.assertEqual(flour["usage_cost"], Decimal("2.00"))

        butter = next(row for row in report["rows"] if row["ingredient_name"] == "Butter")
        self.assertEqual(butter["from_sales"], Decimal("0.20"))
        self.assertEqual(butter["usage_cost"], Decimal("0.60"))

    def test_usage_from_production_at_bakery(self):
        ProductionOrder.objects.create(
            branch=self.bakery,
            product=self.croissant,
            quantity=Decimal("10"),
            status=ProductionOrderStatus.COMPLETED,
        )

        report = build_ingredient_usage_report(
            report_date=self.today.isoformat(),
            branch_id=self.bakery.id,
        )

        flour = next(row for row in report["rows"] if row["ingredient_name"] == "Flour")
        self.assertEqual(flour["from_sales"], Decimal("0"))
        self.assertEqual(flour["from_production"], Decimal("5.00"))
        self.assertEqual(flour["quantity_used"], Decimal("5.00"))

    def test_usage_api_endpoint(self):
        client = APIClient()
        response = client.get(
            f"/api/reports/ingredient-usage/?date={self.today.isoformat()}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("rows", response.data)
        self.assertIn("date", response.data)
