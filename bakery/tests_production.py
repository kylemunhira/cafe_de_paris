from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile, StaffRole
from bakery.models import ProductionOrder, ProductionOrderStatus, Recipe
from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from inventory.models import BranchInventory

User = get_user_model()


class BakeryProductionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.bakery = Branch.objects.create(
            name="Central Bakery",
            branch_type=BranchType.BAKERY,
        )
        self.baker = User.objects.create_user(username="baker", password="pass")
        StaffProfile.objects.create(
            user=self.baker,
            branch=self.bakery,
            role=StaffRole.BAKER,
        )
        self.client.force_login(self.baker)

        pastries = ProductCategory.objects.create(name="Breads & pastries")
        ingredients = ProductCategory.objects.create(name="Ingredients")

        self.croissant = Product.objects.create(
            name="Croissant",
            category=pastries,
            selling_price=Decimal("2.75"),
        )
        self.flour = Product.objects.create(
            name="Flour",
            category=ingredients,
            selling_price=Decimal("5.00"),
        )
        self.butter = Product.objects.create(
            name="Butter",
            category=ingredients,
            selling_price=Decimal("5.00"),
        )

        Recipe.objects.create(
            product=self.croissant,
            ingredient=self.flour,
            quantity_required=Decimal("0.30"),
        )
        Recipe.objects.create(
            product=self.croissant,
            ingredient=self.butter,
            quantity_required=Decimal("0.15"),
        )

        BranchInventory.objects.create(
            branch=self.bakery,
            product=self.flour,
            quantity=Decimal("10"),
        )
        BranchInventory.objects.create(
            branch=self.bakery,
            product=self.butter,
            quantity=Decimal("10"),
        )

    def test_preview_production(self):
        response = self.client.post(
            "/api/production-orders/preview/",
            {
                "branch": self.bakery.id,
                "product": self.croissant.id,
                "quantity": "10",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_produce"])
        self.assertEqual(len(response.data["lines"]), 2)

    def test_complete_production_updates_inventory(self):
        response = self.client.post(
            "/api/production-orders/",
            {
                "branch": self.bakery.id,
                "product": self.croissant.id,
                "quantity": "10",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], ProductionOrderStatus.COMPLETED)

        flour_stock = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.flour,
        )
        butter_stock = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.butter,
        )
        croissant_stock = BranchInventory.objects.get(
            branch=self.bakery,
            product=self.croissant,
        )

        self.assertEqual(flour_stock.quantity, Decimal("7.00"))
        self.assertEqual(butter_stock.quantity, Decimal("8.50"))
        self.assertEqual(croissant_stock.quantity, Decimal("10"))
        self.assertEqual(ProductionOrder.objects.count(), 1)

    def test_rejects_production_without_recipe(self):
        pastries = ProductCategory.objects.get(name="Breads & pastries")
        baguette = Product.objects.create(
            name="Baguette",
            category=pastries,
            selling_price=Decimal("2.50"),
        )

        response = self.client.post(
            "/api/production-orders/",
            {
                "branch": self.bakery.id,
                "product": baguette.id,
                "quantity": "5",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("recipe", str(response.data).lower())

    def test_rejects_production_with_insufficient_ingredients(self):
        response = self.client.post(
            "/api/production-orders/",
            {
                "branch": self.bakery.id,
                "product": self.croissant.id,
                "quantity": "100",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("shortages", response.data)
