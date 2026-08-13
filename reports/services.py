import csv
import io
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from bakery.costing import product_unit_costs
from catalog.models import Product
from orders.models import (
    Expense,
    Order,
    OrderItem,
    OrderPayment,
    OrderStatus,
    PaymentMethod,
    TenderMethod,
)
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

    if parsed_from and not parsed_to:
        parsed_to = timezone.localdate()
    elif parsed_to and not parsed_from:
        parsed_from = parsed_to.replace(day=1)
    elif not parsed_from and not parsed_to:
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
    )[:12]

    return by_category, top_products, tax_collected


PAYMENT_METHOD_LABELS = {
    **dict(TenderMethod.choices),
    PaymentMethod.ACCOUNT: PaymentMethod.ACCOUNT.label,
}


def _payment_line_base_amount(amount, exchange_rate):
    amount = _decimal(amount)
    rate = _decimal(exchange_rate)
    if rate > 0:
        return (amount / rate).quantize(Decimal("0.01"))
    return amount


def _aggregate_payment_methods(paid_orders):
    buckets = {}

    def add_bucket(key, label, amount, order_id, payment_count=1):
        row = buckets.setdefault(
            key,
            {
                "method": key,
                "method_label": label,
                "revenue": Decimal("0"),
                "order_ids": set(),
                "payment_count": 0,
            },
        )
        row["revenue"] += _decimal(amount)
        row["order_ids"].add(order_id)
        row["payment_count"] += payment_count

    account_label = PAYMENT_METHOD_LABELS[PaymentMethod.ACCOUNT]
    for row in paid_orders.filter(payment_method=PaymentMethod.ACCOUNT).values(
        "id", "total_amount"
    ):
        add_bucket(PaymentMethod.ACCOUNT, account_label, row["total_amount"], row["id"])

    tender_order_ids = paid_orders.exclude(
        payment_method=PaymentMethod.ACCOUNT
    ).values_list("id", flat=True)
    payments = OrderPayment.objects.filter(
        order_id__in=tender_order_ids
    ).select_related("currency")
    for payment in payments:
        base_amount = _payment_line_base_amount(payment.amount, payment.exchange_rate)
        currency_name = (payment.currency.name or "").strip() if payment.currency_id else ""
        if currency_name:
            add_bucket(currency_name, currency_name, base_amount, payment.order_id)
        else:
            method = payment.method or TenderMethod.CASH
            add_bucket(
                method,
                PAYMENT_METHOD_LABELS.get(method, method),
                base_amount,
                payment.order_id,
            )

    legacy_orders = (
        paid_orders.exclude(payment_method=PaymentMethod.ACCOUNT)
        .annotate(payment_line_count=Count("payments"))
        .filter(payment_line_count=0)
    )
    for row in legacy_orders.values("id", "payment_method", "total_amount"):
        method = row["payment_method"] or PaymentMethod.CASH
        if method == PaymentMethod.MULTI:
            method = PaymentMethod.CASH
        add_bucket(
            method,
            PAYMENT_METHOD_LABELS.get(method, method),
            row["total_amount"],
            row["id"],
        )

    by_payment_method = [
        {
            "method": row["method"],
            "method_label": row["method_label"],
            "revenue": row["revenue"],
            "order_count": len(row["order_ids"]),
            "payment_count": row["payment_count"],
        }
        for row in buckets.values()
    ]
    by_payment_method.sort(key=lambda row: (-row["revenue"], row["method_label"]))
    return by_payment_method


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
    by_payment_method = _aggregate_payment_methods(paid_orders)

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
        "by_payment_method": by_payment_method,
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
    unit_costs = product_unit_costs()

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
