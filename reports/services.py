import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from bakery.models import Recipe
from catalog.models import Product
from orders.models import Expense, Order, OrderItem, OrderStatus
from orders.tax import get_inclusive_tax_rate, split_inclusive_total

LOW_STOCK_THRESHOLD = Decimal("10")


def default_date_range():
    today = timezone.localdate()
    start = today.replace(day=1)
    return start, today


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date: {value!r}. Use YYYY-MM-DD.") from exc


def parse_report_filters(from_date=None, to_date=None, branch_id=None):
    parsed_from = parse_date(from_date) if from_date else None
    parsed_to = parse_date(to_date) if to_date else None

    if parsed_from and parsed_to and parsed_from > parsed_to:
        raise ValueError("'from' date must be on or before 'to' date.")

    parsed_branch = None
    if branch_id not in (None, ""):
        try:
            parsed_branch = int(branch_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("branch must be a valid branch id.") from exc

    if not parsed_from and not parsed_to:
        parsed_from, parsed_to = default_date_range()

    return parsed_from, parsed_to, parsed_branch


def _paid_orders(from_date, to_date, branch_id):
    orders = Order.objects.filter(status=OrderStatus.PAID).select_related("branch")
    if from_date:
        orders = orders.filter(created_at__date__gte=from_date)
    if to_date:
        orders = orders.filter(created_at__date__lte=to_date)
    if branch_id:
        orders = orders.filter(branch_id=branch_id)
    return orders


def _paid_order_items(from_date, to_date, branch_id):
    items = OrderItem.objects.filter(order__status=OrderStatus.PAID).select_related(
        "product__category",
        "order__branch",
    )
    if from_date:
        items = items.filter(order__created_at__date__gte=from_date)
    if to_date:
        items = items.filter(order__created_at__date__lte=to_date)
    if branch_id:
        items = items.filter(order__branch_id=branch_id)
    return items


def _decimal(value):
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _aggregate_item_sales(items):
    category_buckets = {}
    product_buckets = {}
    tax_collected = Decimal("0")

    for item in items:
        line_total = item.quantity * item.price
        tax_collected += split_inclusive_total(line_total)["tax"]

        category_name = item.product.category.name
        category_row = category_buckets.setdefault(
            category_name,
            {"quantity": Decimal("0"), "revenue": Decimal("0")},
        )
        category_row["quantity"] += item.quantity
        category_row["revenue"] += line_total

        product_row = product_buckets.setdefault(
            item.product_id,
            {
                "product_id": item.product_id,
                "product_name": item.product.name,
                "quantity": Decimal("0"),
                "revenue": Decimal("0"),
            },
        )
        product_row["quantity"] += item.quantity
        product_row["revenue"] += line_total

    by_category = sorted(
        [
            {
                "category": name,
                "quantity": values["quantity"],
                "revenue": values["revenue"],
            }
            for name, values in category_buckets.items()
        ],
        key=lambda row: row["revenue"],
        reverse=True,
    )
    top_products = sorted(
        product_buckets.values(),
        key=lambda row: row["revenue"],
        reverse=True,
    )[:10]

    return by_category, top_products, tax_collected


def _low_stock_products():
    return [
        {
            "product_id": product.id,
            "product_name": product.name,
            "category": product.category.name,
            "remaining_qty": product.remaining_qty,
        }
        for product in Product.objects.filter(
            is_active=True,
            remaining_qty__lte=LOW_STOCK_THRESHOLD,
        )
        .select_related("category")
        .order_by("remaining_qty", "name")[:20]
    ]


def build_report_summary(from_date=None, to_date=None, branch_id=None):
    from_date, to_date, branch_id = parse_report_filters(from_date, to_date, branch_id)
    paid_orders = _paid_orders(from_date, to_date, branch_id)
    paid_items = _paid_order_items(from_date, to_date, branch_id)

    revenue = _decimal(paid_orders.aggregate(total=Sum("total_amount"))["total"])
    order_count = paid_orders.count()

    by_category, top_products, tax_collected = _aggregate_item_sales(list(paid_items))
    tax_collected = _decimal(tax_collected)

    avg_order_value = revenue / order_count if order_count else Decimal("0")

    by_branch = [
        {
            "branch_id": row["branch_id"],
            "branch_name": row["branch__name"],
            "revenue": _decimal(row["revenue"]),
            "orders": row["orders"],
        }
        for row in paid_orders.values("branch_id", "branch__name")
        .annotate(
            revenue=Coalesce(Sum("total_amount"), Decimal("0")),
            orders=Count("id"),
        )
        .order_by("-revenue")
    ]

    low_stock = _low_stock_products()

    return {
        "period": {
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
        },
        "filters": {"branch_id": branch_id},
        "summary": {
            "total_revenue": revenue,
            "tax_collected": tax_collected,
            "order_count": order_count,
            "avg_order_value": avg_order_value.quantize(Decimal("0.01")),
        },
        "by_branch": by_branch,
        "by_category": by_category,
        "top_products": top_products,
        "low_stock": low_stock,
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
    }


def export_sales_csv(from_date=None, to_date=None, branch_id=None):
    from_date, to_date, branch_id = parse_report_filters(from_date, to_date, branch_id)
    paid_items = _paid_order_items(from_date, to_date, branch_id).order_by(
        "-order__created_at",
        "id",
    )

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "order_id",
            "date",
            "branch",
            "product",
            "category",
            "quantity",
            "unit_price",
            "line_total",
            "tax_rate",
            "tax_amount",
        ],
    )
    writer.writeheader()

    inclusive_tax_rate = get_inclusive_tax_rate()

    for item in paid_items:
        line_total = item.quantity * item.price
        tax_rate = inclusive_tax_rate
        tax_amount = split_inclusive_total(line_total, tax_rate)["tax"]
        writer.writerow(
            {
                "order_id": item.order_id,
                "date": timezone.localtime(item.order.created_at).strftime("%Y-%m-%d %H:%M"),
                "branch": item.order.branch.name,
                "product": item.product.name,
                "category": item.product.category.name,
                "quantity": item.quantity,
                "unit_price": item.price,
                "line_total": line_total,
                "tax_rate": tax_rate,
                "tax_amount": tax_amount,
            }
        )

    return output.getvalue()


