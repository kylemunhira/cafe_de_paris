import csv
import io
from decimal import Decimal

from django.db import transaction

from catalog.costings_parse import normalize_name, parse_decimal
from catalog.csv_io import _open_csv_reader, _parse_bool, _parse_decimal
from catalog.models import Product, ProductCategory
from catalog.pos_catalog import POS_EXCLUDED_CATEGORIES, pos_catalog_products
from orders.tax import get_inclusive_tax_rate

MENU_ITEMS_SHEET = "MENU ITEMS "
MENU_ITEMS_CSV_DEFAULT = "csvdata/menu_items.csv"
MENU_ITEMS_CSV_HEADERS = [
    "ch",
    "name",
    "category",
    "selling_price",
    "remaining_qty",
    "tax_rate",
    "is_active",
    "id",
]


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


def _normalize_menu_item(item, *, default_tax_rate):
    return {
        "category": normalize_name(item["category"]),
        "name": normalize_name(item["name"]),
        "selling_price": item["selling_price"],
        "remaining_qty": item.get("remaining_qty"),
        "tax_rate": item["tax_rate"] if item.get("tax_rate") is not None else default_tax_rate,
        "is_active": item.get("is_active", True),
        "product_id": (item.get("product_id") or "").strip() or None,
    }


def _dedupe_menu_items(items):
    """Keep the last row for each category + name pair."""
    by_key = {}
    for item in items:
        by_key[(item["category"], item["name"])] = item
    return list(by_key.values())


def parse_menu_items_csv(file_obj):
    reader = _open_csv_reader(file_obj)

    if not reader.fieldnames:
        return []

    normalized_headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    category_header = normalized_headers.get("ch") or normalized_headers.get("category")
    name_header = normalized_headers.get("name")
    if not category_header or not name_header:
        return []

    default_tax_rate = get_inclusive_tax_rate()
    items = []
    for row in reader:
        category_name = normalize_name(row.get(category_header, ""))
        name = normalize_name(row.get(name_header, ""))
        if not category_name or not name:
            continue

        selling_price = _parse_decimal(
            row.get(normalized_headers.get("selling_price", "selling_price")),
            "selling_price",
            required=True,
            min_value=Decimal("0"),
        )
        remaining_qty = _parse_decimal(
            row.get(normalized_headers.get("remaining_qty", "remaining_qty")),
            "remaining_qty",
            min_value=Decimal("0"),
        )
        tax_rate = _parse_decimal(
            row.get(normalized_headers.get("tax_rate", "tax_rate")),
            "tax_rate",
            min_value=Decimal("0"),
            max_value=Decimal("100"),
        )
        is_active = _parse_bool(row.get(normalized_headers.get("is_active", "is_active")))

        id_header = normalized_headers.get("id")
        product_id = str(row.get(id_header, "")).strip() if id_header else ""

        items.append(
            _normalize_menu_item(
                {
                    "category": category_name,
                    "name": name,
                    "selling_price": selling_price,
                    "remaining_qty": remaining_qty,
                    "tax_rate": tax_rate,
                    "is_active": is_active,
                    "product_id": product_id,
                },
                default_tax_rate=default_tax_rate,
            )
        )

    deduped = _dedupe_menu_items(items)
    seen_ids = set()
    for item in deduped:
        product_id = item.get("product_id")
        if not product_id:
            continue
        if product_id in seen_ids:
            item["product_id"] = None
        else:
            seen_ids.add(product_id)

    return deduped


def import_menu_items_from_list(items, *, replace=False):
    default_tax_rate = get_inclusive_tax_rate()
    normalized_items = [
        _normalize_menu_item(item, default_tax_rate=default_tax_rate) for item in items
    ]
    stats = {
        "items_parsed": len(normalized_items),
        "categories_created": 0,
        "products_created": 0,
        "products_updated": 0,
        "deactivated": 0,
    }

    with transaction.atomic():
        category_by_name = {}
        for item in normalized_items:
            category_name = item["category"]
            if category_name not in category_by_name:
                category, created = ProductCategory.objects.get_or_create(name=category_name)
                category_by_name[category_name] = category
                if created:
                    stats["categories_created"] += 1

        for item in normalized_items:
            category = category_by_name[item["category"]]
            product = None
            product_id = item.get("product_id")
            if product_id:
                try:
                    product = Product.objects.get(pk=int(product_id))
                except (ValueError, Product.DoesNotExist):
                    product = Product.objects.filter(category=category, name=item["name"]).first()
            else:
                product = Product.objects.filter(category=category, name=item["name"]).first()

            if product:
                updates = []
                if product.name != item["name"]:
                    product.name = item["name"]
                    updates.append("name")
                if product.category_id != category.id:
                    product.category = category
                    updates.append("category")
                if product.selling_price != item["selling_price"]:
                    product.selling_price = item["selling_price"]
                    updates.append("selling_price")
                if item["remaining_qty"] is not None and product.remaining_qty != item["remaining_qty"]:
                    product.remaining_qty = item["remaining_qty"]
                    updates.append("remaining_qty")
                if product.tax_rate != item["tax_rate"]:
                    product.tax_rate = item["tax_rate"]
                    updates.append("tax_rate")
                if product.is_active != item["is_active"]:
                    product.is_active = item["is_active"]
                    updates.append("is_active")
                if updates:
                    product.save(update_fields=updates)
                    stats["products_updated"] += 1
            else:
                Product.objects.create(
                    name=item["name"],
                    category=category,
                    selling_price=item["selling_price"],
                    remaining_qty=item["remaining_qty"] or Decimal("0"),
                    tax_rate=item["tax_rate"],
                    is_active=item["is_active"],
                )
                stats["products_created"] += 1

        if replace:
            keys_in_csv = {(item["category"], item["name"]) for item in normalized_items}
            pos_products = (
                Product.objects.filter(is_active=True, category__is_asset=False)
                .exclude(category__name__in=POS_EXCLUDED_CATEGORIES)
                .select_related("category")
            )
            to_deactivate = [
                product.id
                for product in pos_products
                if (product.category.name, product.name) not in keys_in_csv
            ]
            if to_deactivate:
                stats["deactivated"] = Product.objects.filter(id__in=to_deactivate).update(
                    is_active=False
                )

    return stats


def import_menu_items(rows, *, tax_rate=None, replace=False):
    items = parse_menu_items_rows(rows)
    if tax_rate is not None:
        for item in items:
            item["tax_rate"] = tax_rate
            item["is_active"] = True
    return import_menu_items_from_list(items, replace=replace)


def import_menu_items_csv(file_obj, *, replace=False):
    items = parse_menu_items_csv(file_obj)
    return import_menu_items_from_list(items, replace=replace)


def export_menu_items_csv():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=MENU_ITEMS_CSV_HEADERS)
    writer.writeheader()
    for product in pos_catalog_products():
        writer.writerow(
            {
                "ch": product.category.name,
                "name": product.name,
                "category": "",
                "selling_price": product.selling_price,
                "remaining_qty": product.remaining_qty,
                "tax_rate": product.tax_rate,
                "is_active": "TRUE" if product.is_active else "FALSE",
                "id": product.id,
            }
        )
    return output.getvalue()
