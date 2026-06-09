from typing import Any

from .models import FiscalReceipt, FiscalReceiptStatus

ZIMRA_RESPONSE_FIELDS = {
    "deviceBranchName": "device_branch_name",
    "deviceSerialNo": "device_serial_no",
    "fiscalDayNumber": "fiscal_day_number",
    "invoiceNumber": "fiscal_invoice_number",
    "qrString": "qr_string",
    "qrUrl": "qr_url",
    "receiptCounter": "receipt_counter",
    "receiptGlobalNo": "receipt_global_no",
    "verificationCode": "verification_code",
}

_WRAPPER_KEYS = ("data", "result", "receipt", "response", "body")


def _extract_value(payload: Any, field_name: str):
    if not isinstance(payload, dict):
        return None
    if field_name in payload:
        return payload[field_name]
    for key in _WRAPPER_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict) and field_name in nested:
            return nested[field_name]
    return None


def parse_zimra_response_body(body: Any) -> dict:
    parsed = {}
    for source_key, model_field in ZIMRA_RESPONSE_FIELDS.items():
        value = _extract_value(body, source_key)
        if value is None or value == "":
            continue
        if model_field in ("receipt_counter", "receipt_global_no", "fiscal_day_number"):
            try:
                parsed[model_field] = int(value)
            except (TypeError, ValueError):
                continue
        else:
            parsed[model_field] = str(value)
    return parsed


def apply_zimra_response(fiscal_receipt: FiscalReceipt, submit_result: dict) -> FiscalReceipt:
    fiscal_receipt.zimra_response = submit_result
    body = submit_result.get("body")
    parsed_fields = parse_zimra_response_body(body)

    update_fields = ["zimra_response", "status"]
    for field_name, value in parsed_fields.items():
        setattr(fiscal_receipt, field_name, value)
        update_fields.append(field_name)

    if parsed_fields.get("verification_code") or parsed_fields.get("qr_string"):
        fiscal_receipt.status = FiscalReceiptStatus.ACCEPTED
    else:
        fiscal_receipt.status = FiscalReceiptStatus.SUBMITTED

    fiscal_receipt.save(update_fields=update_fields)
    return fiscal_receipt


def fiscal_receipt_summary(fiscal_receipt: FiscalReceipt) -> dict:
    return {
        "deviceBranchName": fiscal_receipt.device_branch_name,
        "deviceSerialNo": fiscal_receipt.device_serial_no,
        "fiscalDayNumber": fiscal_receipt.fiscal_day_number,
        "invoiceNumber": fiscal_receipt.fiscal_invoice_number,
        "qrString": fiscal_receipt.qr_string,
        "qrUrl": fiscal_receipt.qr_url,
        "receiptCounter": fiscal_receipt.receipt_counter,
        "receiptGlobalNo": fiscal_receipt.receipt_global_no,
        "verificationCode": fiscal_receipt.verification_code,
    }
