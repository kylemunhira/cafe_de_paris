from .constants import (
    ALL_INGREDIENT_CATEGORIES,
    ARCHIVED_CATEGORY,
)

# Internal sub-recipes are not sold directly on POS terminals.
POS_EXCLUDED_CATEGORIES = ALL_INGREDIENT_CATEGORIES | {
    ARCHIVED_CATEGORY,
    "Components",
    "Extras",
}


def pos_catalog_products(queryset=None):
    """Menu items and bakery finished goods sold on POS terminals."""
    from .models import Product

    qs = queryset if queryset is not None else Product.objects.all()
    return (
        qs.filter(
            is_active=True,
            category__is_asset=False,
            category__show_on_pos=True,
        )
        .exclude(category__name__in=POS_EXCLUDED_CATEGORIES)
        .exclude(name__istartswith="add ")
        .select_related("category")
        .prefetch_related("addon_group_links__group__addons")
        .order_by("name")
    )


def pos_catalog_categories(queryset=None):
    """Categories marked to show on POS that contain at least one sellable product."""
    from .models import ProductCategory

    category_ids = pos_catalog_products().values_list("category_id", flat=True).distinct()
    qs = queryset if queryset is not None else ProductCategory.objects.all()
    return qs.filter(id__in=category_ids, show_on_pos=True).order_by("name")
