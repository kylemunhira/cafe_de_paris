import re
from decimal import Decimal, InvalidOperation

from catalog.constants import JUNK_INGREDIENT_NAMES, SKIP_RECIPE_LABELS


def normalize_name(value):
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    return text


def normalize_key(value):
    return normalize_name(value).upper()


def is_junk_ingredient(name):
    key = normalize_key(name)
    if not key or key in JUNK_INGREDIENT_NAMES:
        return True
    if key.replace(".", "", 1).isdigit():
        return True
    if re.match(r"^\d+\s", key):
        return True
    if "PORTION" in key or " USD" in key or key.endswith(" PIES"):
        return True
    return False


def parse_decimal(value):
    if value is None:
        return None
    if isinstance(value, str) and value.strip().startswith("#"):
        return None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return amount


def parse_costing_sheet_rows(rows):
    recipes = []
    for row_index, row in enumerate(rows):
        for col_index, cell in enumerate(row):
            if cell != "Item":
                continue

            title = None
            for lookback in range(1, 4):
                prior_row = row_index - lookback
                if prior_row < 0 or col_index >= len(rows[prior_row]):
                    continue
                candidate = rows[prior_row][col_index]
                if not candidate:
                    continue
                text = normalize_name(candidate)
                if text and text not in SKIP_RECIPE_LABELS:
                    title = text
                    break
            if not title:
                continue

            ingredients = []
            sales_price = None
            scan_row = row_index + 1
            while scan_row < len(rows):
                if col_index >= len(rows[scan_row]):
                    break

                block = [
                    rows[scan_row][col_index + offset]
                    if col_index + offset < len(rows[scan_row])
                    else None
                    for offset in range(6)
                ]
                label = normalize_name(block[0])

                for offset, value in enumerate(block):
                    if normalize_name(value) == "Sales Price":
                        price_value = block[offset + 2] if offset + 2 < len(block) else None
                        parsed_price = parse_decimal(price_value)
                        if parsed_price is not None:
                            sales_price = parsed_price

                if label.startswith("Total Cost") or label in {"Cost Of Sales%", "GP%"}:
                    scan_row += 1
                    continue
                if label in SKIP_RECIPE_LABELS or label.startswith("Total"):
                    break
                if not label:
                    scan_row += 1
                    continue

                quantity = parse_decimal(block[3])
                unit_cost = parse_decimal(block[2])
                if quantity is None or quantity <= 0:
                    scan_row += 1
                    continue
                if is_junk_ingredient(label):
                    scan_row += 1
                    continue

                ingredients.append(
                    {
                        "name": label,
                        "unit_cost": unit_cost,
                        "quantity": quantity,
                    }
                )
                scan_row += 1

            if ingredients:
                recipes.append(
                    {
                        "title": title,
                        "sales_price": sales_price,
                        "ingredients": ingredients,
                    }
                )
    return recipes


def dedupe_recipes(recipes):
    deduped = {}
    for recipe in recipes:
        key = normalize_key(recipe["title"])
        current = deduped.get(key)
        if current is None or len(recipe["ingredients"]) > len(current["ingredients"]):
            deduped[key] = recipe
    return list(deduped.values())
