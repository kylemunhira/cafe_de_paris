from datetime import date
from decimal import Decimal

from reports.services import default_date_range, parse_date

from .models import Customer, CustomerAccountTransaction


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def parse_statement_filters(from_date=None, to_date=None, branch_id=None, *, all_time: bool = False):
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

    if all_time:
        return None, None, parsed_branch

    if parsed_from and not parsed_to:
        from django.utils import timezone

        parsed_to = timezone.localdate()
    elif parsed_to and not parsed_from:
        parsed_from = parsed_to.replace(day=1)
    elif not parsed_from and not parsed_to:
        parsed_from, parsed_to = default_date_range()

    return parsed_from, parsed_to, parsed_branch


def build_customer_statement_report(
    customer: Customer,
    *,
    from_date=None,
    to_date=None,
    branch_id=None,
    all_time: bool = False,
):
    # No dates + no explicit all_time still means full ledger for history views.
    if not all_time and not from_date and not to_date:
        all_time = True

    from_date, to_date, branch_id = parse_statement_filters(
        from_date, to_date, branch_id, all_time=all_time
    )

    qs = CustomerAccountTransaction.objects.filter(customer=customer)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    if all_time or from_date is None or to_date is None:
        opening_balance = Decimal("0")
        period_qs = qs.select_related("branch", "currency", "order", "recorded_by").order_by(
            "created_at", "id"
        )
        transactions = list(period_qs[:500])
        closing_balance = (
            _quantize(transactions[-1].balance_after) if transactions else Decimal("0")
        )
        period = {"from": None, "to": None}
    else:
        prior = (
            qs.filter(created_at__date__lt=from_date)
            .order_by("-created_at", "-id")
            .first()
        )
        opening_balance = _quantize(prior.balance_after) if prior else Decimal("0")

        period_qs = (
            qs.filter(
                created_at__date__gte=from_date,
                created_at__date__lte=to_date,
            )
            .select_related("branch", "currency", "order", "recorded_by")
            .order_by("created_at", "id")
        )
        transactions = list(period_qs)
        closing_balance = (
            _quantize(transactions[-1].balance_after) if transactions else opening_balance
        )
        period = {"from": from_date.isoformat(), "to": to_date.isoformat()}

    # Credits reduce what is owed / increase prepaid (negative deltas).
    # Debits increase what is owed (positive deltas).
    total_credits = _quantize(
        sum((-txn.amount for txn in transactions if txn.amount < 0), Decimal("0"))
    )
    total_debits = _quantize(
        sum((txn.amount for txn in transactions if txn.amount > 0), Decimal("0"))
    )

    return {
        "customer_id": customer.pk,
        "period": period,
        "filters": {"branch_id": branch_id},
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "current_balance": _quantize(customer.account_balance),
        "total_credits": total_credits,
        "total_debits": total_debits,
        "transaction_count": len(transactions),
        "transactions": transactions,
    }