def _quantize_percent(numerator, denominator):
    if not denominator:
        return None
    return (numerator / denominator * Decimal("100")).quantize(Decimal("0.01"))


def _product_unit_costs():
    costs = defaultdict(Decimal)
    recipes = Recipe.objects.select_related("ingredient")
    for recipe in recipes:
        costs[recipe.product_id] += (
            recipe.quantity_required * recipe.ingredient.selling_price
        )
    return {product_id: cost.quantize(Decimal("0.01")) for product_id, cost in costs.items()}


def _period_expenses(from_date, to_date, branch_id):
    expenses = Expense.objects.all()
    if from_date:
        expenses = expenses.filter(expense_date__gte=from_date)
    if to_date:
        expenses = expenses.filter(expense_date__lte=to_date)
    if branch_id:
        expenses = expenses.filter(branch_id=branch_id)
    return expenses


def build_profit_report(from_date=None, to_date=None, branch_id=None):
    from_date, to_date, branch_id = parse_report_filters(from_date, to_date, branch_id)
    paid_items = list(_paid_order_items(from_date, to_date, branch_id))
    unit_costs = _product_unit_costs()

    product_buckets = {}
    total_revenue = Decimal("0")
    total_cogs = Decimal("0")
    revenue_without_recipe = Decimal("0")
    products_without_recipe = 0

    for item in paid_items:
        line_revenue = item.quantity * item.price
        total_revenue += line_revenue

        unit_cost = unit_costs.get(item.product_id)
        line_cogs = Decimal("0")
        if unit_cost is not None:
            line_cogs = (unit_cost * item.quantity).quantize(Decimal("0.01"))
            total_cogs += line_cogs
        else:
            revenue_without_recipe += line_revenue

        product_row = product_buckets.setdefault(
            item.product_id,
            {
                "product_id": item.product_id,
                "product_name": item.product.name,
                "category": item.product.category.name,
                "quantity": Decimal("0"),
                "revenue": Decimal("0"),
                "unit_cost": unit_cost,
                "cogs": Decimal("0"),
            },
        )
        product_row["quantity"] += item.quantity
        product_row["revenue"] += line_revenue
        product_row["cogs"] += line_cogs

    by_product = []
    for row in product_buckets.values():
        if row["unit_cost"] is None:
            products_without_recipe += 1
        gross_profit = row["revenue"] - row["cogs"]
        by_product.append(
            {
                **row,
                "gross_profit": gross_profit,
                "gp_percent": _quantize_percent(gross_profit, row["revenue"]),
            }
        )

    by_product.sort(key=lambda row: (-row["gross_profit"], row["product_name"]))

    gross_profit = total_revenue - total_cogs
    operating_expenses = _decimal(
        _period_expenses(from_date, to_date, branch_id).aggregate(
            total=Sum("amount")
        )["total"]
    )
    net_profit = gross_profit - operating_expenses

    return {
        "period": {
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
        },
        "filters": {"branch_id": branch_id},
        "summary": {
            "total_revenue": total_revenue,
            "total_cogs": total_cogs,
            "gross_profit": gross_profit,
            "gross_profit_percent": _quantize_percent(gross_profit, total_revenue),
            "operating_expenses": operating_expenses,
            "net_profit": net_profit,
            "products_without_recipe": products_without_recipe,
            "revenue_without_recipe": revenue_without_recipe,
        },
        "by_product": by_product,
    }
