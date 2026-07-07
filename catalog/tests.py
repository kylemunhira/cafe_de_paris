import io
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from catalog.csv_io import (
    export_ingredients_csv,
    export_products_csv,
    import_ingredients_csv,
    import_products_csv,
)
from catalog.menu_items_import import export_menu_items_csv
from catalog.constants import INGREDIENTS_CATEGORY
from catalog.models import Product, ProductCategory


class ProductCsvTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso",
            category=self.category,
            selling_price="3.50",
        )

    def test_export_includes_products(self):
        csv_text = export_products_csv()
        self.assertIn("remaining_qty", csv_text)
        self.assertIn("tax_rate", csv_text)
        self.assertIn("Espresso", csv_text)
        self.assertIn("Coffee", csv_text)

    def test_import_creates_product(self):
        csv_file = io.BytesIO(
            b"name,category,selling_price,is_active\nLatte,Coffee,4.00,true\n"
        )
        result = import_products_csv(csv_file)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], [])
        self.assertTrue(Product.objects.filter(name="Latte").exists())

    def test_import_updates_by_id(self):
        csv_file = io.BytesIO(
            f"id,name,category,selling_price,is_active\n"
            f"{self.product.id},Espresso Double,Coffee,4.50,false\n".encode()
        )
        result = import_products_csv(csv_file)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Espresso Double")
        self.assertFalse(self.product.is_active)

    def test_import_rolls_back_on_error(self):
        csv_file = io.BytesIO(
            b"name,category,selling_price\nGood Product,Coffee,3.00\n,Tea,2.00\n"
        )
        result = import_products_csv(csv_file)
        self.assertEqual(len(result["errors"]), 1)
        self.assertFalse(Product.objects.filter(name="Good Product").exists())

    def test_export_endpoint(self):
        response = self.client.get("/api/products/export-csv/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(b"Espresso", response.content)

    def test_import_endpoint(self):
        csv_content = b"name,category,selling_price\nCappuccino,Coffee,3.75\n"
        upload = io.BytesIO(csv_content)
        upload.name = "products.csv"
        response = self.client.post(
            "/api/products/import-csv/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)
        self.assertTrue(Product.objects.filter(name="Cappuccino").exists())


class BakeryTransferProductFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.bakery_category = ProductCategory.objects.create(name="Breads & pastries")
        self.component_category = ProductCategory.objects.create(name="Components")
        self.coffee_category = ProductCategory.objects.create(name="Coffee")
        self.croissant = Product.objects.create(
            name="Croissant",
            category=self.bakery_category,
            selling_price="2.75",
        )
        Product.objects.create(
            name="Pastry Cream",
            category=self.component_category,
            selling_price="0",
        )
        Product.objects.create(
            name="Espresso",
            category=self.coffee_category,
            selling_price="3.50",
        )

    def test_bakery_transfer_filter_returns_sellable_bakery_products_only(self):
        response = self.client.get("/api/products/?bakery_transfer=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Croissant"})

    def test_bakery_manufactured_filter_includes_components(self):
        response = self.client.get("/api/products/?bakery_manufactured=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Croissant", "Pastry Cream"})

    def test_exclude_bakery_filter_omits_bakery_categories(self):
        response = self.client.get("/api/products/?exclude_bakery=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Espresso"})

    def test_pos_catalog_includes_bakery_finished_goods(self):
        response = self.client.get("/api/products/?pos_catalog=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertEqual(names, {"Croissant", "Espresso"})

    def test_pos_catalog_excludes_components(self):
        response = self.client.get("/api/products/?pos_catalog=true")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["results"]}
        self.assertNotIn("Pastry Cream", names)


class IngredientCsvTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name=INGREDIENTS_CATEGORY)
        self.ingredient = Product.objects.create(
            name="Butter",
            category=self.category,
            selling_price="8.70",
            remaining_qty="12",
        )

    def test_export_ingredients_csv(self):
        csv_text = export_ingredients_csv()
        self.assertIn("unit_cost", csv_text)
        self.assertIn("Butter", csv_text)
        self.assertNotIn("category", csv_text)

    def test_import_ingredients_csv_creates(self):
        csv_file = io.BytesIO(b"name,unit_cost,remaining_qty\nFlour,1.00,50\n")
        result = import_ingredients_csv(csv_file)
        self.assertEqual(result["created"], 1)
        product = Product.objects.get(name="Flour")
        self.assertEqual(product.category.name, INGREDIENTS_CATEGORY)

    def test_import_ingredients_csv_falls_back_to_name_when_id_missing(self):
        csv_file = io.BytesIO(b"id,name,unit_cost\n99999,Butter,9.50\n")
        result = import_ingredients_csv(csv_file)
        self.assertEqual(result["updated"], 1)
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.selling_price, Decimal("9.50"))

    def test_import_ingredients_endpoint(self):
        upload = io.BytesIO(b"name,unit_cost\nSugar,1.00\n")
        upload.name = "ingredients.csv"
        response = self.client.post(
            "/api/products/import-ingredients-csv/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Product.objects.filter(name="Sugar").exists())


class MenuItemsCsvApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = ProductCategory.objects.create(name="Coffee")
        self.product = Product.objects.create(
            name="Espresso (Short)",
            category=self.category,
            selling_price=Decimal("2"),
            tax_rate=Decimal("0"),
        )

    def test_export_menu_items_csv(self):
        csv_text = export_menu_items_csv()
        self.assertIn("ch,name,category", csv_text)
        self.assertIn("Espresso (Short)", csv_text)
        self.assertIn("Coffee", csv_text)

    def test_import_menu_items_endpoint_replaces_missing_products(self):
        desserts = ProductCategory.objects.create(name="Desserts")
        Product.objects.create(name="Old Tart", category=desserts, selling_price=Decimal("5"))

        csv_content = (
            "ch,name,category,selling_price,remaining_qty,tax_rate,is_active,id\n"
            f"Coffee,Espresso (Short),,2,15,0,TRUE,{self.product.id}\n"
        ).encode()
        upload = io.BytesIO(csv_content)
        upload.name = "menu_items.csv"
        response = self.client.post(
            "/api/products/import-menu-items-csv/?replace=true",
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["products_updated"], 1)
        self.assertEqual(response.data["deactivated"], 1)
        self.assertFalse(Product.objects.get(name="Old Tart").is_active)

    def test_export_menu_items_endpoint(self):
        response = self.client.get("/api/products/export-menu-items-csv/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"Espresso (Short)", response.content)
