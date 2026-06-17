from decimal import Decimal

from django.db import transaction

from bakery.models import Recipe
from catalog.constants import INGREDIENTS_CATEGORY
from catalog.costings_parse import (
    dedupe_recipes,
    is_junk_ingredient,
    normalize_key,
    normalize_name,
    parse_costing_sheet_rows,
)
from catalog.models import Product, ProductCategory


def ensure_categories(product_categories):
    ProductCategory.objects.get_or_create(name=INGREDIENTS_CATEGORY)
    for name in product_categories:
        ProductCategory.objects.get_or_create(name=name)


def get_or_create_product(name, category_name, *, selling_price=None):
    category = ProductCategory.objects.get(name=category_name)
    normalized = normalize_name(name)
    product = Product.objects.filter(name=normalized).first()
    created = False
    if product is None:
        product = Product.objects.create(
            name=normalized,
            category=category,
            selling_price=selling_price or Decimal("0"),
        )
        created = True
        return product, created

    updates = []
    if product.category_id != category.id:
        product.category = category
        updates.append("category")
    if selling_price is not None and product.selling_price != selling_price:
        product.selling_price = selling_price
        updates.append("selling_price")
    if updates:
        product.save(update_fields=updates)
    return product, created


def import_costings(rows, *, product_categories, classify_product):
    ensure_categories(product_categories)
    recipes = dedupe_recipes(parse_costing_sheet_rows(rows))

    stats = {
        "products_created": 0,
        "products_updated": 0,
        "ingredients_created": 0,
        "ingredients_updated": 0,
        "recipes_created": 0,
        "recipes_updated": 0,
        "recipe_blocks": len(recipes),
    }

    ingredient_costs = {}
    for recipe in recipes:
        for line in recipe["ingredients"]:
            key = normalize_key(line["name"])
            cost = line["unit_cost"]
            if cost is None:
                continue
            existing = ingredient_costs.get(key)
            if existing is None or cost > 0:
                ingredient_costs[key] = cost

    product_keys = {normalize_key(recipe["title"]) for recipe in recipes}

    with transaction.atomic():
        product_by_key = {}
        for recipe in recipes:
            category_name = classify_product(recipe["title"])
            product, created = get_or_create_product(
                recipe["title"],
                category_name,
                selling_price=recipe["sales_price"],
            )
            product_by_key[normalize_key(recipe["title"])] = product
            if created:
                stats["products_created"] += 1
            else:
                stats["products_updated"] += 1

        ingredient_category = ProductCategory.objects.get(name=INGREDIENTS_CATEGORY)
        ingredient_by_key = {}
        for recipe in recipes:
            for line in recipe["ingredients"]:
                key = normalize_key(line["name"])
                if key in product_keys:
                    continue
                if is_junk_ingredient(line["name"]):
                    continue
                if key in ingredient_by_key:
                    continue

                cost = ingredient_costs.get(key)
                ingredient, created = Product.objects.get_or_create(
                    name=normalize_name(line["name"]),
                    category=ingredient_category,
                    defaults={"selling_price": cost or Decimal("0")},
                )
                if not created and cost is not None and ingredient.selling_price != cost:
                    ingredient.selling_price = cost
                    ingredient.save(update_fields=["selling_price"])
                    stats["ingredients_updated"] += 1
                elif created:
                    stats["ingredients_created"] += 1
                else:
                    stats["ingredients_updated"] += 1
                ingredient_by_key[key] = ingredient

        for recipe in recipes:
            output_product = product_by_key[normalize_key(recipe["title"])]
            for line in recipe["ingredients"]:
                key = normalize_key(line["name"])
                if key in product_by_key:
                    ingredient_product = product_by_key[key]
                elif key in ingredient_by_key:
                    ingredient_product = ingredient_by_key[key]
                else:
                    continue

                recipe_obj, created = Recipe.objects.update_or_create(
                    product=output_product,
                    ingredient=ingredient_product,
                    defaults={"quantity_required": line["quantity"]},
                )
                if created:
                    stats["recipes_created"] += 1
                else:
                    stats["recipes_updated"] += 1

    return stats
