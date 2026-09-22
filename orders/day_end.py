from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Min, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    Expense,
    Order,
    OrderItem,
    OrderItemAddon,
    OrderPayment,
    OrderStatus,
    OrderType,
    PaymentMethod,
    TenderMethod,
)
from .tax import line_amount, split_inclusive_total

ORDER_TYPE_LABELS = dict(OrderType.choices)
TENDER_METHOD_LABELS = dict(TenderMethod.choices)


def local_day_range(report_date=None):
    if report_date is None:
        report_date = timezone.localdate()
    elif isinstance(report_date, str):
        report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    elif isinstance(report_date, datetime):
        report_date = report_date.date()

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(report_date, datetime.min.time()), tz)
    end = start + timedelta(days=1)
    return start, end, report_date


def _decimal_or_none(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def build_day_end_report(
    branch, report_date: date | str | None = None, counted_by_currency: dict | None = None
) -> dict:
    start, end, report_date = local_day_range(report_date)

    orders_qs = Order.objects.filter(
        branch=branch,
        status=OrderStatus.PAID,
        paid_at__gte=start,
        paid_at__lt=end,
    )

    order_count = orders_qs.count()
    gross_total = orders_qs.aggregate(
        total=Coalesce(Sum("total_amount"), Decimal("0"))
    )["total"]
    tips_total = orders_qs.aggregate(
        total=Coalesce(Sum("tip_amount"), Decimal("0"))
    )["total"]

    tips_by_currency = list(
        orders_qs.exclude(tip_amount=0)
        .values(
            "payment_currency__id",
            "payment_currency__code",
            "payment_currency__name",
            "payment_currency__symbol",
        )
        .annotate(
            order_count=Count("id"),
            tips_total=Coalesce(Sum("tip_amount"), Decimal("0")),
        )
        .order_by("payment_currency__name")
    )

    order_types = [
        {
            "label": ORDER_TYPE_LABELS.get(row["order_type"], row["order_type"]),
            "count": row["count"],
        }
        for row in orders_qs.values("order_type")
        .annotate(count=Count("id"))
        .order_by("order_type")
    ]

    payments = list(
        OrderPayment.objects.filter(
            order__branch=branch,
            order__status=OrderStatus.PAID,
            order__paid_at__gte=start,
            order__paid_at__lt=end,
        )
        .values(
            "currency__id",
            "currency__code",
            "currency__name",
            "currency__symbol",
        )
        .annotate(
            order_count=Count("order", distinct=True),
            total_paid=Coalesce(Sum("amount"), Decimal("0")),
        )
        .order_by("currency__name")
    )
    # Keep day-end template field names stable.
    for row in payments:
        row["payment_currency__id"] = row.pop("currency__id")
        row["payment_currency__code"] = row.pop("currency__code")
        row["payment_currency__name"] = row.pop("currency__name")
        row["payment_currency__symbol"] = row.pop("currency__symbol")

    payments_by_method = list(
        OrderPayment.objects.filter(
            order__branch=branch,
            order__status=OrderStatus.PAID,
            order__paid_at__gte=start,
            order__paid_at__lt=end,
        )
        .values(
            "currency__name",
        )
        .annotate(
            payment_count=Count("id"),
            total_paid=Coalesce(Sum("amount"), Decimal("0")),
            currency__code=Min("currency__code"),
            currency__symbol=Min("currency__symbol"),
            method=Min("method"),
        )
        .order_by("currency__name")
    )
    for row in payments_by_method:
        row["method_label"] = TENDER_METHOD_LABELS.get(row["method"], row["method"])

    from customers.models import CustomerAccountTransaction, CustomerAccountTransactionType

    deposit_rows = list(
        CustomerAccountTransaction.objects.filter(
            branch=branch,
            transaction_type=CustomerAccountTransactionType.DEPOSIT,
            created_at__gte=start,
            created_at__lt=end,
        )
        .values(
            "currency__id",
            "currency__code",
            "currency__name",
            "currency__symbol",
        )
        .annotate(total_received=Coalesce(Sum("amount_received"), Decimal("0")))
        .order_by("currency__name")
    )
    deposits_by_currency = {
        row["currency__id"]: row["total_received"] or Decimal("0") for row in deposit_rows
    }

    account_transactions = []
    account_deposits = []
    account_withdrawals = []
    account_deposits_total = Decimal("0")
    account_withdrawals_total = Decimal("0")
    for txn in (
        CustomerAccountTransaction.objects.filter(
            branch=branch,
            created_at__gte=start,
            created_at__lt=end,
        )
        .select_related("customer", "currency", "order", "recorded_by")
        .order_by("created_at", "id")
    ):
        row = {
            "id": txn.id,
            "customer_name": str(txn.customer),
            "transaction_type": txn.transaction_type,
            "statement_label": txn.statement_label,
            "amount": txn.amount,
            "amount_received": txn.amount_received,
            "balance_after": txn.balance_after,
            "order_id": txn.order_id,
            "notes": txn.notes,
            "created_at": txn.created_at,
            "currency__id": txn.currency_id,
            "currency__code": txn.currency.code if txn.currency else None,
            "currency__name": txn.currency.name if txn.currency else None,
            "currency__symbol": txn.currency.symbol if txn.currency else None,
            "recorded_by__username": txn.recorded_by.username if txn.recorded_by else None,
        }
        account_transactions.append(row)
        if txn.transaction_type == CustomerAccountTransactionType.DEPOSIT:
            account_deposits.append(row)
            # Amount is signed base-currency delta (negative for money onto account).
            account_deposits_total += -(txn.amount or Decimal("0"))
        elif txn.transaction_type == CustomerAccountTransactionType.PAYMENT:
            account_withdrawals.append(row)
            account_withdrawals_total += txn.amount or Decimal("0")

    # Account-paid sales (withdrawals) are tracked separately and must not enter
    # cash-up expected — expected uses tender OrderPayment totals + deposits only.
    account_payments_total = orders_qs.filter(
        payment_method=PaymentMethod.ACCOUNT
    ).aggregate(total=Coalesce(Sum("total_amount"), Decimal("0")))["total"]

    product_totals = defaultdict(
        lambda: {"product__name": "", "quantity": Decimal("0"), "revenue": Decimal("0")}
    )
    item_rows = OrderItem.objects.filter(
        order__branch=branch,
        order__status=OrderStatus.PAID,
        order__paid_at__gte=start,
        order__paid_at__lt=end,
    ).values_list("product_id", "product__name", "quantity", "price")

    for product_id, product_name, quantity, price in item_rows:
        bucket = product_totals[("product", product_id)]
        bucket["product__name"] = product_name
        bucket["quantity"] += Decimal(quantity)
        bucket["revenue"] += line_amount(quantity, price)

    # Priced menu add-ons (e.g. almond milk) are separate sold lines.
    addon_rows = OrderItemAddon.objects.filter(
        order_item__order__branch=branch,
        order_item__order__status=OrderStatus.PAID,
        order_item__order__paid_at__gte=start,
        order_item__order__paid_at__lt=end,
    ).values_list(
        "menu_addon_id",
        "name",
        "order_item__quantity",
        "price",
    )

    for menu_addon_id, addon_name, quantity, price in addon_rows:
        bucket = product_totals[("addon", menu_addon_id)]
        bucket["product__name"] = addon_name
        bucket["quantity"] += Decimal(quantity)
        bucket["revenue"] += line_amount(quantity, price)

    products = sorted(
        product_totals.values(),
        key=lambda row: (-row["revenue"], row["product__name"]),
    )

    tax_breakdown = split_inclusive_total(
        gross_total,
        apply_zta=bool(getattr(branch, "fiscalization_enabled", False)),
    )

    expense_rows = list(
        Expense.objects.filter(branch=branch, expense_date=report_date)
        .select_related("currency", "supplier")
        .order_by("created_at")
        .values(
            "description",
            "amount",
            "currency__id",
            "currency__code",
            "currency__name",
            "currency__symbol",
            "supplier__name",
        )
    )
    expenses_by_currency = defaultdict(lambda: Decimal("0"))
    for row in expense_rows:
        currency_id = row.get("currency__id")
        if currency_id is not None:
            expenses_by_currency[currency_id] += row["amount"] or Decimal("0")
    expenses_total = sum(expenses_by_currency.values(), Decimal("0"))

    counted_by_currency = counted_by_currency or {}
    currency_meta = {}
    for payment in payments:
        currency_id = payment.get("payment_currency__id")
        if currency_id is not None:
            currency_meta[currency_id] = {
                "payment_currency__id": currency_id,
                "payment_currency__code": payment.get("payment_currency__code"),
                "payment_currency__name": payment.get("payment_currency__name"),
                "payment_currency__symbol": payment.get("payment_currency__symbol"),
            }
    for row in deposit_rows:
        currency_id = row.get("currency__id")
        if currency_id is not None and currency_id not in currency_meta:
            currency_meta[currency_id] = {
                "payment_currency__id": currency_id,
                "payment_currency__code": row.get("currency__code"),
                "payment_currency__name": row.get("currency__name"),
                "payment_currency__symbol": row.get("currency__symbol"),
            }

    cashup_rows = []
    variance_total = Decimal("0")
    has_counted_entries = False
    payment_by_currency = {
        payment.get("payment_currency__id"): payment for payment in payments
    }

    for currency_id in sorted(currency_meta.keys()):
        payment = payment_by_currency.get(currency_id, {})
        # Tender/sales collected only (OrderPayment). Account withdrawals excluded.
        sales_total = payment.get("total_paid") or Decimal("0")
        deposits_total = deposits_by_currency.get(currency_id, Decimal("0"))
        expected = sales_total + deposits_total
        expenses_for_currency = expenses_by_currency.get(currency_id, Decimal("0"))
        net_expected = expected - expenses_for_currency
        counted = _decimal_or_none(counted_by_currency.get(currency_id))
        variance = None
        if counted is not None:
            variance = counted - net_expected
            variance_total += variance
            has_counted_entries = True
        cashup_rows.append(
            {
                **currency_meta[currency_id],
                "order_count": payment.get("order_count", 0),
                "total_paid": sales_total,
                "deposits_total": deposits_total,
                "expected_total": expected,
                "expenses_total": expenses_for_currency,
                "net_expected_total": net_expected,
                "counted_total": counted,
                "variance": variance,
            }
        )

    return {
        "report_date": report_date,
        "order_count": order_count,
        "gross_total": gross_total,
        "tips_total": tips_total,
        "tips_by_currency": tips_by_currency,
        "tax_breakdown": tax_breakdown,
        "order_types": order_types,
        "payments": payments,
        "payments_by_method": payments_by_method,
        "account_payments_total": account_payments_total,
        "account_transactions": account_transactions,
        "account_deposits": account_deposits,
        "account_withdrawals": account_withdrawals,
        "account_deposits_total": account_deposits_total,
        "account_withdrawals_total": account_withdrawals_total,
        "cashup_rows": cashup_rows,
        "has_counted_entries": has_counted_entries,
        "variance_total": variance_total,
        "expenses": expense_rows,
        "expenses_total": expenses_total,
        "products": products,
    }
