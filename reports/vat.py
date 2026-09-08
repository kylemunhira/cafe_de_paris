from decimal import Decimal

from django.db.models import Q

from branches.models import Branch, BranchType
from orders.models import FiscalApprovalStatus, Order, OrderItem, OrderStatus
from orders.tax import split_inclusive_total
from payments.models import Currency
from purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus
from purchasing.tax import split_purchase_line_total
from reports.services import parse_report_filters

VAT_CURRENCY_MODES = frozenset({"usd", "zwg", "both"})


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def _parse_currency_mode(currency_mode) -> str:
    mode = (currency_mode or "usd").strip().lower()
    if mode == "base":
        mode = "usd"
    if mode not in VAT_CURRENCY_MODES:
        raise ValueError("currency must be one of: usd, zwg, both.")
    return mode


def _currency_payload(currency):
    if currency is None:
        return None
    return {
        "id": currency.id,
        "code": (currency.code or "").upper(),
        "name": currency.name,
        "symbol": currency.symbol or "",
        "is_base": currency.is_base,
    }


def _empty_sales() -> dict:
    return {
        "total_sales_including_vat": Decimal("0"),
        "total_sales_excluding_vat": Decimal("0"),
        "total_taxable_sales_excluding_vat": Decimal("0"),
        "total_non_taxable_sales": Decimal("0"),
        "vat_on_taxable_sales": Decimal("0"),
        "sales_returns": Decimal("0"),
        "discounts_given": Decimal("0"),
    }


def _empty_purchases() -> dict:
    return {
        "total_purchases_including_vat": Decimal("0"),
        "total_purchases_excluding_vat": Decimal("0"),
        "total_raw_materials_including_vat": Decimal("0"),
        "total_raw_materials_excluding_vat": Decimal("0"),
        "credit_notes_excluding_vat": Decimal("0"),
        "credit_notes_vat": Decimal("0"),
        "credit_notes_including_vat": Decimal("0"),
        "total_taxable_purchases_excluding_vat": Decimal("0"),
        "total_non_taxable_purchases": Decimal("0"),
        "vat_on_taxable_purchases": Decimal("0"),
        "purchases_returns": Decimal("0"),
        "discount_given": Decimal("0"),
    }


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
        .select_related("branch", "payment_currency")
    )
    if from_date:
        orders = orders.filter(fiscal_approved_at__date__gte=from_date)
    if to_date:
        orders = orders.filter(fiscal_approved_at__date__lte=to_date)
    if branch_id:
        orders = orders.filter(branch_id=branch_id)
    return orders


def _usd_paid_q():
    """Fiscalised orders paid in USD / base currency (including unset payment currency)."""
    return (
        Q(payment_currency__isnull=True)
        | Q(payment_currency__is_base=True)
        | Q(payment_currency__code__iexact="USD")
    )


def _zwg_paid_q():
    return Q(payment_currency__code__iexact="ZWG")


def _payment_scale(order) -> Decimal:
    """Units of payment currency per 1 base unit locked at payment — not today's rate."""
    currency = order.payment_currency
    if currency is None or currency.is_base:
        return Decimal("1")
    if (currency.code or "").upper() == "USD":
        return Decimal("1")
    rate = order.exchange_rate
    if rate is None or rate <= 0:
        return Decimal("1")
    return rate


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


def _aggregate_sales(orders, *, in_payment_currency=False):
    order_ids = list(orders.values_list("pk", flat=True))
    if not order_ids:
        return _empty_sales()

    items = OrderItem.objects.filter(order_id__in=order_ids).select_related(
        "product__category",
        "order__payment_currency",
    )

    total_incl = Decimal("0")
    total_excl = Decimal("0")
    taxable_excl = Decimal("0")
    non_taxable = Decimal("0")
    vat_amount = Decimal("0")

    for item in items:
        line_total = item.quantity * item.price
        split = _split_line_total(line_total, item.product)
        scale = _payment_scale(item.order) if in_payment_currency else Decimal("1")

        total_incl += _quantize(split["total"] * scale)
        total_excl += _quantize(split["subtotal"] * scale)
        vat_amount += _quantize(split["tax"] * scale)
        if _is_taxable_product(item.product):
            taxable_excl += _quantize(split["subtotal"] * scale)
        else:
            non_taxable += _quantize(split["total"] * scale)

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
    if not po_ids:
        return _empty_purchases()

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
        split = split_purchase_line_total(line_total, line.product)
        is_raw = line.product.category.name == "Ingredients"

        total_incl += split["total"]
        total_excl += split["subtotal"]
        vat_amount += split["tax"]

        # VAT-registered supplier purchases always carry input VAT on line totals.
        taxable_excl += split["subtotal"]

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


