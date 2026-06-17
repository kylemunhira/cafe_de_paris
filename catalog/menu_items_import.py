from decimal import Decimal

from django.db import transaction

from catalog.costings_parse import normalize_name, parse_decimal
from catalog.models import Product, ProductCategory
from orders.tax import get_inclusive_tax_rate

MENU_ITEMS_SHEET = "MENU ITEMS "


def build_product_name(item, size):
    name = normalize_name(item)
    size_text = normalize_name(size)
    if size_text:
        return f"{name} ({size_text})"
    return name


def parse_menu_items_rows(rows):
    if not rows:
        return []

    items = []
    for row in rows[1:]:
        if not row or len(row) < 4:
            continue

        category_name = normalize_name(row[0])
        item_name = normalize_name(row[1])
        if not category_name or not item_name:
            continue

        selling_price = parse_decimal(row[3])
        if selling_price is None:
            continue

        items.append(
            {
                "category": category_name,
                "name": build_product_name(item_name, row[2]),
                "selling_price": selling_price,
            }
        )
    return items


def import_menu_items(rows, *, tax_rate=None):
    if tax_rate is None:
        tax_rate = get_inclusive_tax_rate()

    items = parse_menu_items_rows(rows)
    stats = {
        "items_parsed": len(items),
        "categories_created": 0,
        "products_created": 0,
        "products_updated": 0,
    }

    with transaction.atomic():
        category_by_name = {}
        for item in items:
            category_name = item["category"]
            if category_name not in category_by_name:
                category, created = ProductCategory.objects.get_or_create(name=category_name)
                category_by_name[category_name] = category
                if created:
                    stats["categories_created"] += 1

        for item in items:
            category = category_by_name[item["category"]]
            product, created = Product.objects.get_or_create(
                name=item["name"],
                category=category,
                defaults={
                    "selling_price": item["selling_price"],
                    "tax_rate": tax_rate,
                    "is_active": True,
                },
            )
            if created:
                stats["products_created"] += 1
                continue

            updates = []
            if product.selling_price != item["selling_price"]:
                product.selling_price = item["selling_price"]
                updates.append("selling_price")
            if product.tax_rate != tax_rate:
                product.tax_rate = tax_rate
                updates.append("tax_rate")
            if not product.is_active:
                product.is_active = True
                updates.append("is_active")
            if updates:
                product.save(update_fields=updates)
                stats["products_updated"] += 1

    return stats
