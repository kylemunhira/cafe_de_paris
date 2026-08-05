from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from branches.models import Branch, BranchType
from catalog.constants import BAKERY_SELLABLE_CATEGORIES, is_bakery_transfer_product
from catalog.models import Product
from inventory.models import BranchInventory, StockMovementReason
from inventory.services import InsufficientStockError, adjust_inventory

from .models import (
    ProductionOrder,
    ProductionOrderStatus,
    ProductionSheet,
    ProductionSheetAllocation,
    ProductionSheetLine,
    ProductionSheetStatus,
    Recipe,
)


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
        # Products without a recipe can still be produced (stock in only).
        return {
            "product_id": product.id,
            "product_name": product.name,
            "quantity": quantity,
            "lines": [],
            "can_produce": True,
            "shortages": [],
        }

    ingredient_ids = list(requirements.keys())
    availability = ingredient_availability(branch, ingredient_ids)
    ingredients = {
        row.id: row
        for row in Product.objects.filter(id__in=ingredient_ids).select_related(
            "category",
            "group_category",
        )
    }

    lines = []
    shortages = []
    for ingredient_id, required in requirements.items():
        available = availability.get(ingredient_id, Decimal("0"))
        ingredient = ingredients[ingredient_id]
        line = {
            "ingredient_id": ingredient_id,
            "ingredient_name": ingredient.name,
            "ingredient_category": (
                ingredient.group_category.name
                if ingredient.group_category_id
                else ingredient.category.name
            ),
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
                adjust_inventory(
                    branch,
                    ingredient_products[ingredient_id],
                    -amount,
                    reason=StockMovementReason.PRODUCTION_CONSUME,
                    note=f"Production of {product.name}",
                    user=created_by,
                )
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

        adjust_inventory(
            branch,
            product,
            quantity,
            reason=StockMovementReason.PRODUCTION_OUTPUT,
            note=f"Produced {quantity}",
            user=created_by,
        )
        return ProductionOrder.objects.create(
            branch=branch,
            product=product,
            quantity=quantity,
            status=ProductionOrderStatus.COMPLETED,
            created_by=created_by,
        )


class InvalidProductionSheetStateError(Exception):
    def __init__(self, sheet, expected, action):
        self.sheet = sheet
        self.expected = expected
        self.action = action
        super().__init__(
            f"Production sheet #{sheet.pk} must be '{expected}' to {action}, "
            f"currently '{sheet.status}'."
        )


class EmptyProductionSheetError(Exception):
    def __init__(self, sheet):
        self.sheet = sheet
        super().__init__(
            f"Production sheet #{sheet.pk} has no quantities to produce."
        )


def production_destination_branches():
    """Outlet branches and central stores that receive bakery production."""
    return list(
        Branch.objects.filter(
            is_active=True,
            branch_type__in=(BranchType.BRANCH, BranchType.STORES),
        ).order_by("branch_type", "name")
    )


def destination_column_label(branch) -> str:
    name = (branch.name or "").strip()
    lower = name.lower()
    if "highland" in lower:
        return "Highlands qty"
    if "churchill" in lower:
        return "Churchill"
    if branch.branch_type == BranchType.STORES or "central store" in lower:
        return "Central stores"
    if branch.code:
        return branch.code
    return name


def bakery_production_products():
    return (
        Product.objects.filter(
            is_active=True,
            category__name__in=BAKERY_SELLABLE_CATEGORIES,
        )
        .select_related("category")
        .order_by("category__name", "name")
    )


def create_production_sheet(branch, production_date, *, created_by=None) -> ProductionSheet:
    if branch.branch_type != BranchType.BAKERY or not branch.is_active:
        raise InvalidProductionBranchError(branch)

    destinations = production_destination_branches()
    products = list(bakery_production_products())

    with transaction.atomic():
        sheet = ProductionSheet.objects.create(
            branch=branch,
            production_date=production_date,
            created_by=created_by,
        )
        lines = [
            ProductionSheetLine(sheet=sheet, product=product)
            for product in products
        ]
        ProductionSheetLine.objects.bulk_create(lines)
        created_lines = list(sheet.lines.select_related("product"))
        allocations = [
            ProductionSheetAllocation(
                line=line,
                destination_branch=destination,
            )
            for line in created_lines
            for destination in destinations
        ]
        if allocations:
            ProductionSheetAllocation.objects.bulk_create(allocations)
    return sheet


def sync_production_sheet_lines(sheet: ProductionSheet) -> ProductionSheet:
    if sheet.status != ProductionSheetStatus.DRAFT:
        return sheet

    destinations = production_destination_branches()
    destination_ids = {branch.id for branch in destinations}
    product_ids = set(bakery_production_products().values_list("id", flat=True))

    with transaction.atomic():
        existing_lines = {
            line.product_id: line
            for line in sheet.lines.select_for_update().prefetch_related("allocations")
        }
        stale_ids = [
            line.id
            for product_id, line in existing_lines.items()
            if product_id not in product_ids
        ]
        if stale_ids:
            ProductionSheetLine.objects.filter(id__in=stale_ids).delete()

        missing_products = [
            product
            for product in bakery_production_products()
            if product.id not in existing_lines
        ]
        if missing_products:
            new_lines = ProductionSheetLine.objects.bulk_create(
                [
                    ProductionSheetLine(sheet=sheet, product=product)
                    for product in missing_products
                ]
            )
            ProductionSheetAllocation.objects.bulk_create(
                [
                    ProductionSheetAllocation(
                        line=line,
                        destination_branch=destination,
                    )
                    for line in new_lines
                    for destination in destinations
                ]
            )

        for line in sheet.lines.prefetch_related("allocations"):
            existing_destinations = {
                allocation.destination_branch_id: allocation
                for allocation in line.allocations.all()
            }
            to_delete = [
                allocation.id
                for dest_id, allocation in existing_destinations.items()
                if dest_id not in destination_ids
            ]
            if to_delete:
                ProductionSheetAllocation.objects.filter(id__in=to_delete).delete()
            missing = [
                destination
                for destination in destinations
                if destination.id not in existing_destinations
            ]
            if missing:
                ProductionSheetAllocation.objects.bulk_create(
                    [
                        ProductionSheetAllocation(
                            line=line,
                            destination_branch=destination,
                        )
                        for destination in missing
                    ]
                )
    return sheet


def update_production_sheet_lines(sheet: ProductionSheet, lines_data: list) -> ProductionSheet:
    if sheet.status != ProductionSheetStatus.DRAFT:
        raise InvalidProductionSheetStateError(
            sheet, ProductionSheetStatus.DRAFT, "update lines"
        )

    with transaction.atomic():
        lines_by_id = {
            line.id: line
            for line in sheet.lines.select_for_update().prefetch_related("allocations")
        }
        for row in lines_data:
            line = lines_by_id.get(row["id"])
            if line is None:
                continue
            allocations_by_dest = {
                allocation.destination_branch_id: allocation
                for allocation in line.allocations.all()
            }
            for allocation_data in row.get("allocations", []):
                allocation = allocations_by_dest.get(
                    allocation_data["destination_branch"]
                )
                if allocation is None:
                    continue
                quantity = allocation_data.get("quantity")
                if quantity is not None and quantity < Decimal("0"):
                    raise ValueError("Quantity cannot be negative.")
                allocation.quantity = quantity
                allocation.save(update_fields=["quantity"])
    return sheet


def complete_production_sheet(sheet: ProductionSheet) -> ProductionSheet:
    if sheet.status != ProductionSheetStatus.DRAFT:
        raise InvalidProductionSheetStateError(
            sheet, ProductionSheetStatus.DRAFT, "complete"
        )

    lines = list(
        sheet.lines.select_related("product").prefetch_related("allocations")
    )
    to_produce = []
    for line in lines:
        total = Decimal("0")
        for allocation in line.allocations.all():
            if allocation.quantity is not None and allocation.quantity > 0:
                total += allocation.quantity
        if total > 0:
            to_produce.append((line.product, total))

    if not to_produce:
        raise EmptyProductionSheetError(sheet)

    with transaction.atomic():
        for product, quantity in to_produce:
            complete_production(
                sheet.branch,
                product,
                quantity,
                created_by=sheet.created_by,
            )
        sheet.status = ProductionSheetStatus.COMPLETED
        sheet.completed_at = timezone.now()
        sheet.save(update_fields=["status", "completed_at"])
    return sheet


def cancel_production_sheet(sheet: ProductionSheet) -> ProductionSheet:
    if sheet.status != ProductionSheetStatus.DRAFT:
        raise InvalidProductionSheetStateError(
            sheet, ProductionSheetStatus.DRAFT, "cancel"
        )
    sheet.status = ProductionSheetStatus.CANCELLED
    sheet.save(update_fields=["status"])
    return sheet
