from decimal import Decimal

from django.core.management.base import BaseCommand

from branches.models import Branch, BranchType
from catalog.models import Product, ProductCategory
from bakery.models import Recipe
from inventory.models import BranchInventory


class Command(BaseCommand):
    help = "Seed demo branches, products, and starter inventory."

    def handle(self, *args, **options):
        hq, _ = Branch.objects.get_or_create(
            name="Café de Paris HQ",
            defaults={
                "location": "Harare",
                "branch_type": BranchType.HQ,
            },
        )
        bakery, _ = Branch.objects.get_or_create(
            name="Central Bakery",
            defaults={
                "location": "Harare Industrial",
                "branch_type": BranchType.BAKERY,
            },
        )
        stores, _ = Branch.objects.get_or_create(
            name="Central Stores",
            defaults={
                "location": "Harare",
                "branch_type": BranchType.STORES,
                "code": "STR",
            },
        )
        branch, _ = Branch.objects.get_or_create(
            name="Café de Paris Avondale",
            defaults={
                "location": "Avondale, Harare",
                "branch_type": BranchType.BRANCH,
            },
        )

        categories = {
            "Coffee": ["Espresso", "Cappuccino", "Americano", "Latte"],
            "Pastries": ["Croissant", "Pain au Chocolat", "Muffin"],
            "Ingredients": ["Coffee Beans", "Milk", "Flour", "Butter"],
        }

        products = []
        for category_name, product_names in categories.items():
            category, _ = ProductCategory.objects.get_or_create(name=category_name)
            prices = {
                "Coffee": Decimal("3.50"),
                "Pastries": Decimal("2.75"),
                "Ingredients": Decimal("5.00"),
            }
            for product_name in product_names:
                product, _ = Product.objects.get_or_create(
                    name=product_name,
                    category=category,
                    defaults={"selling_price": prices[category_name]},
                )
                products.append(product)

        for product in products:
            if product.category.name == "Ingredients":
                BranchInventory.objects.get_or_create(
                    branch=bakery,
                    product=product,
                    defaults={"quantity": Decimal("100")},
                )
            elif product.category.name == "Pastries":
                BranchInventory.objects.get_or_create(
                    branch=bakery,
                    product=product,
                    defaults={"quantity": Decimal("50")},
                )
                BranchInventory.objects.get_or_create(
                    branch=branch,
                    product=product,
                    defaults={"quantity": Decimal("10")},
                )
            else:
                BranchInventory.objects.get_or_create(
                    branch=branch,
                    product=product,
                    defaults={"quantity": Decimal("25")},
                )

        product_by_name = {product.name: product for product in products}
        recipe_lines = [
            ("Croissant", "Flour", Decimal("0.30")),
            ("Croissant", "Butter", Decimal("0.15")),
            ("Pain au Chocolat", "Flour", Decimal("0.35")),
            ("Pain au Chocolat", "Butter", Decimal("0.20")),
            ("Muffin", "Flour", Decimal("0.25")),
            ("Muffin", "Butter", Decimal("0.08")),
        ]
        recipes_created = 0
        for output_name, ingredient_name, qty in recipe_lines:
            output = product_by_name.get(output_name)
            ingredient = product_by_name.get(ingredient_name)
            if output and ingredient:
                _, created = Recipe.objects.get_or_create(
                    product=output,
                    ingredient=ingredient,
                    defaults={"quantity_required": qty},
                )
                if created:
                    recipes_created += 1

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write(f"  HQ: {hq.name}")
        self.stdout.write(f"  Bakery: {bakery.name}")
        self.stdout.write(f"  Branch: {branch.name}")
        self.stdout.write(f"  Products: {len(products)}")
        self.stdout.write(f"  Recipe lines: {recipes_created}")
