from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Order, OrderItem, OrderStatus, OrderType
from .tax import line_amount, split_inclusive_total

ORDER_TYPE_LABELS = dict(OrderType.choices)


def local_day_range(report_date=None):
    if report_date is None:
        report_date = timezone.localdate()
    elif isinstance(report_date, str):
        report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    elif isinstance(report_date, datetime):
        report_date = report_date.date()

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(report_date, datetime.min.time()), tz)
    end = start + timedelta(days=1)
    return start, end, report_date


def build_day_end_report(branch, report_date: date | str | None = None) -> dict:
    start, end, report_date = local_day_range(report_date)

    orders_qs = Order.objects.filter(
        branch=branch,
        status=OrderStatus.PAID,
        paid_at__gte=start,
        paid_at__lt=end,
    )

    order_count = orders_qs.count()
    gross_total = orders_qs.aggregate(
        total=Coalesce(Sum("total_amount"), Decimal("0"))
    )["total"]

    order_types = [
        {
            "label": ORDER_TYPE_LABELS.get(row["order_type"], row["order_type"]),
            "count": row["count"],
        }
        for row in orders_qs.values("order_type")
        .annotate(count=Count("id"))
        .order_by("order_type")
    ]

    payments = list(
        orders_qs.values(
            "payment_currency__id",
            "payment_currency__code",
            "payment_currency__name",
            "payment_currency__symbol",
        )
        .annotate(order_count=Count("id"), total_paid=Coalesce(Sum("amount_paid"), Decimal("0")))
        .order_by("payment_currency__name")
    )

    product_totals = defaultdict(
        lambda: {"product__name": "", "quantity": Decimal("0"), "revenue": Decimal("0")}
    )
    item_rows = OrderItem.objects.filter(
        order__branch=branch,
        order__status=OrderStatus.PAID,
        order__paid_at__gte=start,
        order__paid_at__lt=end,
    ).values_list("product_id", "product__name", "quantity", "price")

    for product_id, product_name, quantity, price in item_rows:
        bucket = product_totals[product_id]
        bucket["product__name"] = product_name
        bucket["quantity"] += Decimal(quantity)
        bucket["revenue"] += line_amount(quantity, price)

    products = sorted(
        product_totals.values(),
        key=lambda row: (-row["revenue"], row["product__name"]),
    )

    tax_breakdown = split_inclusive_total(gross_total)

    return {
        "report_date": report_date,
        "order_count": order_count,
        "gross_total": gross_total,
        "tax_breakdown": tax_breakdown,
        "order_types": order_types,
        "payments": payments,
        "products": products,
    }
