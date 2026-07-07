from decimal import Decimal, InvalidOperation

from django.utils import timezone

from bakery.models import ProductionOrder, ProductionOrderStatus, Recipe
from bakery.services import required_ingredients
from branches.models import Branch, BranchType
from catalog.constants import ingredient_categories_for_branch_type
from catalog.models import Product
from inventory.models import BranchInventory
from orders.models import OrderItem, OrderStatus

from .services import parse_date

INGREDIENTS_CATEGORY = "Ingredients"
DEFAULT_LOW_STOCK_THRESHOLD = Decimal("10")


def _ingredient_categories_for_report(branch_id=None, branches=None):
    if branch_id is not None:
        branch = Branch.objects.filter(pk=branch_id).first()
        if branch:
            return ingredient_categories_for_branch_type(branch.branch_type)
    if branches:
        categories = set()
        for branch in branches:
            categories.update(ingredient_categories_for_branch_type(branch.branch_type))
        return frozenset(categories)
    from catalog.constants import ALL_INGREDIENT_CATEGORIES

    return ALL_INGREDIENT_CATEGORIES


def _decimal(value):
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def parse_low_stock_threshold(value):
    if value in (None, ""):
        return DEFAULT_LOW_STOCK_THRESHOLD
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("low_stock_threshold must be a valid number.") from exc


def build_ingredient_stock_report(
    branch_id=None,
    search=None,
    active_only=True,
    low_stock_only=False,
    low_stock_threshold=None,
):
    threshold = parse_low_stock_threshold(low_stock_threshold)

    branches = Branch.objects.filter(is_active=True).order_by("name")
    if branch_id is not None:
        branches = branches.filter(pk=branch_id)
    branches = list(branches)

    categories = _ingredient_categories_for_report(branch_id=branch_id, branches=branches)
    ingredients_qs = Product.objects.filter(
        category__name__in=categories,
    ).select_related("category")
    if active_only:
        ingredients_qs = ingredients_qs.filter(is_active=True)
    if search:
        ingredients_qs = ingredients_qs.filter(name__icontains=search.strip())
    ingredients = list(ingredients_qs.order_by("name"))

    branch_ids = [branch.id for branch in branches]
    ingredient_ids = [ingredient.id for ingredient in ingredients]

    inventory_map = {}
    if branch_ids and ingredient_ids:
        for row in BranchInventory.objects.filter(
            branch_id__in=branch_ids,
            product_id__in=ingredient_ids,
        ):
            inventory_map[(row.branch_id, row.product_id)] = row.quantity

    rows = []
    total_stock_value = Decimal("0")
    rows_with_stock = 0

    for ingredient in ingredients:
        unit_cost = _decimal(ingredient.selling_price)
        for branch in branches:
            quantity = inventory_map.get((branch.id, ingredient.id), Decimal("0"))
            if low_stock_only and quantity > threshold:
                continue

            stock_value = (quantity * unit_cost).quantize(Decimal("0.01"))
            if quantity > 0:
                rows_with_stock += 1
            total_stock_value += stock_value

            rows.append(
                {
                    "ingredient_id": ingredient.id,
                    "ingredient_name": ingredient.name,
                    "branch_id": branch.id,
                    "branch_name": branch.name,
                    "unit_cost": unit_cost,
                    "quantity": quantity,
                    "stock_value": stock_value,
                    "is_active": ingredient.is_active,
                }
            )

    return {
        "filters": {
            "branch_id": branch_id,
            "search": search or "",
            "active_only": active_only,
            "low_stock_only": low_stock_only,
            "low_stock_threshold": threshold,
        },
        "summary": {
            "row_count": len(rows),
            "ingredient_count": len(ingredients),
            "branch_count": len(branches),
            "rows_with_stock": rows_with_stock,
            "total_stock_value": total_stock_value.quantize(Decimal("0.01")),
        },
        "rows": rows,
    }


def parse_report_date(value):
    if value in (None, ""):
        return timezone.localdate()
    parsed = parse_date(value)
    if parsed is None:
        return timezone.localdate()
    return parsed


def _recipe_lines_by_product():
    from collections import defaultdict

    recipe_lines = defaultdict(list)
    for recipe in Recipe.objects.select_related("ingredient", "ingredient__category"):
        if recipe.ingredient.category.name != INGREDIENTS_CATEGORY:
            continue
        recipe_lines[recipe.product_id].append(
            (recipe.ingredient_id, recipe.quantity_required)
        )
    return recipe_lines


