INGREDIENTS_CATEGORY = "Ingredients"
BRANCH_INGREDIENTS_CATEGORY = "Branch Ingredients"
ARCHIVED_CATEGORY = "Archived"

ALL_INGREDIENT_CATEGORIES = frozenset({
    INGREDIENTS_CATEGORY,
    BRANCH_INGREDIENTS_CATEGORY,
})

BAKERY_CATEGORIES = {
    "Breads & pastries",
    "Cakes & desserts",
    "Savory",
    "Components",
}

# Finished bakery goods sold on POS and transferable to stores and branches.
# Components are internal sub-recipes; Ingredients are raw materials.
BAKERY_SELLABLE_CATEGORIES = {
    "Breads & pastries",
    "Cakes & desserts",
    "Savory",
}

# Legacy POS tabs and bakery categories — finished goods counted at the shop.
STOCK_TAKE_BAKERY_CATEGORIES = BAKERY_CATEGORIES | {
    "Croissants",
    "Desserts",
    "Confectionary",
    "Sweet Confessions",
    "Cafe Classics",
}


def is_bakery_transfer_product(product):
    return product.category.name in BAKERY_SELLABLE_CATEGORIES


def is_stock_take_bakery_product(product):
    """Finished bakery goods — grouped with shop stock."""
    return product.category.name in STOCK_TAKE_BAKERY_CATEGORIES


def ingredient_categories_for_branch_type(branch_type):
    """Which ingredient categories are stocked at a given branch type."""
    from branches.models import BranchType

    # Central bakery and central stores both hold bakery raw materials and
    # branch/kitchen supplies (cleaning, packaging, etc.) so stores can
    # transfer either category to the bakery.
    if branch_type == BranchType.BAKERY:
        return ALL_INGREDIENT_CATEGORIES
    if branch_type == BranchType.BRANCH:
        return frozenset({BRANCH_INGREDIENTS_CATEGORY})
    if branch_type == BranchType.STORES:
        return ALL_INGREDIENT_CATEGORIES
    return frozenset()


def is_ingredient_product(product):
    return product.category.name in ALL_INGREDIENT_CATEGORIES


def is_bakery_ingredient_product(product):
    return product.category.name == INGREDIENTS_CATEGORY


def is_branch_ingredient_product(product):
    return product.category.name == BRANCH_INGREDIENTS_CATEGORY


class StockTakeStation:
    KITCHEN = "kitchen"
    BAR = "bar"
    SHOP = "shop"


STOCK_TAKE_STATION_LABELS = {
    StockTakeStation.KITCHEN: "Kitchen",
    StockTakeStation.BAR: "Bar",
    StockTakeStation.SHOP: "Shop",
}

STOCK_TAKE_STATION_ORDER = (
    StockTakeStation.KITCHEN,
    StockTakeStation.BAR,
    StockTakeStation.SHOP,
)

# Branch/bakery ingredients tagged with these group categories are counted
# with shop stock (bottled drinks, retail beverages), not kitchen prep.
STOCK_TAKE_SHOP_GROUP_CATEGORIES = frozenset({
    "beverages",
})


def _group_category_name(product):
    group = getattr(product, "group_category", None)
    if group is None:
        return ""
    return (group.name or "").strip().casefold()


def is_stock_take_shop_grouped_ingredient(product):
    """Ingredient whose group_category should count under Shop."""
    if not is_ingredient_product(product):
        return False
    return _group_category_name(product) in STOCK_TAKE_SHOP_GROUP_CATEGORIES


def stock_take_station_for_product(product):
    """Prep area for stock-take grouping: ingredients, bar, or shop."""
    from catalog.models import PosStation

    if is_stock_take_shop_grouped_ingredient(product):
        return StockTakeStation.SHOP
    if is_ingredient_product(product):
        return StockTakeStation.KITCHEN
    if is_stock_take_bakery_product(product):
        return StockTakeStation.SHOP
    pos_station = (product.category.pos_station or "").strip()
    if pos_station == PosStation.BAR:
        return StockTakeStation.BAR
    if pos_station == PosStation.KITCHEN:
        return StockTakeStation.KITCHEN
    return StockTakeStation.SHOP


def stock_take_station_display_for_product(product):
    station = stock_take_station_for_product(product)
    return STOCK_TAKE_STATION_LABELS[station]


def is_bakery_manufactured_product(product):
    """Products made at the central bakery (finished goods and components)."""
    return product.category.name in BAKERY_CATEGORIES

KITCHEN_CATEGORIES = {
    "Breakfast",
    "Mains",
    "Sandwiches",
    "Burgers",
    "Salads",
    "Seafood",
    "Components",
}

SKIP_RECIPE_LABELS = {
    "Item",
    "UOM",
    "Unit Cost",
    "Quantity",
    "Cost",
    "Total Cost Ex VAT",
    "Total Cost incl VAT",
    "Sales Price",
    "Cost Of Sales%",
    "GP%",
    "GLUTEN FREE",
}

JUNK_INGREDIENT_NAMES = {
    "Item",
    "UOM",
    "Unit Cost",
    "Quantity",
    "Cost",
    "KG",
    "kg",
    "LT",
    "EACH",
    "EQUALS",
    "FILLING",
    "filling",
    "PACAKGIN",
    "HOC",
    "IBZ",
}
