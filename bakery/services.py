from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from branches.models import Branch, BranchType
from catalog.constants import is_bakery_transfer_product
from catalog.models import Product
from inventory.models import BranchInventory
from inventory.services import InsufficientStockError, adjust_inventory

from .models import ProductionOrder, ProductionOrderStatus, Recipe


class InvalidProductionBranchError(Exception):
    def __init__(self, branch):
        self.branch = branch
        super().__init__("Production must be recorded at a central bakery branch.")


class InvalidProductionProductError(Exception):
    def __init__(self, product):
        self.product = product
        super().__init__(
            "Only finished bakery products can be produced. "
            "Use Breads & pastries, Cakes & desserts, or Savory categories."
        )


class NoRecipeError(Exception):
    def __init__(self, product):
        self.product = product
        super().__init__(f"No recipe defined for {product}.")


class IngredientShortage:
    def __init__(self, ingredient, required, available):
        self.ingredient = ingredient
        self.required = required
        self.available = available


class InsufficientIngredientsError(Exception):
    def __init__(self, shortages: list[IngredientShortage]):
        self.shortages = shortages
        details = ", ".join(
            f"{item.ingredient.name} (need {item.required}, have {item.available})"
            for item in shortages
        )
        super().__init__(f"Insufficient ingredients: {details}")


def required_ingredients(product, quantity: Decimal) -> dict[int, Decimal]:
    totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for line in Recipe.objects.filter(product=product).select_related("ingredient"):
        totals[line.ingredient_id] += line.quantity_required * quantity
    return dict(totals)


def ingredient_availability(branch, ingredient_ids) -> dict[int, Decimal]:
    inventory = BranchInventory.objects.filter(
        branch=branch,
        product_id__in=ingredient_ids,
    )
    return {row.product_id: row.quantity for row in inventory}


def preview_production(branch, product, quantity: Decimal) -> dict:
    requirements = required_ingredients(product, quantity)
    if not requirements:
        raise NoRecipeError(product)

    ingredient_ids = list(requirements.keys())
    availability = ingredient_availability(branch, ingredient_ids)
    ingredients = {
        row.id: row
        for row in Product.objects.filter(id__in=ingredient_ids).select_related("category")
    }

    lines = []
    shortages = []
    for ingredient_id, required in requirements.items():
        available = availability.get(ingredient_id, Decimal("0"))
        ingredient = ingredients[ingredient_id]
        line = {
            "ingredient_id": ingredient_id,
            "ingredient_name": ingredient.name,
            "ingredient_category": ingredient.category.name,
            "required": required,
            "available": available,
            "sufficient": available >= required,
        }
        lines.append(line)
        if available < required:
            shortages.append(
                IngredientShortage(ingredient, required, available)
            )

    return {
        "product_id": product.id,
        "product_name": product.name,
        "quantity": quantity,
        "lines": lines,
        "can_produce": not shortages,
        "shortages": [
            {
                "ingredient_id": item.ingredient.id,
                "ingredient_name": item.ingredient.name,
                "required": item.required,
                "available": item.available,
            }
            for item in shortages
        ],
    }


def complete_production(
    branch,
    product,
    quantity: Decimal,
    *,
    created_by=None,
) -> ProductionOrder:
    if branch.branch_type != BranchType.BAKERY:
        raise InvalidProductionBranchError(branch)
    if not branch.is_active:
        raise InvalidProductionBranchError(branch)
    if not is_bakery_transfer_product(product):
        raise InvalidProductionProductError(product)
    if quantity <= Decimal("0"):
        raise ValueError("Quantity must be greater than zero.")

    preview = preview_production(branch, product, quantity)
    if not preview["can_produce"]:
        shortages = [
            IngredientShortage(
                Product.objects.get(pk=item["ingredient_id"]),
                item["required"],
                item["available"],
            )
            for item in preview["shortages"]
        ]
        raise InsufficientIngredientsError(shortages)

    requirements = required_ingredients(product, quantity)
    ingredient_products = {
        row.id: row
        for row in Product.objects.filter(id__in=requirements.keys())
    }

    with transaction.atomic():
        for ingredient_id, amount in requirements.items():
            try:
                adjust_inventory(branch, ingredient_products[ingredient_id], -amount)
            except InsufficientStockError as exc:
                raise InsufficientIngredientsError(
                    [
                        IngredientShortage(
                            exc.product,
                            amount,
                            exc.available,
                        )
                    ]
                ) from exc

        adjust_inventory(branch, product, quantity)
        return ProductionOrder.objects.create(
            branch=branch,
            product=product,
            quantity=quantity,
            status=ProductionOrderStatus.COMPLETED,
            created_by=created_by,
        )
