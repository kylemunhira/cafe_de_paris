import openpyxl
from django.test import TestCase

from bakery.models import Recipe
from catalog.constants import INGREDIENTS_CATEGORY
from catalog.kitchen_import import import_kitchen_costings
from catalog.models import Product, ProductCategory


class KitchenImportTests(TestCase):
    def test_import_kitchen_costings_from_workbook(self):
        workbook = openpyxl.load_workbook("CDP COSTINGS.xlsx", read_only=True, data_only=True)
        rows = list(workbook["KITCHEN "].iter_rows(values_only=True))
        stats = import_kitchen_costings(rows)

        self.assertGreater(stats["recipe_blocks"], 0)
        self.assertTrue(ProductCategory.objects.filter(name=INGREDIENTS_CATEGORY).exists())
        self.assertTrue(ProductCategory.objects.filter(name="Mains").exists())
        self.assertTrue(ProductCategory.objects.filter(name="Breakfast").exists())
        self.assertTrue(Product.objects.filter(category__name="Mains").exists())
        self.assertTrue(Product.objects.filter(category__name=INGREDIENTS_CATEGORY).exists())
        self.assertTrue(Recipe.objects.exists())