def build_ingredient_usage_report(
    report_date=None,
    branch_id=None,
    search=None,
    active_only=True,
):
    usage_date = parse_report_date(report_date)
    recipe_lines = _recipe_lines_by_product()

    usage = {}
    branches_seen = set()

    sales_items = OrderItem.objects.filter(
        order__status=OrderStatus.PAID,
        order__created_at__date=usage_date,
    ).select_related("order__branch", "product")
    if branch_id is not None:
        sales_items = sales_items.filter(order__branch_id=branch_id)

    for item in sales_items:
        branch_key = item.order.branch_id
        branches_seen.add(branch_key)
        for ingredient_id, quantity_required in recipe_lines.get(item.product_id, []):
            key = (branch_key, ingredient_id)
            bucket = usage.setdefault(
                key,
                {"from_sales": Decimal("0"), "from_production": Decimal("0")},
            )
            bucket["from_sales"] += item.quantity * quantity_required

    productions = ProductionOrder.objects.filter(
        status=ProductionOrderStatus.COMPLETED,
        created_at__date=usage_date,
    ).select_related("branch", "product")
    if branch_id is not None:
        productions = productions.filter(branch_id=branch_id)

    for production in productions:
        branches_seen.add(production.branch_id)
        for ingredient_id, amount in required_ingredients(
            production.product, production.quantity
        ).items():
            key = (production.branch_id, ingredient_id)
            bucket = usage.setdefault(
                key,
                {"from_sales": Decimal("0"), "from_production": Decimal("0")},
            )
            bucket["from_production"] += amount

    ingredient_filter = Product.objects.filter(category__name=INGREDIENTS_CATEGORY)
    if active_only:
        ingredient_filter = ingredient_filter.filter(is_active=True)
    if search:
        ingredient_filter = ingredient_filter.filter(name__icontains=search.strip())
    allowed_ingredient_ids = set(ingredient_filter.values_list("id", flat=True))

    ingredient_ids = {key[1] for key in usage} & allowed_ingredient_ids
    ingredients = {
        product.id: product
        for product in Product.objects.filter(id__in=ingredient_ids)
    }
    branches = {
        branch.id: branch
        for branch in Branch.objects.filter(id__in=branches_seen, is_active=True)
    }

    rows = []
    total_quantity_used = Decimal("0")
    total_usage_cost = Decimal("0")
    ingredients_with_usage = set()

    for (branch_key, ingredient_key), amounts in sorted(
        usage.items(),
        key=lambda item: (item[0][0], item[0][1]),
    ):
        if ingredient_key not in allowed_ingredient_ids:
            continue

        from_sales = amounts["from_sales"]
        from_production = amounts["from_production"]
        quantity_used = from_sales + from_production
        if quantity_used <= 0:
            continue

        ingredient = ingredients.get(ingredient_key)
        branch = branches.get(branch_key)
        if ingredient is None or branch is None:
            continue

        unit_cost = _decimal(ingredient.selling_price)
        usage_cost = (quantity_used * unit_cost).quantize(Decimal("0.01"))
        ingredients_with_usage.add(ingredient_key)
        total_quantity_used += quantity_used
        total_usage_cost += usage_cost

        rows.append(
            {
                "ingredient_id": ingredient.id,
                "ingredient_name": ingredient.name,
                "branch_id": branch.id,
                "branch_name": branch.name,
                "from_sales": from_sales,
                "from_production": from_production,
                "quantity_used": quantity_used,
                "unit_cost": unit_cost,
                "usage_cost": usage_cost,
            }
        )

    rows.sort(key=lambda row: (row["branch_name"], row["ingredient_name"]))

    branch_ids_in_rows = {row["branch_id"] for row in rows}
    return {
        "date": usage_date.isoformat(),
        "filters": {
            "branch_id": branch_id,
            "search": search or "",
            "active_only": active_only,
        },
        "summary": {
            "row_count": len(rows),
            "ingredient_count": len(ingredients_with_usage),
            "branch_count": len(branch_ids_in_rows),
            "total_quantity_used": total_quantity_used,
            "total_usage_cost": total_usage_cost.quantize(Decimal("0.01")),
        },
        "rows": rows,
    }
