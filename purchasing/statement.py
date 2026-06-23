from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce

from reports.services import default_date_range, parse_date

from .models import PurchaseOrder, PurchaseOrderStatus, Supplier


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def parse_statement_filters(from_date=None, to_date=None, branch_id=None):
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


def _received_purchase_orders(supplier: Supplier, *, branch_id=None):
    qs = PurchaseOrder.objects.filter(
        supplier=supplier,
        status=PurchaseOrderStatus.RECEIVED,
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return qs


def _sum_purchase_orders(qs) -> Decimal:
    total = qs.aggregate(
        total=Coalesce(
            Sum(F("lines__quantity") * F("lines__unit_cost")),
            Decimal("0"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )["total"]
    return _quantize(total or Decimal("0"))


def _filter_by_received_date(qs, *, from_date: date | None = None, to_date: date | None = None):
    if from_date:
        qs = qs.filter(received_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(received_at__date__lte=to_date)
    return qs


def build_supplier_statement_report(
    supplier: Supplier,
    *,
    from_date=None,
    to_date=None,
    branch_id=None,
    all_time: bool = False,
):
    from_date, to_date, branch_id = parse_statement_filters(from_date, to_date, branch_id)
    base_qs = _received_purchase_orders(supplier, branch_id=branch_id)

    all_time_spend = _sum_purchase_orders(base_qs)

    if all_time:
        period_qs = (
            base_qs.select_related("branch", "created_by")
            .prefetch_related("lines__product")
            .order_by("received_at", "id")
        )
        purchases = list(period_qs[:500])
        period_spend = all_time_spend
        opening_spend = Decimal("0")
        closing_spend = all_time_spend
        period = {"from": None, "to": None}
    else:
        opening_spend = _sum_purchase_orders(base_qs.filter(received_at__date__lt=from_date))
        period_qs = (
            _filter_by_received_date(base_qs, from_date=from_date, to_date=to_date)
            .select_related("branch", "created_by")
            .prefetch_related("lines__product")
            .order_by("received_at", "id")
        )
        purchases = list(period_qs)
        period_spend = _sum_purchase_orders(period_qs)
        closing_spend = _quantize(opening_spend + period_spend)
        period = {"from": from_date.isoformat(), "to": to_date.isoformat()}

    return {
        "supplier_id": supplier.pk,
        "period": period,
        "filters": {"branch_id": branch_id},
        "opening_spend": opening_spend,
        "period_spend": period_spend,
        "closing_spend": closing_spend,
        "all_time_spend": all_time_spend,
        "purchase_count": len(purchases),
        "purchases": purchases,
    }
