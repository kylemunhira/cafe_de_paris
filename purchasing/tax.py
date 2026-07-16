from decimal import Decimal, ROUND_HALF_UP

from orders.tax import get_inclusive_tax_rate

TWOPLACES = Decimal("0.01")


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(TWOPLACES, ROUND_HALF_UP)


def is_taxable_product(product) -> bool:
    if product.tax_rate and product.tax_rate > 0:
        return True
    code = (product.fiscal_tax_code or "").strip().upper()
    return code not in ("", "B")


def split_purchase_line_total(line_total: Decimal, product) -> dict:
    """Split an inclusive line total at full precision; order totals are quantized later."""
    line_total = Decimal(line_total)
    if not is_taxable_product(product):
        return {
            "subtotal": line_total,
            "tax": Decimal("0"),
            "total": line_total,
        }

    rate = product.tax_rate if product.tax_rate and product.tax_rate > 0 else None
    if rate is None:
        rate = get_inclusive_tax_rate()
    else:
        rate = Decimal(rate)

    divisor = Decimal("1") + rate / Decimal("100")
    subtotal = line_total / divisor
    tax = line_total - subtotal
    return {
        "subtotal": subtotal,
        "tax": tax,
        "total": line_total,
    }


def purchase_order_amounts(purchase_order) -> dict:
    subtotal = Decimal("0")
    vat = Decimal("0")
    total = Decimal("0")

    lines = purchase_order.lines.all()
    if hasattr(lines, "select_related"):
        lines = lines.select_related("product")

    for line in lines:
        split = split_purchase_line_total(line.line_total, line.product)
        subtotal += split["subtotal"]
        vat += split["tax"]
        total += split["total"]

    return {
        "subtotal_amount": _quantize(subtotal),
        "vat_amount": _quantize(vat),
        "total_amount": _quantize(total),
    }
