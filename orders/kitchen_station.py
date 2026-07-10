from catalog.models import PosStation


def resolve_kitchen_station_filter(user, requested_station=None):
    """Return kitchen/bar station filter for order lists, or '' for all items."""
    from accounts.branch_access import get_staff_kitchen_station, user_has_global_branch_access

    explicit = (requested_station or "").strip().lower()
    if explicit in PosStation.values:
        return explicit
    if user_has_global_branch_access(user):
        return ""
    return get_staff_kitchen_station(user)


def filter_orders_for_kitchen_station(queryset, station):
    """Keep open orders that include at least one item for this prep station."""
    if not station:
        return queryset
    return queryset.filter(items__product__category__pos_station=station).distinct()


def order_item_matches_kitchen_station(item, station):
    if not station:
        return True
    category = item.product.category
    return category.pos_station == station
