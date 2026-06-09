from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

TWOPLACES = Decimal("0.01")


def get_inclusive_tax_rate() -> Decimal:
    return Decimal(str(getattr(settings, "INCLUSIVE_TAX_RATE", "15.5")))


def line_amount(quantity, price) -> Decimal:
    return (Decimal(quantity) * Decimal(price)).quantize(TWOPLACES, ROUND_HALF_UP)


def receipt_total_from_order(order) -> Decimal:
    return sum(
        line_amount(item.quantity, item.price) for item in order.items.all()
    )


def split_inclusive_total(total, tax_rate=None) -> dict:
    total = Decimal(total).quantize(TWOPLACES, ROUND_HALF_UP)
    if tax_rate is None:
        tax_rate = get_inclusive_tax_rate()
    else:
        tax_rate = Decimal(tax_rate)

    divisor = Decimal("1") + tax_rate / Decimal("100")
    subtotal = (total / divisor).quantize(TWOPLACES, ROUND_HALF_UP)
    tax = (total - subtotal).quantize(TWOPLACES, ROUND_HALF_UP)
    return {
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "tax_rate": tax_rate,
    }


def order_receipt_tax_breakdown(order) -> dict:
    return split_inclusive_total(receipt_total_from_order(order))
