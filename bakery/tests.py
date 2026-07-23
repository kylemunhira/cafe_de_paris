from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import Product, ProductCategory

from .models import Recipe


class RecipeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        pastries = ProductCategory.objects.create(name="Pastries")
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

    def test_create_and_list_recipe_lines(self):
        create_response = self.client.post(
            "/api/recipes/",
            {
                "product": self.croissant.id,
                "ingredient": self.flour.id,
                "quantity_required": "0.25",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["product_name"], "Croissant")
        self.assertEqual(create_response.data["ingredient_name"], "Flour")
        self.assertEqual(create_response.data["ingredient_unit_cost"], "5.00")
        self.assertEqual(create_response.data["line_cost"], Decimal("1.25"))

        list_response = self.client.get(
            f"/api/recipes/?product={self.croissant.id}"
        )
        self.assertEqual(list_response.status_code, 200)
        results = list_response.data.get("results", list_response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(Decimal(results[0]["quantity_required"]), Decimal("0.25"))
        self.assertEqual(results[0]["line_cost"], Decimal("1.25"))

    def test_accepts_small_fractional_quantities(self):
        response = self.client.post(
            "/api/recipes/",
            {
                "product": self.croissant.id,
                "ingredient": self.flour.id,
                "quantity_required": "0.005",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["quantity_required"], "0.0050")

        recipe = Recipe.objects.get(pk=response.data["id"])
        self.assertEqual(recipe.quantity_required, Decimal("0.0050"))

    def test_rejects_duplicate_ingredient_for_same_product(self):
        Recipe.objects.create(
            product=self.croissant,
            ingredient=self.flour,
            quantity_required=Decimal("0.25"),
        )

        response = self.client.post(
            "/api/recipes/",
            {
                "product": self.croissant.id,
                "ingredient": self.flour.id,
                "quantity_required": "0.30",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_same_product_as_ingredient(self):
        response = self.client.post(
            "/api/recipes/",
            {
                "product": self.croissant.id,
                "ingredient": self.croissant.id,
                "quantity_required": "1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ingredient", response.data)

    def test_update_and_delete_recipe_line(self):
        recipe = Recipe.objects.create(
            product=self.croissant,
            ingredient=self.butter,
            quantity_required=Decimal("0.10"),
        )

        patch_response = self.client.patch(
            f"/api/recipes/{recipe.id}/",
            {"quantity_required": "0.15"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(Decimal(patch_response.data["quantity_required"]), Decimal("0.15"))

        delete_response = self.client.delete(f"/api/recipes/{recipe.id}/")
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Recipe.objects.filter(pk=recipe.id).exists())

    def test_can_update_quantity_when_product_is_inactive(self):
        recipe = Recipe.objects.create(
            product=self.croissant,
            ingredient=self.butter,
            quantity_required=Decimal("0.10"),
        )
        self.croissant.is_active = False
        self.croissant.save(update_fields=["is_active"])

        response = self.client.patch(
            f"/api/recipes/{recipe.id}/",
            {"quantity_required": "0.20"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["quantity_required"]), Decimal("0.20"))

    def test_rejects_create_for_inactive_product(self):
        self.croissant.is_active = False
        self.croissant.save(update_fields=["is_active"])

        response = self.client.post(
            "/api/recipes/",
            {
                "product": self.croissant.id,
                "ingredient": self.flour.id,
                "quantity_required": "0.25",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("product", response.data)
