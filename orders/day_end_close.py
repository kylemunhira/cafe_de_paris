from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from payments.models import Currency

from .day_end import _decimal_or_none, build_day_end_report, local_day_range
from .day_end_serialization import serialize_day_end_report
from .models import DayEndCashLine, DayEndClose
from .serializers import staff_display_name


class DayEndValidationError(Exception):
    """Raised when day-end cash-up input is invalid for the branch."""


def validate_fiscal_counted_currencies(branch, counted_by_currency: dict | None) -> None:
    """Fiscal branches may count only one currency code (e.g. all USD or all ZWG)."""
    if not getattr(branch, "fiscalization_enabled", False):
        return
    if not counted_by_currency:
        return

    currency_ids = []
    for currency_id, raw in counted_by_currency.items():
        if _decimal_or_none(raw) is None:
            continue
        try:
            currency_ids.append(int(currency_id))
        except (TypeError, ValueError):
            continue

    if len(currency_ids) < 2:
        return

    codes = {
        (code or "").strip().upper()
        for code in Currency.objects.filter(pk__in=currency_ids).values_list(
            "code", flat=True
        )
    }
    codes.discard("")
    if len(codes) > 1:
        raise DayEndValidationError(
            "On fiscal branches, counted amounts must use the same currency code "
            f"({' or '.join(sorted(codes))}). Do not mix USD and ZWG."
        )


def parse_counted_from_body(data) -> dict:
    """Accept counted map from POST body (dict or counted_* keys)."""
    counted = {}
    if not isinstance(data, dict):
        return counted

    raw_map = data.get("counted")
    if isinstance(raw_map, dict):
        for key, value in raw_map.items():
            try:
                currency_id = int(key)
            except (TypeError, ValueError):
                continue
            counted[currency_id] = value

    for key, value in data.items():
        if not isinstance(key, str) or not key.startswith("counted_"):
            continue
        try:
            currency_id = int(key.split("counted_", 1)[1])
        except (TypeError, ValueError):
            continue
        counted[currency_id] = value

    return counted


@transaction.atomic
def save_day_end_close(
    branch,
    report_date=None,
    counted_by_currency: dict | None = None,
    user=None,
    notes: str = "",
) -> tuple[DayEndClose, dict]:
    """Build the live day-end report and persist variance + activity snapshot."""
    counted = counted_by_currency or {}
    validate_fiscal_counted_currencies(branch, counted)
    _, _, resolved_date = local_day_range(report_date)
    report = build_day_end_report(
        branch,
        resolved_date,
        counted_by_currency=counted,
    )
    snapshot = serialize_day_end_report(report)

    close, _created = DayEndClose.objects.update_or_create(
        branch=branch,
        report_date=resolved_date,
        defaults={
            "closed_by": user if getattr(user, "is_authenticated", False) else None,
            "notes": (notes or "").strip()[:255],
            "order_count": report["order_count"],
            "gross_total": report["gross_total"] or Decimal("0"),
            "expenses_total": report["expenses_total"] or Decimal("0"),
            "variance_total": report["variance_total"] or Decimal("0"),
            "has_counted_entries": bool(report["has_counted_entries"]),
            "activity_snapshot": snapshot,
        },
    )

    close.cash_lines.all().delete()
    currency_ids = [
        row.get("payment_currency__id")
        for row in report.get("cashup_rows") or []
        if row.get("payment_currency__id") is not None
    ]
    currencies = {
        currency.id: currency
        for currency in Currency.objects.filter(pk__in=currency_ids)
    }
    lines = []
    for row in report.get("cashup_rows") or []:
        currency_id = row.get("payment_currency__id")
        currency = currencies.get(currency_id)
        if currency is None:
            continue
        lines.append(
            DayEndCashLine(
                day_end=close,
                currency=currency,
                sales_total=row.get("total_paid") or Decimal("0"),
                deposits_total=row.get("deposits_total") or Decimal("0"),
                expenses_total=row.get("expenses_total") or Decimal("0"),
                expected_total=row.get("expected_total") or Decimal("0"),
                net_expected_total=row.get("net_expected_total") or Decimal("0"),
                counted_total=_decimal_or_none(row.get("counted_total")),
                variance=_decimal_or_none(row.get("variance")),
            )
        )
    if lines:
        DayEndCashLine.objects.bulk_create(lines)

    close.refresh_from_db()
    return close, report


def serialize_day_end_close(close: DayEndClose, *, include_snapshot: bool = False) -> dict:
    cash_lines = []
    for line in close.cash_lines.select_related("currency").all():
        cash_lines.append(
            {
                "currency": {
                    "id": line.currency_id,
                    "code": line.currency.code,
                    "name": line.currency.name,
                    "symbol": line.currency.symbol,
                },
                "sales_total": str(line.sales_total),
                "deposits_total": str(line.deposits_total),
                "expenses_total": str(line.expenses_total),
                "expected_total": str(line.expected_total),
                "net_expected_total": str(line.net_expected_total),
                "counted_total": (
                    str(line.counted_total) if line.counted_total is not None else None
                ),
                "variance": str(line.variance) if line.variance is not None else None,
            }
        )

    payload = {
        "id": close.id,
        "branch": {
            "id": close.branch_id,
            "name": close.branch.name,
            "location": close.branch.location,
        },
        "report_date": close.report_date.isoformat(),
        "closed_at": close.closed_at.isoformat() if close.closed_at else None,
        "closed_by": close.closed_by_id,
        "closed_by_name": staff_display_name(close.closed_by) if close.closed_by_id else "",
        "notes": close.notes or "",
        "order_count": close.order_count,
        "gross_total": str(close.gross_total),
        "expenses_total": str(close.expenses_total),
        "variance_total": str(close.variance_total),
        "has_counted_entries": close.has_counted_entries,
        "cash_lines": cash_lines,
    }
    if include_snapshot:
        payload["activity_snapshot"] = close.activity_snapshot or {}
    return payload


def parse_report_date_param(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)
