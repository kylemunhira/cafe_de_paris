import io

from django.test import TestCase
from rest_framework.test import APIClient

from catalog.csv_io import export_products_csv, import_products_csv
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
