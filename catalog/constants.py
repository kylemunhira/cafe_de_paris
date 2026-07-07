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


def is_bakery_transfer_product(product):
    return product.category.name in BAKERY_SELLABLE_CATEGORIES


def ingredient_categories_for_branch_type(branch_type):
    """Which ingredient categories are stocked at a given branch type."""
    from branches.models import BranchType

    if branch_type == BranchType.BAKERY:
        return frozenset({INGREDIENTS_CATEGORY})
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
