from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from .constants import (
    DEFAULT_MONEY_TYPE_CODE,
    DEFAULT_STANDARD_TAX_ID,
    RECEIPT_LINE_TYPE,
    RECEIPT_PRINT_FORM,
    RECEIPT_TYPE,
    STANDARD_TAX_CODE,
    ZERO_RATED_TAX_CODE,
    ZERO_RATED_TAX_ID,
)

TWOPLACES = Decimal("0.01")
QUANT = Decimal("0.01")


def _money(value: Decimal) -> float:
    return float(value.quantize(TWOPLACES, rounding=ROUND_HALF_UP))


def _quantity(value: Decimal) -> float:
    return float(value.quantize(QUANT, rounding=ROUND_HALF_UP))


def _format_receipt_date(dt):
    local = timezone.localtime(dt)
    centiseconds = local.microsecond // 10000
    return local.strftime(f"%Y-%m-%dT%H:%M:%S.{centiseconds:02d}")


def _payment_currency_code(order) -> str:
    currency = order.payment_currency
    if currency.code:
        return currency.code.strip().upper()
    return currency.name[:10].upper().replace(" ", "")


def _to_payment_amount(order, base_amount: Decimal) -> Decimal:
    rate = order.exchange_rate or Decimal("1")
    return (base_amount * rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _to_tax_exclusive(amount: Decimal, tax_percent: Decimal) -> Decimal:
    if tax_percent <= 0:
        return amount
    divisor = Decimal("1") + tax_percent / Decimal("100")
    return (amount / divisor).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _product_tax_meta(product):
    tax_percent = product.tax_rate or Decimal("0")
    if product.fiscal_tax_code:
        tax_code = product.fiscal_tax_code
    elif tax_percent > 0:
        tax_code = STANDARD_TAX_CODE
    else:
        tax_code = ZERO_RATED_TAX_CODE

    if product.fiscal_tax_id is not None:
        tax_id = product.fiscal_tax_id
    elif tax_code == ZERO_RATED_TAX_CODE:
        tax_id = ZERO_RATED_TAX_ID
    else:
        tax_id = DEFAULT_STANDARD_TAX_ID

    return tax_code, tax_percent, tax_id


def build_fiscal_receipt_payload(
    order,
    *,
    receipt_counter: int,
    receipt_global_no: int,
    invoice_no: str,
    money_type_code: str = DEFAULT_MONEY_TYPE_CODE,
    receipt_date=None,
):
    if receipt_date is None:
        receipt_date = timezone.now()
    money_type_code = money_type_code or DEFAULT_MONEY_TYPE_CODE

    receipt_lines = []
    tax_groups = {}

    for line_no, item in enumerate(order.items.select_related("product"), start=1):
        product = item.product
        tax_code, tax_percent, tax_id = _product_tax_meta(product)
        unit_price_inclusive = _to_payment_amount(order, item.price)
        unit_price = _to_tax_exclusive(unit_price_inclusive, tax_percent)
        line_total = (unit_price * item.quantity).quantize(
            TWOPLACES, rounding=ROUND_HALF_UP
        )
        tax_key = (tax_code, str(tax_percent), tax_id)

        receipt_lines.append(
            {
                "receiptLineType": RECEIPT_LINE_TYPE,
                "receiptLineNo": line_no,
                "receiptLineHSCode": product.hs_code or "00000000",
                "receiptLineName": product.name,
                "receiptLinePrice": _money(unit_price),
                "receiptLineQuantity": _quantity(item.quantity),
                "receiptLineTotal": _money(line_total),
                "taxCode": tax_code,
                "taxPercent": _money(tax_percent),
                "taxID": tax_id,
            }
        )

        group = tax_groups.setdefault(
            tax_key,
            {
                "taxCode": tax_code,
                "taxPercent": _money(tax_percent),
                "taxID": tax_id,
                "salesAmount": Decimal("0"),
            },
        )
        group["salesAmount"] += line_total

    receipt_taxes = []
    receipt_total = Decimal("0")
    for group in tax_groups.values():
        sales_amount = group["salesAmount"].quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        tax_percent = Decimal(str(group["taxPercent"]))
        tax_amount = (
            sales_amount * tax_percent / Decimal("100")
        ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        sales_with_tax = sales_amount + tax_amount
        receipt_total += sales_with_tax
        if tax_amount > 0:
            receipt_taxes.append(
                {
                    "taxCode": group["taxCode"],
                    "taxPercent": group["taxPercent"],
                    "taxID": group["taxID"],
                    "taxAmount": _money(tax_amount),
                    "salesAmountWithTax": _money(sales_with_tax),
                }
            )

    receipt_total = receipt_total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    receipt = {
        "receiptType": RECEIPT_TYPE,
        "receiptCurrency": _payment_currency_code(order),
        "receiptCounter": receipt_counter,
        "receiptGlobalNo": receipt_global_no,
        "invoiceNo": invoice_no,
        "buyerData": None,
        "receiptNotes": None,
        "receiptDate": _format_receipt_date(receipt_date),
        "creditDebitNote": None,
        "receiptLinesTaxInclusive": False,
        "receiptLines": receipt_lines,
        "receiptTaxes": receipt_taxes,
        "receiptPayments": [
            {
                "moneyTypeCode": money_type_code,
                "paymentAmount": _money(receipt_total),
            }
        ],
        "receiptTotal": _money(receipt_total),
        "receiptPrintForm": RECEIPT_PRINT_FORM,
    }
    return {"receipt": receipt}
