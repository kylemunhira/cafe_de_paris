"""Import actual customer account balances from Customer_Accounts_final.xlsx."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import openpyxl
from django.db import transaction

from branches.models import Branch
from catalog.costings_parse import normalize_name
from customers.csv_io import _normalize_phone, customer_name_key
from customers.models import Customer
from customers.services import apply_account_balance_adjustment

NAME_HEADERS = {"name", "customer", "customer name"}
PHONE_HEADERS = {"phone", "phone number", "phonenumber", "mobile"}
BALANCE_HEADERS = {"balance", "account balance", "amount"}


def phone_match_key(value) -> str:
    """Digits-only phone key; drop a single leading 0 for local numbers."""
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) > 1 and digits.startswith("0"):
        digits = digits.lstrip("0") or "0"
    return digits


def parse_balance(value) -> Decimal | None:
    """Parse Excel balance cells. Blank / '-' mean no balance to import."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.01"))

    text = str(value).strip()
    if not text or text in {"-", "—", "n/a", "N/A", "none", "None"}:
        return None

    text = text.replace(",", "").replace(" ", "")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    if text.startswith("+"):
        text = text[1:]

    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid balance {value!r}") from exc

    if negative:
        amount = -amount
    return amount.quantize(Decimal("0.01"))


def _split_name(full_name: str) -> tuple[str, str]:
    parts = normalize_name(full_name).split(" ", 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first, last


def _header_map(row) -> dict[str, int]:
    mapping = {}
    for index, cell in enumerate(row):
        key = normalize_name(cell).casefold()
        if not key:
            continue
        if key in NAME_HEADERS and "name" not in mapping:
            mapping["name"] = index
        elif key in PHONE_HEADERS and "phone" not in mapping:
            mapping["phone"] = index
        elif key in BALANCE_HEADERS and "balance" not in mapping:
            mapping["balance"] = index
    return mapping


def _load_customer_indexes():
    by_phone = {}
    by_name = {}
    for customer in Customer.objects.all():
        phone_key = phone_match_key(customer.phone)
        if phone_key:
            by_phone.setdefault(phone_key, customer)
        name_key = customer_name_key(customer.first_name, customer.last_name)
        if name_key:
            by_name.setdefault(name_key, customer)
        # Also index by first name alone when last name is blank in DB.
        first_only = customer_name_key(customer.first_name, "")
        if first_only and not customer.last_name:
            by_name.setdefault(first_only, customer)
    return by_phone, by_name


def _names_compatible(excel_name, customer) -> bool:
    first, last = _split_name(excel_name)
    excel_full = customer_name_key(first, last)
    excel_first = customer_name_key(first, "")
    customer_full = customer_name_key(customer.first_name, customer.last_name)
    customer_first = customer_name_key(customer.first_name, "")
    if excel_full and excel_full == customer_full:
        return True
    if excel_first and excel_first == customer_first:
        return True
    return False


def _find_customer(name, phone, *, by_phone, by_name):
    phone_key = phone_match_key(phone)
    phone_customer = by_phone.get(phone_key) if phone_key else None
    if phone_customer is not None and _names_compatible(name, phone_customer):
        return phone_customer, "phone"

    first, last = _split_name(name)
    full_key = customer_name_key(first, last)
    if full_key and full_key in by_name:
        return by_name[full_key], "name"

    first_key = customer_name_key(first, "")
    if first_key and first_key in by_name:
        return by_name[first_key], "name"

    return None, None


def _default_branch(branch=None, branch_id=None):
    if branch is not None:
        return branch
    if branch_id is not None:
        return Branch.objects.get(pk=branch_id)
    branch = Branch.objects.filter(is_active=True).order_by("id").first()
    if branch is None:
        raise ValueError("No active branch found to record balance adjustments.")
    return branch


def read_balance_rows(workbook_path) -> list[dict]:
    path = Path(workbook_path)
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    if not rows:
        raise ValueError("Workbook is empty")

    headers = _header_map(rows[0])
    if "name" not in headers or "balance" not in headers:
        raise ValueError("Workbook must include Name and Balance columns")

    parsed = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        name = normalize_name(row[headers["name"]] if headers["name"] < len(row) else None)
        phone = _normalize_phone(
            row[headers["phone"]] if "phone" in headers and headers["phone"] < len(row) else None
        )
        raw_balance = row[headers["balance"]] if headers["balance"] < len(row) else None
        try:
            balance = parse_balance(raw_balance)
        except ValueError as exc:
            parsed.append(
                {
                    "row": row_number,
                    "name": name,
                    "phone": phone,
                    "balance": None,
                    "error": str(exc),
                }
            )
            continue

        if balance is None:
            continue

        parsed.append(
            {
                "row": row_number,
                "name": name,
                "phone": phone,
                "balance": balance,
                "error": None,
            }
        )
    return parsed


def import_customer_balances(
    workbook_path,
    *,
    branch=None,
    branch_id=None,
    dry_run=False,
    recorded_by=None,
    notes="Imported account balance from Customer_Accounts_final.xlsx",
):
    rows = read_balance_rows(workbook_path)
    branch_obj = _default_branch(branch=branch, branch_id=branch_id)
    by_phone, by_name = _load_customer_indexes()

    result = {
        "adjusted": 0,
        "unchanged": 0,
        "missing": 0,
        "skipped": 0,
        "errors": [],
        "details": [],
    }
    seen_customers = {}

    def process():
        for row in rows:
            if row.get("error"):
                result["skipped"] += 1
                result["details"].append(
                    {
                        "row": row["row"],
                        "name": row.get("name") or "",
                        "phone": row.get("phone") or "",
                        "excel_balance": None,
                        "status": "skipped",
                        "message": row["error"],
                    }
                )
                continue
            if not row["name"]:
                result["skipped"] += 1
                result["details"].append(
                    {
                        "row": row["row"],
                        "name": "",
                        "phone": row.get("phone") or "",
                        "excel_balance": str(row["balance"]),
                        "status": "skipped",
                        "message": "name is required",
                    }
                )
                continue

            customer, matched_by = _find_customer(
                row["name"],
                row["phone"],
                by_phone=by_phone,
                by_name=by_name,
            )
            if customer is None:
                result["missing"] += 1
                result["details"].append(
                    {
                        "row": row["row"],
                        "name": row["name"],
                        "phone": row["phone"],
                        "excel_balance": str(row["balance"]),
                        "status": "missing",
                    }
                )
                continue

            before = customer.account_balance
            target = row["balance"]
            delta = (target - before).quantize(Decimal("0.01"))
            prior_row = seen_customers.get(customer.id)
            detail = {
                "row": row["row"],
                "customer_id": customer.id,
                "name": str(customer),
                "phone": customer.phone,
                "matched_by": matched_by,
                "before": str(before),
                "excel_balance": str(target),
                "delta": str(delta),
                "after": str(target),
            }
            if prior_row is not None:
                detail["message"] = (
                    f"duplicate match — already updated from row {prior_row}; "
                    "later Excel row wins"
                )
            seen_customers[customer.id] = row["row"]

            if delta == Decimal("0"):
                result["unchanged"] += 1
                detail["status"] = "unchanged"
                result["details"].append(detail)
                continue

            if not dry_run:
                txn = apply_account_balance_adjustment(
                    customer=customer,
                    branch=branch_obj,
                    target_balance=target,
                    notes=notes,
                    recorded_by=recorded_by,
                )
                if txn is None:
                    result["unchanged"] += 1
                    detail["status"] = "unchanged"
                else:
                    customer.account_balance = target
                    result["adjusted"] += 1
                    detail["status"] = "adjusted"
                    detail["transaction_id"] = txn.id
            else:
                customer.account_balance = target
                result["adjusted"] += 1
                detail["status"] = "adjusted"

            result["details"].append(detail)

    if dry_run:
        process()
    else:
        with transaction.atomic():
            process()

    return result
