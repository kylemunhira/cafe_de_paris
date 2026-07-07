import csv
import io
from decimal import Decimal

from django.test import TestCase

from catalog.menu_items_import import (
    import_menu_items,
    import_menu_items_csv,
    parse_menu_items_csv,
    parse_menu_items_rows,
)
from catalog.models import Product, ProductCategory
from orders.tax import get_inclusive_tax_rate


class MenuItemsImportTests(TestCase):
    def test_parse_menu_items_rows_builds_size_variants(self):
        rows = [
            ("Category", "Item", "Size", "Price"),
            ("Coffee", "Cappuccino", "Tall", 4),
            ("Panini", "Beef Panini", None, 18),
        ]
        items = parse_menu_items_rows(rows)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["name"], "Cappuccino (Tall)")
        self.assertEqual(items[0]["category"], "Coffee")
        self.assertEqual(items[0]["selling_price"], Decimal("4"))
        self.assertEqual(items[1]["name"], "Beef Panini")

    def test_parse_menu_items_csv_reads_category_tax_and_id(self):
        csv_text = (
            "ch,name,category,selling_price,remaining_qty,tax_rate,is_active,id\n"
            "Coffee,Cappuccino (Tall),,4,15,0,TRUE,1377\n"
            "Panini,Beef Panini,,18,15,15.5,TRUE,\n"
        )
        items = parse_menu_items_csv(io.BytesIO(csv_text.encode("utf-8")))

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["category"], "Coffee")
        self.assertEqual(items[0]["tax_rate"], Decimal("0"))
        self.assertEqual(items[0]["product_id"], "1377")
        self.assertIsNone(items[1]["product_id"])

    def test_import_menu_items_csv_creates_and_updates(self):
        category = ProductCategory.objects.create(name="Coffee")
        existing = Product.objects.create(
            name="Cappuccino (Tall)",
            category=category,
            selling_price=Decimal("3"),
            tax_rate=Decimal("15.5"),
        )
        csv_text = (
            "ch,name,category,selling_price,remaining_qty,tax_rate,is_active,id\n"
            f"Coffee,Cappuccino (Tall),,4,15,0,TRUE,{existing.id}\n"
            "Coffee,Espresso (Short),,2,15,0,TRUE,\n"
        )
        stats = import_menu_items_csv(io.BytesIO(csv_text.encode("utf-8")))

        self.assertEqual(stats["products_created"], 1)
        self.assertEqual(stats["products_updated"], 1)
        existing.refresh_from_db()
        self.assertEqual(existing.selling_price, Decimal("4"))
        self.assertEqual(existing.tax_rate, Decimal("0"))
        self.assertTrue(Product.objects.filter(name="Espresso (Short)", category__name="Coffee").exists())

    def test_import_menu_items_csv_replace_deactivates_missing_products(self):
        coffee = ProductCategory.objects.create(name="Coffee")
        desserts = ProductCategory.objects.create(name="Desserts")
        Product.objects.create(name="Espresso (Short)", category=coffee, selling_price=Decimal("2"))
        Product.objects.create(name="Old Tart", category=desserts, selling_price=Decimal("5"))

        csv_text = (
            "ch,name,category,selling_price,remaining_qty,tax_rate,is_active,id\n"
            "Coffee,Espresso (Short),,2,15,0,TRUE,\n"
        )
        stats = import_menu_items_csv(
            io.BytesIO(csv_text.encode("utf-8")),
            replace=True,
        )

        self.assertEqual(stats["deactivated"], 1)
        self.assertTrue(Product.objects.get(name="Espresso (Short)").is_active)
        self.assertFalse(Product.objects.get(name="Old Tart").is_active)
