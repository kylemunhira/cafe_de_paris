from catalog.constants import KITCHEN_CATEGORIES
from catalog.costings_import import import_costings
from catalog.costings_parse import normalize_key

KITCHEN_PRODUCT_CATEGORY_MAP = {
    "ENGLISH BREAKFAST": "Breakfast",
    "EGGS BENEDICT": "Breakfast",
    "FRENCH TOAST": "Breakfast",
    "OMLETTE": "Breakfast",
    "OMELETTE": "Breakfast",
    "SANDWICH": "Sandwiches",
    "SMOKED SALMON BAGEL": "Sandwiches",
    "CDP CLUB": "Sandwiches",
    "BURGER": "Burgers",
    "NICOISE": "Salads",
    "SALAD": "Salads",
    "FISH": "Seafood",
    "PRAWN": "Seafood",
    "SALMON": "Seafood",
    "OCEAN": "Seafood",
    "HOLLANDAISE": "Components",
    "HOLLANDNAISE": "Components",
    "BBQ SAUCE": "Components",
    "CHEESE PIE FILLING": "Components",
}


def classify_kitchen_product(title):
    key = normalize_key(title)
    for prefix, category in sorted(
        KITCHEN_PRODUCT_CATEGORY_MAP.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if key.startswith(prefix) or prefix in key:
            return category
    return "Mains"


def import_kitchen_costings(rows):
    return import_costings(
        rows,
        product_categories=KITCHEN_CATEGORIES,
        classify_product=classify_kitchen_product,
    )
