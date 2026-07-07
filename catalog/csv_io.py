import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .constants import INGREDIENTS_CATEGORY
from .models import Product, ProductCategory

CSV_HEADERS = [
    "id",
    "name",
    "category",
    "selling_price",
    "remaining_qty",
    "tax_rate",
    "is_active",
]

INGREDIENT_CSV_HEADERS = [
    "id",
    "name",
    "unit_cost",
    "remaining_qty",
    "is_active",
]


def export_products_csv():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()
    for product in Product.objects.select_related("category").order_by("name"):
        writer.writerow(
            {
                "id": product.id,
                "name": product.name,
                "category": product.category.name,
                "selling_price": product.selling_price,
                "remaining_qty": product.remaining_qty,
                "tax_rate": product.tax_rate,
                "is_active": "true" if product.is_active else "false",
            }
        )
    return output.getvalue()


def export_ingredients_csv():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=INGREDIENT_CSV_HEADERS)
    writer.writeheader()
    for product in (
        Product.objects.select_related("category")
        .filter(category__name=INGREDIENTS_CATEGORY)
        .order_by("name")
    ):
        writer.writerow(
            {
                "id": product.id,
                "name": product.name,
                "unit_cost": product.selling_price,
                "remaining_qty": product.remaining_qty,
                "is_active": "true" if product.is_active else "false",
            }
        )
    return output.getvalue()


def _parse_bool(value, default=True):
    if value is None or str(value).strip() == "":
        return default
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "y"):
        return True
    if normalized in ("false", "0", "no", "n"):
        return False
    raise ValueError(f"invalid is_active value: {value!r}")


def _parse_decimal(value, field_name, *, required=False, min_value=None, max_value=None):
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"{field_name} is required")
        return None
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc
    if min_value is not None and amount < min_value:
        raise ValueError(f"{field_name} must be {min_value} or greater")
    if max_value is not None and amount > max_value:
        raise ValueError(f"{field_name} must be {max_value} or less")
    return amount


def _parse_price(value):
    parsed = _parse_decimal(value, "selling_price", required=True, min_value=Decimal("0"))
    return parsed


def _open_csv_reader(file_obj):
    """Open a CSV DictReader, falling back to cp1252 when UTF-8 fails."""
    raw = file_obj.read()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return csv.DictReader(io.StringIO(raw.decode(encoding)))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, "unsupported encoding")


def import_products_csv(file_obj):
    try:
        reader = _open_csv_reader(file_obj)
    except UnicodeDecodeError as exc:
        return {"created": 0, "updated": 0, "errors": [{"row": 0, "message": "File must be UTF-8 or Windows-1252 encoded CSV"}]}

    if not reader.fieldnames:
        return {"created": 0, "updated": 0, "errors": [{"row": 0, "message": "CSV file is empty"}]}

    normalized_headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    missing = [h for h in ("name", "category", "selling_price") if h not in normalized_headers]
    if missing:
        return {
            "created": 0,
            "updated": 0,
            "errors": [{"row": 0, "message": f"Missing required columns: {', '.join(missing)}"}],
        }

    created = 0
    updated = 0
    errors = []

    with transaction.atomic():
        for row_num, row in enumerate(reader, start=2):
            if not any(str(v).strip() for v in row.values() if v is not None):
                continue

            try:
                name = str(row.get(normalized_headers.get("name", "name"), "")).strip()
                category_name = str(row.get(normalized_headers.get("category", "category"), "")).strip()
                if not name:
                    raise ValueError("name is required")
                if not category_name:
                    raise ValueError("category is required")

                price = _parse_price(row.get(normalized_headers.get("selling_price", "selling_price")))
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

                category, _ = ProductCategory.objects.get_or_create(name=category_name)

                id_header = normalized_headers.get("id")
                product_id = str(row.get(id_header, "")).strip() if id_header else ""

                if product_id:
                    try:
                        product = Product.objects.get(pk=int(product_id))
                    except (ValueError, Product.DoesNotExist) as exc:
                        raise ValueError(f"product id {product_id!r} not found") from exc
                    product.name = name
                    product.category = category
                    product.selling_price = price
                    if remaining_qty is not None:
                        product.remaining_qty = remaining_qty
                    if tax_rate is not None:
                        product.tax_rate = tax_rate
                    product.is_active = is_active
                    product.save()
                    updated += 1
                else:
                    Product.objects.create(
                        name=name,
                        category=category,
                        selling_price=price,
                        remaining_qty=remaining_qty or Decimal("0"),
                        tax_rate=tax_rate or Decimal("0"),
                        is_active=is_active,
                    )
                    created += 1
            except Exception as exc:
                errors.append({"row": row_num, "message": str(exc)})

        if errors:
            transaction.set_rollback(True)
            return {"created": 0, "updated": 0, "errors": errors}

    return {"created": created, "updated": updated, "errors": errors}


def import_ingredients_csv(file_obj):
    try:
        reader = _open_csv_reader(file_obj)
    except UnicodeDecodeError:
        return {"created": 0, "updated": 0, "errors": [{"row": 0, "message": "File must be UTF-8 or Windows-1252 encoded CSV"}]}

    if not reader.fieldnames:
        return {"created": 0, "updated": 0, "errors": [{"row": 0, "message": "CSV file is empty"}]}

    normalized_headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    missing = [h for h in ("name", "unit_cost") if h not in normalized_headers]
    if missing:
        return {
            "created": 0,
            "updated": 0,
            "errors": [{"row": 0, "message": f"Missing required columns: {', '.join(missing)}"}],
        }

    category, _ = ProductCategory.objects.get_or_create(name=INGREDIENTS_CATEGORY)
    created = 0
    updated = 0
    errors = []

    with transaction.atomic():
        for row_num, row in enumerate(reader, start=2):
            if not any(str(v).strip() for v in row.values() if v is not None):
                continue

            try:
                name = str(row.get(normalized_headers.get("name", "name"), "")).strip()
                if not name:
                    continue

                unit_cost = _parse_decimal(
                    row.get(normalized_headers.get("unit_cost", "unit_cost")),
                    "unit_cost",
                    required=True,
                    min_value=Decimal("0"),
                )
                remaining_qty = _parse_decimal(
                    row.get(normalized_headers.get("remaining_qty", "remaining_qty")),
                    "remaining_qty",
                    min_value=Decimal("0"),
                )
                is_active = _parse_bool(row.get(normalized_headers.get("is_active", "is_active")))

                id_header = normalized_headers.get("id")
                product_id = str(row.get(id_header, "")).strip() if id_header else ""

                product = None
                if product_id:
                    try:
                        product = Product.objects.get(
                            pk=int(product_id),
                            category=category,
                        )
                    except (ValueError, Product.DoesNotExist):
                        product = Product.objects.filter(category=category, name=name).first()
                else:
                    product = Product.objects.filter(category=category, name=name).first()

                if product:
                    product.name = name
                    product.selling_price = unit_cost
                    if remaining_qty is not None:
                        product.remaining_qty = remaining_qty
                    product.is_active = is_active
                    product.save()
                    updated += 1
                else:
                    Product.objects.create(
                        name=name,
                        category=category,
                        selling_price=unit_cost,
                        remaining_qty=remaining_qty or Decimal("0"),
                        is_active=is_active,
                    )
                    created += 1
            except Exception as exc:
                errors.append({"row": row_num, "message": str(exc)})

        if errors:
            transaction.set_rollback(True)
            return {"created": 0, "updated": 0, "errors": errors}

    return {"created": created, "updated": updated, "errors": errors}
