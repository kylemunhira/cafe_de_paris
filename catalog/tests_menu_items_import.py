import openpyxl
from decimal import Decimal
from django.test import TestCase

from catalog.menu_items_import import import_menu_items, parse_menu_items_rows
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

    def test_import_menu_items_from_workbook(self):
        workbook = openpyxl.load_workbook("NEW DATA BASE CDP.xlsx", read_only=True, data_only=True)
        rows = list(workbook["MENU ITEMS "].iter_rows(values_only=True))
        stats = import_menu_items(rows)

        tax_rate = get_inclusive_tax_rate()
        self.assertGreater(stats["items_parsed"], 80)
        self.assertTrue(ProductCategory.objects.filter(name="Coffee").exists())
        self.assertTrue(Product.objects.filter(name="French Toast", category__name="All Day Breakfast").exists())
        self.assertTrue(
            Product.objects.filter(
                name="Cappuccino (Tall)",
                category__name="Coffee",
                selling_price=Decimal("4"),
                tax_rate=tax_rate,
            ).exists()
        )
