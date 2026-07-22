import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction

from catalog.costings_parse import normalize_name
from customers.models import Customer, CustomerAccountType

CSV_HEADERS = [
    "id",
    "first_name",
    "last_name",
    "phone",
    "email",
    "account_type",
    "loyalty_points",
    "credit_limit",
]

VALID_ACCOUNT_TYPES = {choice.value for choice in CustomerAccountType}


def _normalize_phone(value):
    return normalize_name(value)


def _normalize_email(value):
    text = normalize_name(value)
    return text.casefold() if text else ""


def customer_name_key(first_name, last_name=""):
    return f"{normalize_name(first_name)} {normalize_name(last_name)}".strip().casefold()


def _parse_account_type(value):
    if value is None or str(value).strip() == "":
        return CustomerAccountType.REGULAR
    normalized = str(value).strip().lower()
    if normalized in VALID_ACCOUNT_TYPES:
        return normalized
    raise ValueError(
        f"invalid account_type {value!r} — use regular, family, or staff"
    )


def _parse_non_negative_int(value, field_name, default=0):
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be zero or greater")
    return parsed


def _parse_non_negative_decimal(value, field_name, default=Decimal("0")):
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be zero or greater")
    return parsed


def _customer_payload_from_row(row, available_fields):
    first_name = normalize_name(row.get("first_name"))
    if not first_name:
        raise ValueError("first_name is required")

    payload = {"first_name": first_name}

    if "last_name" in available_fields:
        payload["last_name"] = normalize_name(row.get("last_name"))
    if "phone" in available_fields:
        payload["phone"] = _normalize_phone(row.get("phone"))
    if "email" in available_fields:
        payload["email"] = normalize_name(row.get("email"))
    if "account_type" in available_fields:
        payload["account_type"] = _parse_account_type(row.get("account_type"))
    if "loyalty_points" in available_fields:
        payload["loyalty_points"] = _parse_non_negative_int(
            row.get("loyalty_points"),
            "loyalty_points",
        )
    if "credit_limit" in available_fields:
        payload["credit_limit"] = _parse_non_negative_decimal(
            row.get("credit_limit"),
            "credit_limit",
        )

    return payload


def _create_defaults():
    return {
        "last_name": "",
        "phone": "",
        "email": "",
        "account_type": CustomerAccountType.REGULAR,
        "loyalty_points": 0,
        "credit_limit": Decimal("0"),
    }


def _payload_for_create(payload):
    return {**_create_defaults(), **payload}


def _load_customer_indexes():
    customers_by_id = {}
    customers_by_phone = {}
    customers_by_email = {}
    customers_by_name = {}

    for customer in Customer.objects.all():
        customers_by_id[customer.id] = customer
        phone = _normalize_phone(customer.phone)
        if phone:
            customers_by_phone.setdefault(phone, customer)
        email = _normalize_email(customer.email)
        if email:
            customers_by_email.setdefault(email, customer)
        name_key = customer_name_key(customer.first_name, customer.last_name)
        if name_key:
            customers_by_name.setdefault(name_key, customer)

    return customers_by_id, customers_by_phone, customers_by_email, customers_by_name


def _find_existing_customer(
    payload,
    *,
    available_fields,
    customers_by_phone,
    customers_by_email,
    customers_by_name,
):
    if "phone" in available_fields:
        phone = payload.get("phone", "")
        if phone:
            customer = customers_by_phone.get(phone)
            if customer:
                return customer

    if "email" in available_fields:
        email = _normalize_email(payload.get("email", ""))
        if email:
            customer = customers_by_email.get(email)
            if customer:
                return customer

    last_name = payload.get("last_name", "") if "last_name" in available_fields else ""
    name_key = customer_name_key(payload["first_name"], last_name)
    if name_key:
        return customers_by_name.get(name_key)
    return None


