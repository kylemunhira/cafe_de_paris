from catalog.constants import BAKERY_CATEGORIES
from catalog.costings_import import import_costings
from catalog.costings_parse import normalize_key

PRODUCT_CATEGORY_MAP = {
    "CATS TONGUE": "Breads & pastries",
    "CIABATTA": "Breads & pastries",
    "CIABBATTA": "Breads & pastries",
    "BAGUETTE": "Breads & pastries",
    "SOURDOUGH": "Breads & pastries",
    "BRIOCHE": "Breads & pastries",
    "CROSSAINT": "Breads & pastries",
    "CROISSANT": "Breads & pastries",
    "HOT CROSS BUN": "Breads & pastries",
    "BATONNE": "Breads & pastries",
    "MBATTONES": "Breads & pastries",
    "CRAQUELIN": "Breads & pastries",
    "CHOUX": "Breads & pastries",
    "PUFF PASTRY": "Breads & pastries",
    "GALETTE": "Breads & pastries",
    "GOUYERE": "Breads & pastries",
    "GRUYERE": "Breads & pastries",
    "CHEESECAKE": "Cakes & desserts",
    "CHOCOLATE CAKE": "Cakes & desserts",
    "CHOOCOLATE CAKE": "Cakes & desserts",
    "CHOC ORANGE CAKE": "Cakes & desserts",
    "LEMON CAKE": "Cakes & desserts",
    "BUCHE DE NOEL": "Cakes & desserts",
    "MILLEFEUILLE": "Cakes & desserts",
    "MADELINE": "Cakes & desserts",
    "CHELSEA": "Cakes & desserts",
    "TUILES AUX AMANDES": "Cakes & desserts",
    "CHOCOALTE TART": "Cakes & desserts",
    "CHOCOLATE TART": "Cakes & desserts",
    "CHICKEN PIE": "Savory",
    "CHICEKN PIE": "Savory",
    "BEEF PIE": "Savory",
    "CHEESE PIE": "Savory",
    "ALMOND CREAM": "Components",
    "PASTRY CREAM": "Components",
    "BEEF FILLING": "Components",
    "CHICKEN FILLING": "Components",
    "CHOC CHIP": "Components",
    "CHEESE PIE FILLING": "Components",
    "ALMOND CROSSAINT": "Components",
    "CREPE": "Components",
    "BROWNIES": "Components",
}


def classify_product(title):
    key = normalize_key(title)
    for prefix, category in sorted(PRODUCT_CATEGORY_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if key.startswith(prefix) or prefix in key:
            return category
    return "Components"


def import_bakery_costings(rows):
    return import_costings(
        rows,
        product_categories=BAKERY_CATEGORIES,
        classify_product=classify_product,
    )
