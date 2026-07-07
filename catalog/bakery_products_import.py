from decimal import Decimal

from django.db import transaction

from catalog.bakery_import import classify_product
from catalog.constants import BAKERY_CATEGORIES
from catalog.costings_parse import normalize_key, normalize_name
from catalog.csv_io import _open_csv_reader, _parse_bool, _parse_decimal
from catalog.models import Product, ProductCategory
from orders.tax import get_inclusive_tax_rate

BAKERY_PRODUCTS_CSV_DEFAULT = "csvdata/Backerproducts.csv"

FINISHED_GOOD_CATEGORY_KEYWORDS = {
    "Cakes & desserts": (
        "CAKE",
        "TART",
        "ECLAIR",
        "ÉCLAIR",
        "MACAROON",
        "MERINGUE",
        "FRAISIER",
        "PROFITEROLE",
        "CHEESECAKE",
        "BREST",
        "MILLIE",
        "FEUILLE",
        "CROQUEMBOUCHE",
        "CROQUMBOUCHE",
        "DOUGHNUT",
        "MADELINE",
        "MADELEINE",
        "MERVEILLEUX",
        "FLAN",
        "GALETTE",
        "HONOURE",
        "BROWNIE",
        "PUDDING",
        "COOKIE",
        "TUILE",
        "EASTER CAKE",
    ),
    "Savory": (
        "PIE",
        "BAGUETTE",
        "BAGUET",
        "ROLL",
        "PANINI",
        "PITA",
        "VOL AU VENT",
        "HOT CROSS",
        "SAUSAGE",
    ),
}


def classify_manufactured_product(name):
    """Map finished bakery goods to transferable categories."""
    category = classify_product(name)
    if category != "Components":
        return category

    key = normalize_key(name)
    for category_name, keywords in FINISHED_GOOD_CATEGORY_KEYWORDS.items():
        if any(keyword in key for keyword in keywords):
            return category_name
    return "Breads & pastries"


def _normalize_bakery_item(item, *, default_tax_rate):
    name = normalize_name(item["name"])
    return {
        "name": name,
        "category": classify_manufactured_product(name),
        "selling_price": item["selling_price"],
        "remaining_qty": item.get("remaining_qty"),
        "tax_rate": item["tax_rate"] if item.get("tax_rate") is not None else default_tax_rate,
        "is_active": item.get("is_active", True),
        "legacy_id": (item.get("legacy_id") or "").strip() or None,
    }


def _dedupe_bakery_items(items):
    by_name = {}
    for item in items:
        by_name[normalize_name(item["name"]).upper()] = item
    return list(by_name.values())


def parse_bakery_products_csv(file_obj):
    reader = _open_csv_reader(file_obj)
    if not reader.fieldnames:
        return [], []

    normalized_headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    name_header = normalized_headers.get("name")
    if not name_header:
        return [], []

    default_tax_rate = get_inclusive_tax_rate()
    items = []
    skipped = []

    for row_num, row in enumerate(reader, start=2):
        if not any(str(value).strip() for value in row.values() if value is not None):
            continue

        name = normalize_name(row.get(name_header, ""))
        if not name:
            skipped.append({"row": row_num, "message": "name is required"})
            continue

        try:
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
            legacy_id = str(row.get(id_header, "")).strip() if id_header else ""

            items.append(
                _normalize_bakery_item(
                    {
                        "name": name,
                        "selling_price": selling_price,
                        "remaining_qty": remaining_qty,
                        "tax_rate": tax_rate,
                        "is_active": is_active,
                        "legacy_id": legacy_id,
                    },
                    default_tax_rate=default_tax_rate,
                )
            )
        except ValueError as exc:
            skipped.append({"row": row_num, "message": str(exc)})

    return _dedupe_bakery_items(items), skipped


def _find_bakery_product(name, category_name, legacy_id=None):
    if legacy_id:
        try:
            product = Product.objects.select_related("category").get(pk=int(legacy_id))
            if product.category.name in BAKERY_CATEGORIES:
                return product
        except (ValueError, Product.DoesNotExist):
            pass

    product = Product.objects.filter(category__name=category_name, name=name).first()
    if product:
        return product

    return Product.objects.filter(category__name__in=BAKERY_CATEGORIES, name=name).first()


def import_bakery_products_from_list(items, *, replace=False):
    stats = {
        "items_parsed": len(items),
        "categories_created": 0,
        "products_created": 0,
        "products_updated": 0,
        "deactivated": 0,
        "skipped_rows": 0,
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
            product = _find_bakery_product(
                item["name"],
                item["category"],
                legacy_id=item.get("legacy_id"),
            )

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
            names_in_csv = {normalize_name(item["name"]).upper() for item in items}
            to_deactivate = [
                product.id
                for product in Product.objects.filter(
                    is_active=True,
                    category__name__in=BAKERY_CATEGORIES,
                ).select_related("category")
                if normalize_name(product.name).upper() not in names_in_csv
            ]
            if to_deactivate:
                stats["deactivated"] = Product.objects.filter(id__in=to_deactivate).update(
                    is_active=False
                )

    return stats


def import_bakery_products_csv(file_obj, *, replace=False):
    items, skipped = parse_bakery_products_csv(file_obj)
    stats = import_bakery_products_from_list(items, replace=replace)
    stats["skipped_rows"] = len(skipped)
    stats["skipped"] = skipped
    return stats
