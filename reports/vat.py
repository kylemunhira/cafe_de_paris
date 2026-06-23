from decimal import Decimal

from branches.models import Branch, BranchType
from orders.models import FiscalApprovalStatus, Order, OrderItem, OrderStatus
from orders.tax import split_inclusive_total
from purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus
from reports.services import parse_report_filters


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def _is_taxable_product(product) -> bool:
    if product.tax_rate and product.tax_rate > 0:
        return True
    code = (product.fiscal_tax_code or "").strip().upper()
    return code not in ("", "B")


def _split_line_total(line_total: Decimal, product) -> dict:
    if _is_taxable_product(product):
        rate = product.tax_rate if product.tax_rate and product.tax_rate > 0 else None
        return split_inclusive_total(line_total, rate)
    return {
        "subtotal": _quantize(line_total),
        "tax": Decimal("0"),
        "total": _quantize(line_total),
    }


def _fiscalized_sales_qs(from_date, to_date, branch_id):
    """Paid orders fiscalized after proforma approval — excludes pending proforma."""
    orders = (
        Order.objects.filter(
            status=OrderStatus.PAID,
            branch__branch_type=BranchType.BRANCH,
            branch__fiscalization_enabled=True,
            fiscal_approval_status=FiscalApprovalStatus.APPROVED,
            fiscal_approved_at__isnull=False,
        )
        .select_related("branch")
    )
    if from_date:
        orders = orders.filter(fiscal_approved_at__date__gte=from_date)
    if to_date:
        orders = orders.filter(fiscal_approved_at__date__lte=to_date)
    if branch_id:
        orders = orders.filter(branch_id=branch_id)
    return orders


def _vat_registered_purchases_qs(from_date, to_date, branch_id):
    purchase_orders = (
        PurchaseOrder.objects.filter(
            status=PurchaseOrderStatus.RECEIVED,
            branch__branch_type=BranchType.BRANCH,
            supplier__vat_number__gt="",
        )
        .select_related("branch", "supplier")
    )
    if from_date:
        purchase_orders = purchase_orders.filter(received_at__date__gte=from_date)
    if to_date:
        purchase_orders = purchase_orders.filter(received_at__date__lte=to_date)
    if branch_id:
        purchase_orders = purchase_orders.filter(branch_id=branch_id)
    return purchase_orders


def _aggregate_sales(orders):
    order_ids = list(orders.values_list("pk", flat=True))
    items = OrderItem.objects.filter(order_id__in=order_ids).select_related(
        "product__category"
    )

    total_incl = Decimal("0")
    total_excl = Decimal("0")
    taxable_excl = Decimal("0")
    non_taxable = Decimal("0")
    vat_amount = Decimal("0")

    for item in items:
        line_total = item.quantity * item.price
        split = _split_line_total(line_total, item.product)
        total_incl += split["total"]
        total_excl += split["subtotal"]
        vat_amount += split["tax"]
        if _is_taxable_product(item.product):
            taxable_excl += split["subtotal"]
        else:
            non_taxable += split["total"]

    return {
        "total_sales_including_vat": _quantize(total_incl),
        "total_sales_excluding_vat": _quantize(total_excl),
        "total_taxable_sales_excluding_vat": _quantize(taxable_excl),
        "total_non_taxable_sales": _quantize(non_taxable),
        "vat_on_taxable_sales": _quantize(vat_amount),
        "sales_returns": Decimal("0"),
        "discounts_given": Decimal("0"),
    }


def _aggregate_purchases(purchase_orders):
    po_ids = list(purchase_orders.values_list("pk", flat=True))
    lines = PurchaseOrderLine.objects.filter(purchase_order_id__in=po_ids).select_related(
        "product__category"
    )

    total_incl = Decimal("0")
    total_excl = Decimal("0")
    raw_incl = Decimal("0")
    raw_excl = Decimal("0")
    taxable_excl = Decimal("0")
    non_taxable = Decimal("0")
    vat_amount = Decimal("0")

    for line in lines:
        line_total = line.line_total
        split = _split_line_total(line_total, line.product)
        is_raw = line.product.category.name == "Ingredients"

        total_incl += split["total"]
        total_excl += split["subtotal"]
        vat_amount += split["tax"]

        if _is_taxable_product(line.product):
            taxable_excl += split["subtotal"]
        else:
            non_taxable += split["total"]

        if is_raw:
            raw_incl += split["total"]
            raw_excl += split["subtotal"]

    return {
        "total_purchases_including_vat": _quantize(total_incl),
        "total_purchases_excluding_vat": _quantize(total_excl),
        "total_raw_materials_including_vat": _quantize(raw_incl),
        "total_raw_materials_excluding_vat": _quantize(raw_excl),
        "credit_notes_excluding_vat": Decimal("0"),
        "credit_notes_vat": Decimal("0"),
        "credit_notes_including_vat": Decimal("0"),
        "total_taxable_purchases_excluding_vat": _quantize(taxable_excl),
        "total_non_taxable_purchases": _quantize(non_taxable),
        "vat_on_taxable_purchases": _quantize(vat_amount),
        "purchases_returns": Decimal("0"),
        "discount_given": Decimal("0"),
    }


def physical_branch_label(branch_id):
    if branch_id:
        branch = Branch.objects.filter(pk=branch_id, branch_type=BranchType.BRANCH).first()
        return branch.name if branch else "Unknown branch"
    return "All Branches"


def build_vat_report(*, from_date=None, to_date=None, branch_id=None):
    from_date, to_date, branch_id = parse_report_filters(from_date, to_date, branch_id)

    if branch_id:
        branch = Branch.objects.filter(pk=branch_id).first()
        if branch is None:
            raise ValueError("branch must be a valid branch id.")
        if branch.branch_type != BranchType.BRANCH:
            raise ValueError("VAT report is only available for physical branches.")

    sales_orders = _fiscalized_sales_qs(from_date, to_date, branch_id)
    purchase_orders = _vat_registered_purchases_qs(from_date, to_date, branch_id)

    output_tax = _aggregate_sales(sales_orders)
    input_tax = _aggregate_purchases(purchase_orders)
    net_vat = _quantize(
        output_tax["vat_on_taxable_sales"] - input_tax["vat_on_taxable_purchases"]
    )

    return {
        "period": {
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
        },
        "filters": {
            "branch_id": branch_id,
            "branch_name": physical_branch_label(branch_id),
            "physical_branches_only": True,
        },
        "output_tax": output_tax,
        "input_tax": input_tax,
        "net_vat": net_vat,
        "meta": {
            "fiscalized_sales_count": sales_orders.count(),
            "vat_purchase_order_count": purchase_orders.count(),
            "sales_scope": "fiscal_approved_only",
            "sales_excludes_proforma": True,
        },
    }
