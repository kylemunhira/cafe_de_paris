import csv
import io
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalog.models import Product
from orders.models import Order, OrderItem, OrderStatus

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
        tax_collected += line_total * item.product.tax_rate / Decimal("100")

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

    for item in paid_items:
        line_total = item.quantity * item.price
        tax_rate = item.product.tax_rate
        tax_amount = (line_total * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
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
