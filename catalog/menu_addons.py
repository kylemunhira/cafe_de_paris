from decimal import Decimal

from django.db import transaction

from catalog.models import MenuAddon, MenuAddonGroup, MenuAddonSelectionType, Product, ProductMenuAddonGroup

# Prices aligned with csvdata/menu_items.csv where available.
ADDON_GROUP_DEFINITIONS = [
    {
        "name": "Coffee Extras",
        "selection_type": MenuAddonSelectionType.MULTIPLE,
        "sort_order": 10,
        "addons": [
            ("Add Hot Milk", Decimal("1"), Decimal("15.5")),
            ("Add Oat Milk", Decimal("1"), Decimal("0")),
            ("Add Almond Milk", Decimal("1"), Decimal("0")),
            ("Add Caramel Syrup", Decimal("1"), Decimal("0")),
            ("Add Hazelnut Syrup", Decimal("1"), Decimal("0")),
            ("Add Vanilla Syrup", Decimal("1"), Decimal("0")),
        ],
    },
    {
        "name": "Extras",
        "selection_type": MenuAddonSelectionType.MULTIPLE,
        "sort_order": 20,
        "addons": [
            ("Add Macon", Decimal("2"), Decimal("15.5")),
            ("Add Egg", Decimal("1"), Decimal("15.5")),
            ("Add Mushroom", Decimal("3"), Decimal("15.5")),
            ("Add Sausage", Decimal("3"), Decimal("15.5")),
            ("Add Cheese", Decimal("3"), Decimal("15.5")),
            ("Add Avo", Decimal("2"), Decimal("15.5")),
            ("Add Tomato", Decimal("1"), Decimal("15.5")),
            ("Add Brioche Slice", Decimal("2"), Decimal("15.5")),
            ("Add Veggie", Decimal("2"), Decimal("15.5")),
            ("Add Mushroom Sauce", Decimal("3"), Decimal("15.5")),
            ("Add Pepper Sauce", Decimal("3"), Decimal("15.5")),
            ("Add Chicken", Decimal("3"), Decimal("15.5")),
            ("Add Beef", Decimal("2"), Decimal("15.5")),
            ("Add Salmon", Decimal("3"), Decimal("15.5")),
            ("Add Ice Cream", Decimal("2"), Decimal("15.5")),
        ],
    },
    {
        "name": "Egg Options",
        "selection_type": MenuAddonSelectionType.SINGLE,
        "sort_order": 30,
        "addons": [
            ("Scrambled", Decimal("0"), Decimal("15.5")),
            ("Fried Sunny Side", Decimal("0"), Decimal("15.5")),
            ("Turn Over Easy", Decimal("0"), Decimal("15.5")),
            ("Turnover Med", Decimal("0"), Decimal("15.5")),
            ("Poached Soft", Decimal("0"), Decimal("15.5")),
            ("Med", Decimal("0"), Decimal("15.5")),
            ("Well Done", Decimal("0"), Decimal("15.5")),
            ("Boiled Soft", Decimal("0"), Decimal("15.5")),
            ("Boiled Med", Decimal("0"), Decimal("15.5")),
            ("Boiled Well Done", Decimal("0"), Decimal("15.5")),
            ("Turnover Welldone", Decimal("0"), Decimal("15.5")),
        ],
    },
    {
        "name": "Meat Option",
        "selection_type": MenuAddonSelectionType.SINGLE,
        "sort_order": 40,
        "addons": [
            ("Rare", Decimal("0"), Decimal("15.5")),
            ("Rare / Med", Decimal("0"), Decimal("15.5")),
            ("Medium", Decimal("0"), Decimal("15.5")),
            ("Medium / Welldone", Decimal("0"), Decimal("15.5")),
            ("Welldone", Decimal("0"), Decimal("15.5")),
        ],
    },
]

CATEGORY_ADDON_GROUPS = {
    "Coffee": ["Coffee Extras"],
    "All Day Breakfast1": ["Egg Options", "Extras"],
    "Cafe Classics": ["Extras"],
    "Cafe Plates": ["Meat Option", "Extras"],
    "Panini": ["Extras"],
    "Waffles ": ["Extras"],
    "Sweet Crepe ": ["Extras"],
    "Savory": ["Extras"],
    "Galette ": ["Extras"],
}

PRODUCT_NAME_ADDON_GROUPS = {
    "omelette": ["Egg Options", "Extras"],
    "eggs": ["Egg Options", "Extras"],
    "benedict": ["Egg Options", "Extras"],
    "steak": ["Meat Option", "Extras"],
    "beef": ["Meat Option", "Extras"],
}


def _group_names_for_product(product):
    names = set(CATEGORY_ADDON_GROUPS.get(product.category.name, []))
    lowered = product.name.lower()
    for keyword, groups in PRODUCT_NAME_ADDON_GROUPS.items():
        if keyword in lowered:
            names.update(groups)
    return sorted(names)


def seed_menu_addons(*, link_products=True):
    stats = {"groups_created": 0, "addons_created": 0, "links_created": 0}

    with transaction.atomic():
        group_by_name = {}
        for index, definition in enumerate(ADDON_GROUP_DEFINITIONS):
            group, created = MenuAddonGroup.objects.update_or_create(
                name=definition["name"],
                defaults={
                    "selection_type": definition["selection_type"],
                    "sort_order": definition.get("sort_order", index * 10),
                },
            )
            if created:
                stats["groups_created"] += 1
            group_by_name[group.name] = group

            for addon_index, (name, price, tax_rate) in enumerate(definition["addons"]):
                addon, created = MenuAddon.objects.update_or_create(
                    group=group,
                    name=name,
                    defaults={
                        "selling_price": price,
                        "tax_rate": tax_rate,
                        "sort_order": addon_index * 10,
                        "is_active": True,
                    },
                )
                if created:
                    stats["addons_created"] += 1

        if link_products:
            pos_products = Product.objects.filter(is_active=True).select_related("category")
            for product in pos_products:
                if product.category.name == "Extras":
                    continue
                if product.name.lower().startswith("add "):
                    continue

                for group_name in _group_names_for_product(product):
                    group = group_by_name.get(group_name)
                    if not group:
                        continue
                    _, created = ProductMenuAddonGroup.objects.get_or_create(
                        product=product,
                        group=group,
                    )
                    if created:
                        stats["links_created"] += 1

    return stats
