from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

TWOPLACES = Decimal("0.01")


def get_inclusive_tax_rate() -> Decimal:
    return Decimal(str(getattr(settings, "INCLUSIVE_TAX_RATE", "15.5")))


def get_zta_levy_rate() -> Decimal:
    """Zimbabwe Tourism Authority levy rate (% of amount before VAT)."""
    return Decimal(str(getattr(settings, "ZTA_LEVY_RATE", "2")))


def line_amount(quantity, price) -> Decimal:
    return (Decimal(quantity) * Decimal(price)).quantize(TWOPLACES, ROUND_HALF_UP)


def receipt_total_from_order(order) -> Decimal:
    total = Decimal("0")
    for item in order.items.prefetch_related("addons"):
        total += line_amount(item.quantity, item.price)
        for addon in item.addons.all():
            total += line_amount(item.quantity, addon.price)
    return total


def branch_applies_zta(branch) -> bool:
    return bool(branch and getattr(branch, "fiscalization_enabled", False))


def split_inclusive_total(total, tax_rate=None, *, apply_zta=False) -> dict:
    """Split an all-inclusive selling price into subtotal, ZTA, VAT, and total.

    The selling price already includes VAT and ZTA — the customer pays that amount.
    On fiscal branches: extract 15.5% VAT first, then ZTA is 2% of that before-tax
    amount. Displayed subtotal is the remainder so Subtotal + ZTA + Tax = Total.
    """
    goods_total = Decimal(total).quantize(TWOPLACES, ROUND_HALF_UP)
    if tax_rate is None:
        tax_rate = get_inclusive_tax_rate()
    else:
        tax_rate = Decimal(tax_rate)

    divisor = Decimal("1") + tax_rate / Decimal("100")
    exclusive = (goods_total / divisor).quantize(TWOPLACES, ROUND_HALF_UP)
    tax = (goods_total - exclusive).quantize(TWOPLACES, ROUND_HALF_UP)

    zta = Decimal("0.00")
    zta_rate = Decimal("0")
    subtotal = exclusive
    if apply_zta:
        zta_rate = get_zta_levy_rate()
        if zta_rate > 0:
            zta = (exclusive * zta_rate / Decimal("100")).quantize(
                TWOPLACES, ROUND_HALF_UP
            )
            subtotal = (exclusive - zta).quantize(TWOPLACES, ROUND_HALF_UP)

    return {
        "subtotal": subtotal,
        "tax": tax,
        "tax_rate": tax_rate,
        "zta": zta,
        "zta_rate": zta_rate,
        "goods_total": goods_total,
        "total": goods_total,
    }


def order_receipt_tax_breakdown(order) -> dict:
    goods_total = receipt_total_from_order(order)
    return split_inclusive_total(
        goods_total,
        apply_zta=branch_applies_zta(getattr(order, "branch", None)),
    )


def order_amount_due(order) -> Decimal:
    """Amount the customer must pay (the all-inclusive selling price)."""
    return Decimal(order.total_amount or 0).quantize(TWOPLACES, ROUND_HALF_UP)
