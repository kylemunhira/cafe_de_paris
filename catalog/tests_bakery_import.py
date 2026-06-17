import openpyxl
from django.test import TestCase

from bakery.models import Recipe
from catalog.bakery_import import import_bakery_costings
from catalog.constants import INGREDIENTS_CATEGORY
from catalog.models import Product, ProductCategory


class BakeryImportTests(TestCase):
    def test_import_bakery_costings_from_workbook(self):
        workbook = openpyxl.load_workbook("CDP COSTINGS.xlsx", read_only=True, data_only=True)
        rows = list(workbook["BAKERY "].iter_rows(values_only=True))
        stats = import_bakery_costings(rows)

        self.assertGreater(stats["recipe_blocks"], 0)
        self.assertTrue(ProductCategory.objects.filter(name=INGREDIENTS_CATEGORY).exists())
        self.assertTrue(ProductCategory.objects.filter(name="Breads & pastries").exists())
        self.assertTrue(Product.objects.filter(category__name="Breads & pastries").exists())
        self.assertTrue(Product.objects.filter(category__name=INGREDIENTS_CATEGORY).exists())
        self.assertTrue(Recipe.objects.exists())
