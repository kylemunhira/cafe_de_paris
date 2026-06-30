from collections import defaultdict
from decimal import Decimal

from bakery.models import Recipe


def product_unit_cost(product) -> Decimal | None:
    recipes = Recipe.objects.filter(product=product).select_related("ingredient")
    if not recipes.exists():
        return None
    total = sum(
        recipe.quantity_required * recipe.ingredient.selling_price for recipe in recipes
    )
    return total.quantize(Decimal("0.01"))


def product_unit_costs() -> dict[int, Decimal]:
    costs = defaultdict(Decimal)
    recipes = Recipe.objects.select_related("ingredient")
    for recipe in recipes:
        costs[recipe.product_id] += (
            recipe.quantity_required * recipe.ingredient.selling_price
        )
    return {
        product_id: cost.quantize(Decimal("0.01")) for product_id, cost in costs.items()
    }