def _resolve_currency_records():
    usd = (
        Currency.objects.filter(code__iexact="USD", is_active=True).first()
        or Currency.objects.filter(is_base=True).first()
    )
    zwg = Currency.objects.filter(code__iexact="ZWG", is_active=True).first()
    return usd, zwg


def build_vat_report(*, from_date=None, to_date=None, branch_id=None, currency=None):
    from_date, to_date, branch_id = parse_report_filters(from_date, to_date, branch_id)
    currency_mode = _parse_currency_mode(currency)

    if branch_id:
        branch = Branch.objects.filter(pk=branch_id).first()
        if branch is None:
            raise ValueError("branch must be a valid branch id.")
        if branch.branch_type != BranchType.BRANCH:
            raise ValueError("VAT report is only available for physical branches.")

    sales_orders = _fiscalized_sales_qs(from_date, to_date, branch_id)
    purchase_orders = _vat_registered_purchases_qs(from_date, to_date, branch_id)

    usd_orders = sales_orders.filter(_usd_paid_q())
    zwg_orders = sales_orders.filter(_zwg_paid_q())

    # Base-currency aggregates (all fiscalised sales) — kept for API compatibility.
    output_tax = _aggregate_sales(sales_orders, in_payment_currency=False)
    input_tax = _aggregate_purchases(purchase_orders)
    net_vat = _quantize(
        output_tax["vat_on_taxable_sales"] - input_tax["vat_on_taxable_purchases"]
    )

    usd_output = _aggregate_sales(usd_orders, in_payment_currency=True)
    zwg_output = _aggregate_sales(zwg_orders, in_payment_currency=True)
    # Purchases are recorded in base/USD only — not FX-converted into ZWG.
    usd_input = input_tax
    zwg_input = _empty_purchases()

    usd_net = _quantize(
        usd_output["vat_on_taxable_sales"] - usd_input["vat_on_taxable_purchases"]
    )
    zwg_net = _quantize(zwg_output["vat_on_taxable_sales"])

    usd_currency, zwg_currency = _resolve_currency_records()
    usd_code = ((usd_currency.code if usd_currency else None) or "USD").upper()
    zwg_code = ((zwg_currency.code if zwg_currency else None) or "ZWG").upper()

    amounts_by_currency = {}
    if currency_mode in ("usd", "both"):
        amounts_by_currency[usd_code] = {
            "output_tax": usd_output,
            "input_tax": usd_input,
            "net_vat": usd_net,
            "sales_count": usd_orders.count(),
            "payment_scope": "usd_paid_fiscalised",
        }
    if currency_mode in ("zwg", "both"):
        amounts_by_currency[zwg_code] = {
            "output_tax": zwg_output,
            "input_tax": zwg_input,
            "net_vat": zwg_net,
            "sales_count": zwg_orders.count(),
            "payment_scope": "zwg_paid_fiscalised",
        }

    return {
        "period": {
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
        },
        "filters": {
            "branch_id": branch_id,
            "branch_name": physical_branch_label(branch_id),
            "physical_branches_only": True,
            "currency": currency_mode,
        },
        "currency": {
            "mode": currency_mode,
            "basis": "payment_currency",
            "usd": _currency_payload(usd_currency),
            "zwg": _currency_payload(zwg_currency),
            # Aliases used by the existing UI
            "base": _currency_payload(usd_currency),
        },
        "amounts_by_currency": amounts_by_currency,
        "output_tax": output_tax,
        "input_tax": input_tax,
        "net_vat": net_vat,
        "meta": {
            "fiscalized_sales_count": sales_orders.count(),
            "usd_paid_fiscalized_sales_count": usd_orders.count(),
            "zwg_paid_fiscalized_sales_count": zwg_orders.count(),
            "vat_purchase_order_count": purchase_orders.count(),
            "sales_scope": "fiscal_approved_only",
            "sales_excludes_proforma": True,
            "currency_basis": "payment_currency_no_fx_conversion",
            "purchases_currency": "base_usd_only",
        },
    }
