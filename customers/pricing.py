from decimal import Decimal

from bakery.costing import product_unit_cost

from .models import CustomerAccountType


def uses_cost_price(customer) -> bool:
    if customer is None:
        return False
    return customer.account_type in {
        CustomerAccountType.FAMILY,
        CustomerAccountType.STAFF,
    }


def unit_price_for_customer(product, customer) -> Decimal:
    """Return the unit price for a product given the order customer.

    Family/staff customers pay recipe cost when available; otherwise selling price.
    """
    if uses_cost_price(customer):
        cost = product_unit_cost(product)
        if cost is not None:
            return cost
    return product.selling_price
