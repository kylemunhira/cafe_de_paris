from django.conf import settings

from .client import call_device_api, call_device_api_with_fallbacks, resolve_device_id
from .exceptions import ZimraConfigurationError


def _require_fiscal_branch(branch):
    if not branch.fiscalization_enabled:
        raise ZimraConfigurationError(
            f'Branch "{branch.name}" is not configured for fiscalization.'
        )
    if not branch.is_active:
        raise ZimraConfigurationError(
            f'Branch "{branch.name}" is inactive.'
        )
    return resolve_device_id(branch)


def _unwrap_body(body):
    if not isinstance(body, dict):
        return {}
    nested = body.get("data")
    if isinstance(nested, dict):
        return nested
    return body


def normalize_fiscal_day_status(result: dict) -> dict:
    """Normalize middleware / FDMS status payload for the UI."""
    body = _unwrap_body(result.get("body") or {})
    status = (
        body.get("fiscalDayStatus")
        or body.get("fiscal_day_status")
        or body.get("status")
        or ""
    )
    fiscal_day_number = (
        body.get("lastFiscalDayNo")
        or body.get("fiscalDayNo")
        or body.get("fiscal_day_number")
    )
    return {
        "fiscal_day_status": status,
        "fiscal_day_number": fiscal_day_number,
        "last_receipt_global_no": body.get("lastReceiptGlobalNo")
        or body.get("last_receipt_global_no"),
        "fiscal_day_closed_at": body.get("fiscalDayClosed")
        or body.get("fiscal_day_closed"),
        "operation_id": body.get("operationID") or body.get("operation_id"),
        "can_open_day": status in ("FiscalDayClosed", ""),
        "can_close_day": status in ("FiscalDayOpened", "FiscalDayCloseFailed"),
        "raw": body,
    }


def get_fiscal_day_status(branch) -> dict:
    device_id = _require_fiscal_branch(branch)
    primary = getattr(settings, "ZIMRA_GET_STATUS_ACTION", "getstatus")
    fallbacks = getattr(settings, "ZIMRA_GET_STATUS_FALLBACKS", "")
    actions = [primary] + [
        action.strip()
        for action in fallbacks.split(",")
        if action.strip() and action.strip() != primary
    ]
    result = call_device_api_with_fallbacks(device_id, actions, method="GET")
    normalized = normalize_fiscal_day_status(result)
    normalized["device_id"] = device_id
    normalized["branch_id"] = branch.id
    normalized["branch_name"] = branch.name
    return normalized


def open_fiscal_day(branch) -> dict:
    device_id = _require_fiscal_branch(branch)
    primary = getattr(settings, "ZIMRA_OPEN_DAY_ACTION", "openday")
    fallbacks = getattr(settings, "ZIMRA_OPEN_DAY_FALLBACKS", "")
    actions = [primary] + [
        action.strip()
        for action in fallbacks.split(",")
        if action.strip() and action.strip() != primary
    ]
    result = call_device_api_with_fallbacks(
        device_id,
        actions,
        method="POST",
        payload={},
    )
    normalized["device_id"] = device_id
    normalized["branch_id"] = branch.id
    normalized["branch_name"] = branch.name
    return normalized


def close_fiscal_day(branch) -> dict:
    device_id = _require_fiscal_branch(branch)
    action = getattr(settings, "ZIMRA_CLOSE_DAY_ACTION", "close_day")
    result = call_device_api(device_id, action, method="POST", payload={})
    normalized = normalize_fiscal_day_status(result)
    normalized["device_id"] = device_id
    normalized["branch_id"] = branch.id
    normalized["branch_name"] = branch.name
    return normalized
