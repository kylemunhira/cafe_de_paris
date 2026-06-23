from decimal import Decimal

from django.db.models import DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce

from reports.services import default_date_range, parse_date

from .models import PurchaseOrderStatus, Supplier


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def _parse_filters(from_date=None, to_date=None, branch_id=None):
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


def build_supplier_spend_summary_report(
    *,
    search=None,
    from_date=None,
    to_date=None,
    branch_id=None,
):
    from_date, to_date, branch_id = _parse_filters(from_date, to_date, branch_id)

    qs = Supplier.objects.filter(is_active=True)
    if search:
        term = search.strip()
        if term:
            qs = qs.filter(
                Q(name__icontains=term)
                | Q(contact_person__icontains=term)
                | Q(phone__icontains=term)
                | Q(email__icontains=term)
                | Q(vat_number__icontains=term)
            )

    spend_filter = {
        "purchase_orders__status": PurchaseOrderStatus.RECEIVED,
        "purchase_orders__received_at__date__gte": from_date,
        "purchase_orders__received_at__date__lte": to_date,
    }
    if branch_id:
        spend_filter["purchase_orders__branch_id"] = branch_id

    suppliers = list(
        qs.annotate(
            period_spend=Coalesce(
                Sum(
                    F("purchase_orders__lines__quantity")
                    * F("purchase_orders__lines__unit_cost"),
                    filter=Q(**spend_filter),
                ),
                Decimal("0"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ).order_by("-period_spend", "name", "id")
    )

    total_spend = sum((supplier.period_spend for supplier in suppliers), Decimal("0"))
    with_spend = sum(1 for supplier in suppliers if supplier.period_spend > 0)

    return {
        "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "filters": {
            "search": search or "",
            "branch_id": branch_id,
        },
        "summary": {
            "supplier_count": len(suppliers),
            "suppliers_with_spend": with_spend,
            "total_spend": _quantize(total_spend),
        },
        "suppliers": [
            {
                "id": supplier.pk,
                "name": supplier.name,
                "contact_person": supplier.contact_person,
                "phone": supplier.phone,
                "email": supplier.email,
                "vat_number": supplier.vat_number,
                "period_spend": _quantize(supplier.period_spend),
            }
            for supplier in suppliers
        ],
    }
