from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import (
    BranchInventory,
    StockTake,
    StockTakeStatus,
    StockTakeType,
)

User = get_user_model()


class StockTakeWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(
            name="Avondale",
            branch_type=BranchType.BRANCH,
        )
        food_cat = ProductCategory.objects.create(name="Pastries", is_asset=False)
        ingredient_cat = ProductCategory.objects.create(
            name="Ingredients", is_asset=False
        )
        asset_cat = ProductCategory.objects.create(name="Equipment", is_asset=True)

        self.croissant = Product.objects.create(
            name="Croissant",
            category=food_cat,
            selling_price=Decimal("2.75"),
        )
        self.flour = Product.objects.create(
            name="Flour",
            category=ingredient_cat,
            selling_price=Decimal("5.00"),
        )
        self.blender = Product.objects.create(
            name="Blender",
            category=asset_cat,
            selling_price=Decimal("200.00"),
        )

        BranchInventory.objects.create(
            branch=self.branch,
            product=self.croissant,
            quantity=Decimal("10"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.flour,
            quantity=Decimal("50"),
        )
        BranchInventory.objects.create(
            branch=self.branch,
            product=self.blender,
            quantity=Decimal("2"),
        )

    def test_daily_stock_take_excludes_assets(self):
        response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-09",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        product_ids = {line["product"] for line in response.data["lines"]}
        self.assertIn(self.croissant.id, product_ids)
        self.assertIn(self.flour.id, product_ids)
        self.assertNotIn(self.blender.id, product_ids)

    def test_monthly_stock_take_includes_assets(self):
        response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.MONTHLY,
                "count_date": "2026-06-15",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["count_date"], "2026-06-01")
        product_ids = {line["product"] for line in response.data["lines"]}
        self.assertIn(self.blender.id, product_ids)

    def test_complete_stock_take_posts_variances(self):
        create_response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-09",
            },
            format="json",
        )
        stock_take_id = create_response.data["id"]
        lines = create_response.data["lines"]

        croissant_line = next(
            line for line in lines if line["product"] == self.croissant.id
        )
        flour_line = next(line for line in lines if line["product"] == self.flour.id)

        patch_response = self.client.patch(
            f"/api/stock-takes/{stock_take_id}/lines/",
            {
                "lines": [
                    {
                        "id": croissant_line["id"],
                        "counted_quantity": "8",
                    },
                    {
                        "id": flour_line["id"],
                        "counted_quantity": "50",
                    },
                ]
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)

        complete_response = self.client.post(
            f"/api/stock-takes/{stock_take_id}/complete/",
            {},
            format="json",
        )
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.data["status"], StockTakeStatus.COMPLETED)

        croissant_inventory = BranchInventory.objects.get(
            branch=self.branch, product=self.croissant
        )
        self.assertEqual(croissant_inventory.quantity, Decimal("8"))

    def test_duplicate_completed_daily_stock_take_rejected(self):
        stock_take = StockTake.objects.create(
            branch=self.branch,
            stock_take_type=StockTakeType.DAILY,
            count_date=date(2026, 6, 9),
            status=StockTakeStatus.COMPLETED,
        )
        self.assertEqual(stock_take.pk, stock_take.id)

        response = self.client.post(
            "/api/stock-takes/",
            {
                "branch": self.branch.id,
                "stock_take_type": StockTakeType.DAILY,
                "count_date": "2026-06-09",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.data["detail"])
