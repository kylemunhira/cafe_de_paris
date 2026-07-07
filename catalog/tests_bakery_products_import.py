import io
from decimal import Decimal

from django.test import TestCase

from catalog.bakery_products_import import import_bakery_products_csv
from catalog.constants import BAKERY_CATEGORIES
from catalog.models import Product, ProductCategory


class BakeryProductsImportTests(TestCase):
    def test_import_creates_products_in_bakery_categories(self):
        csv_text = (
            "id,name,category,selling_price,remaining_qty,tax_rate,is_active\n"
            "1,PLAIN CROISSANTS,MANUFACTURED ITEMS,2,15,15.5,TRUE\n"
            "2,CHICKEN PIE,MANUFACTURED ITEMS,6,15,15.5,TRUE\n"
        )
        stats = import_bakery_products_csv(io.BytesIO(csv_text.encode("utf-8")))

        self.assertEqual(stats["products_created"], 2)
        croissant = Product.objects.get(name="PLAIN CROISSANTS")
        self.assertEqual(croissant.category.name, "Breads & pastries")
        pie = Product.objects.get(name="CHICKEN PIE")
        self.assertEqual(pie.category.name, "Savory")

    def test_import_does_not_overwrite_pos_product_by_legacy_id(self):
        pos_category = ProductCategory.objects.create(name="Coffee")
        pos_product = Product.objects.create(
            name="Americano",
            category=pos_category,
            selling_price=Decimal("4"),
        )
        csv_text = (
            "id,name,category,selling_price,remaining_qty,tax_rate,is_active\n"
            f"{pos_product.id},PLAIN CROISSANTS,MANUFACTURED ITEMS,2,15,15.5,TRUE\n"
        )
        stats = import_bakery_products_csv(io.BytesIO(csv_text.encode("utf-8")))

        self.assertEqual(stats["products_created"], 1)
        pos_product.refresh_from_db()
        self.assertEqual(pos_product.name, "Americano")
        self.assertTrue(Product.objects.filter(name="PLAIN CROISSANTS").exists())

    def test_import_replace_deactivates_missing_bakery_products(self):
        category = ProductCategory.objects.create(name="Breads & pastries")
        Product.objects.create(
            name="Old Roll",
            category=category,
            selling_price=Decimal("1"),
        )
        csv_text = (
            "id,name,category,selling_price,remaining_qty,tax_rate,is_active\n"
            "1,BAGUETTE,MANUFACTURED ITEMS,1.5,15,0,TRUE\n"
        )
        stats = import_bakery_products_csv(
            io.BytesIO(csv_text.encode("utf-8")),
            replace=True,
        )

        self.assertEqual(stats["deactivated"], 1)
        self.assertFalse(Product.objects.get(name="Old Roll").is_active)
        self.assertTrue(Product.objects.get(name="BAGUETTE").is_active)

    def test_import_skips_rows_without_name_or_price(self):
        csv_text = (
            "id,name,category,selling_price,remaining_qty,tax_rate,is_active\n"
            ",,MANUFACTURED ITEMS,,15,0,TRUE\n"
            "2,FINANCIERS,MANUFACTURED ITEMS,,15,15.5,TRUE\n"
            "3,BAGUETTE,MANUFACTURED ITEMS,1.5,15,0,TRUE\n"
        )
        stats = import_bakery_products_csv(io.BytesIO(csv_text.encode("utf-8")))

        self.assertEqual(stats["skipped_rows"], 2)
        self.assertEqual(stats["products_created"], 1)
        self.assertEqual(
            Product.objects.filter(category__name__in=BAKERY_CATEGORIES).count(),
            1,
        )
