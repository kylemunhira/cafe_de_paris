from decimal import Decimal

from .models import Currency


def payment_options_for_amount(base_amount) -> list[dict]:
    """Convert a base-currency total into each active currency with a rate.

    Returns a list of dicts suitable for receipt templates:
    [{name, code, symbol, amount, rate, is_base}, ...]
    """
    try:
        amount = Decimal(str(base_amount or 0))
    except Exception:
        amount = Decimal("0")

    options = []
    currencies = Currency.objects.filter(is_active=True).order_by("name")
    for currency in currencies:
        rate = currency.get_current_rate()
        if rate is None:
            continue
        options.append(
            {
                "name": currency.name,
                "code": currency.code or "",
                "symbol": currency.symbol or "",
                "amount": currency.convert_from_base(amount),
                "rate": rate,
                "is_base": currency.is_base,
            }
        )
    return options
