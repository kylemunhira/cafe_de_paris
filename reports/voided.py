from decimal import Decimal

from django.utils import timezone

from orders.models import Order, OrderStatus
from orders.serializers import staff_display_name
from orders.tax import line_amount

from .ingredients import parse_report_date


def _action_type(order):
    if order.status == OrderStatus.CANCELLED:
        return "cancelled"
    return "voided"


def _action_label(action_type):
    return "Cancelled" if action_type == "cancelled" else "Voided"


def _line_total(item):
    total = line_amount(item.quantity, item.price)
    for addon in item.addons.all():
        total += line_amount(item.quantity, addon.price)
    return total


def build_voided_cancelled_report(
    report_date=None,
    branch_id=None,
    search=None,
):
    usage_date = parse_report_date(report_date)
    search_term = (search or "").strip().lower()

    orders = (
        Order.objects.filter(cancelled_at__date=usage_date)
        .select_related("branch", "cancelled_by", "created_by")
        .prefetch_related(
            "items__product",
            "items__addons",
        )
        .order_by("cancelled_at", "id")
    )
    if branch_id is not None:
        orders = orders.filter(branch_id=branch_id)

    rows = []
    voided_order_ids = set()
    cancelled_order_ids = set()
    voided_item_count = 0
    cancelled_item_count = 0
    voided_amount = Decimal("0")
    cancelled_amount = Decimal("0")

    for order in orders:
        action_type = _action_type(order)
        cancelled_at = timezone.localtime(order.cancelled_at)
        staff_name = staff_display_name(order.cancelled_by)
        table_number = (order.table_number or "").strip()
        items = list(order.items.all())
        order_rows = []

        if not items:
            order_rows.append(
                {
                    "cancelled_at": cancelled_at.isoformat(),
                    "action_type": action_type,
                    "action_label": _action_label(action_type),
                    "order_id": order.id,
                    "branch_id": order.branch_id,
                    "branch_name": order.branch.name,
                    "table_number": table_number,
                    "product_name": "—",
                    "addons": "",
                    "quantity": Decimal("0"),
                    "unit_price": Decimal("0"),
                    "line_total": Decimal("0"),
                    "cancelled_by_name": staff_name,
                    "order_status": order.status,
                    "order_type": order.order_type,
                }
            )
        else:
            for item in items:
                product_name = item.product.name
                addon_names = [addon.name for addon in item.addons.all()]
                addons_text = ", ".join(addon_names)

                if search_term:
                    haystack = f"{product_name} {addons_text}".lower()
                    if search_term not in haystack:
                        continue

                line_total = _line_total(item)
                order_rows.append(
                    {
                        "cancelled_at": cancelled_at.isoformat(),
                        "action_type": action_type,
                        "action_label": _action_label(action_type),
                        "order_id": order.id,
                        "branch_id": order.branch_id,
                        "branch_name": order.branch.name,
                        "table_number": table_number,
                        "product_name": product_name,
                        "addons": addons_text,
                        "quantity": item.quantity,
                        "unit_price": item.price,
                        "line_total": line_total,
                        "cancelled_by_name": staff_name,
                        "order_status": order.status,
                        "order_type": order.order_type,
                    }
                )

        if not order_rows:
            continue

        for row in order_rows:
            if row["action_type"] == "cancelled":
                cancelled_item_count += 1
                cancelled_amount += row["line_total"]
            else:
                voided_item_count += 1
                voided_amount += row["line_total"]

        if action_type == "cancelled":
            cancelled_order_ids.add(order.id)
        else:
            voided_order_ids.add(order.id)

        rows.extend(order_rows)

    return {
        "date": usage_date.isoformat(),
        "filters": {
            "branch_id": branch_id,
            "search": search or "",
        },
        "summary": {
            "row_count": len(rows),
            "voided_order_count": len(voided_order_ids),
            "cancelled_order_count": len(cancelled_order_ids),
            "voided_item_count": voided_item_count,
            "cancelled_item_count": cancelled_item_count,
            "voided_amount": voided_amount.quantize(Decimal("0.01")),
            "cancelled_amount": cancelled_amount.quantize(Decimal("0.01")),
            "total_amount": (voided_amount + cancelled_amount).quantize(Decimal("0.01")),
        },
        "rows": rows,
    }