def _upsert_customer(
    payload,
    *,
    available_fields,
    customer_id=None,
    customers_by_id=None,
    customers_by_phone=None,
    customers_by_email=None,
    customers_by_name=None,
):
    if customer_id:
        customer = (customers_by_id or {}).get(customer_id)
        if not customer:
            raise ValueError(f"customer id {customer_id} not found")
        for field, value in payload.items():
            setattr(customer, field, value)
        customer.save()
        _update_indexes(
            customer,
            customers_by_phone=customers_by_phone,
            customers_by_email=customers_by_email,
            customers_by_name=customers_by_name,
        )
        return customer, "updated"

    customer = _find_existing_customer(
        payload,
        available_fields=available_fields,
        customers_by_phone=customers_by_phone,
        customers_by_email=customers_by_email,
        customers_by_name=customers_by_name,
    )
    if customer:
        for field, value in payload.items():
            setattr(customer, field, value)
        customer.save()
        _update_indexes(
            customer,
            customers_by_phone=customers_by_phone,
            customers_by_email=customers_by_email,
            customers_by_name=customers_by_name,
        )
        return customer, "updated"

    customer = Customer.objects.create(**_payload_for_create(payload))
    if customers_by_id is not None:
        customers_by_id[customer.id] = customer
    _update_indexes(
        customer,
        customers_by_phone=customers_by_phone,
        customers_by_email=customers_by_email,
        customers_by_name=customers_by_name,
    )
    return customer, "created"


def _update_indexes(customer, *, customers_by_phone, customers_by_email, customers_by_name):
    phone = _normalize_phone(customer.phone)
    if phone and customers_by_phone is not None:
        customers_by_phone[phone] = customer
    email = _normalize_email(customer.email)
    if email and customers_by_email is not None:
        customers_by_email[email] = customer
    name_key = customer_name_key(customer.first_name, customer.last_name)
    if name_key and customers_by_name is not None:
        customers_by_name[name_key] = customer


def import_customers_rows(rows, available_fields=None):
    if available_fields is None:
        available_fields = set()
        for row in rows:
            available_fields.update(row.keys())
        available_fields.add("first_name")
    created = 0
    updated = 0
    errors = []

    with transaction.atomic():
        (
            customers_by_id,
            customers_by_phone,
            customers_by_email,
            customers_by_name,
        ) = _load_customer_indexes()

        for row_number, row in enumerate(rows, start=2):
            try:
                payload = _customer_payload_from_row(row, available_fields)
                customer_id = None
                if "id" in available_fields:
                    raw_id = row.get("id")
                    if raw_id not in (None, ""):
                        customer_id = int(str(raw_id).strip())
                _, action = _upsert_customer(
                    payload,
                    available_fields=available_fields,
                    customer_id=customer_id,
                    customers_by_id=customers_by_id,
                    customers_by_phone=customers_by_phone,
                    customers_by_email=customers_by_email,
                    customers_by_name=customers_by_name,
                )
                if action == "created":
                    created += 1
                else:
                    updated += 1
            except Exception as exc:
                errors.append({"row": row_number, "message": str(exc)})

    if errors:
        transaction.set_rollback(True)

    return {"created": created, "updated": updated, "errors": errors}


def import_customers_csv(file_obj):
    try:
        text = io.TextIOWrapper(file_obj, encoding="utf-8-sig")
        reader = csv.DictReader(text)
    except UnicodeDecodeError:
        return {
            "created": 0,
            "updated": 0,
            "errors": [{"row": 0, "message": "File must be UTF-8 encoded CSV"}],
        }

    if not reader.fieldnames:
        return {
            "created": 0,
            "updated": 0,
            "errors": [{"row": 0, "message": "CSV file is empty"}],
        }

    normalized_headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    if "first_name" not in normalized_headers:
        return {
            "created": 0,
            "updated": 0,
            "errors": [{"row": 0, "message": "Missing required column: first_name"}],
        }

    available_fields = set(normalized_headers.keys())

    rows = []
    for raw_row in reader:
        row = {
            key.strip().lower(): (raw_row.get(header) or "").strip()
            for key, header in normalized_headers.items()
        }
        if not normalize_name(row.get("first_name")):
            continue
        rows.append(row)

    return import_customers_rows(rows, available_fields)


def export_customers_csv():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()
    for customer in Customer.objects.order_by("first_name", "last_name", "id"):
        writer.writerow(
            {
                "id": customer.id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "phone": customer.phone,
                "email": customer.email,
                "account_type": customer.account_type,
                "loyalty_points": customer.loyalty_points,
                "credit_limit": customer.credit_limit,
            }
        )
    return output.getvalue()
