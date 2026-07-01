from .constants import INGREDIENTS_CATEGORY

# Internal sub-recipes are not sold directly on POS terminals.
POS_EXCLUDED_CATEGORIES = {
    INGREDIENTS_CATEGORY,
    "Components",
}


def pos_catalog_products(queryset=None):
    """Menu items and bakery finished goods sold on POS terminals."""
    from .models import Product

    qs = queryset if queryset is not None else Product.objects.all()
    return (
        qs.filter(is_active=True, category__is_asset=False)
        .exclude(category__name__in=POS_EXCLUDED_CATEGORIES)
        .select_related("category")
        .order_by("name")
    )
