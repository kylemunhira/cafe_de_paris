import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .exceptions import ZimraConfigurationError, ZimraSubmissionError

logger = logging.getLogger("zimra_fiscal")


def resolve_device_id(branch) -> str:
    device_id = (branch.zimra_device_id or "").strip()
    if device_id:
        return device_id

    default_id = (getattr(settings, "ZIMRA_DEFAULT_DEVICE_ID", "") or "").strip()
    if default_id:
        return default_id

    raise ZimraConfigurationError(
        f'Branch "{branch.name}" has no ZIMRA device ID configured.'
    )


def _fiscal_base_url() -> str:
    base_url = getattr(settings, "ZIMRA_FISCAL_BASE_URL", "").rstrip("/")
    if not base_url:
        raise ZimraConfigurationError("ZIMRA_FISCAL_BASE_URL is not configured.")
    return base_url


def build_device_action_url(device_id: str, action: str) -> str:
    return f"{_fiscal_base_url()}/api/{action}/{device_id}"


def build_submit_url(device_id: str) -> str:
    return build_device_action_url(device_id, "submit_receipt")


def _parse_response_body(raw_body: str):
    if not raw_body:
        return None
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return {"raw": raw_body}


def _log_json(label: str, data) -> None:
    try:
        formatted = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        formatted = repr(data)
    logger.info("ZIMRA %s:\n%s", label, formatted)


def _request_device(
    url: str,
    *,
    method: str,
    device_id: str,
    payload: dict | None = None,
    error_label: str = "request",
) -> dict:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
        _log_json("request payload", payload)

    logger.info("ZIMRA %s %s (device %s)", method, url, device_id)
    request = Request(url, data=data, headers=headers, method=method)
    timeout = getattr(settings, "ZIMRA_SUBMIT_TIMEOUT", 30)

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            parsed = _parse_response_body(raw)
            result = {
                "status_code": response.status,
                "body": parsed,
            }
            logger.info("ZIMRA response HTTP %s", response.status)
            _log_json("response body", parsed)
            return result
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed = _parse_response_body(raw)
        logger.error("ZIMRA response HTTP %s", exc.code)
        _log_json("error response body", parsed)
        raise ZimraSubmissionError(
            f"ZIMRA rejected the {error_label} (HTTP {exc.code}).",
            status_code=exc.code,
            response_body=parsed,
        ) from exc
    except URLError as exc:
        logger.error("ZIMRA connection failed: %s", exc.reason)
        raise ZimraSubmissionError(
            f"Could not reach ZIMRA fiscal server: {exc.reason}",
        ) from exc


def call_device_api(
    device_id: str,
    action: str,
    *,
    method: str = "POST",
    payload: dict | None = None,
) -> dict:
    url = build_device_action_url(device_id, action)
    try:
        return _request_device(
            url,
            method=method,
            device_id=device_id,
            payload=payload,
            error_label=action.replace("_", " "),
        )
    except ZimraSubmissionError as exc:
        if method.upper() != "GET" or exc.status_code not in (404, 405):
            raise
        return _request_device(
            url,
            method="POST",
            device_id=device_id,
            payload=payload if payload is not None else {},
            error_label=action.replace("_", " "),
        )


def call_device_api_with_fallbacks(
    device_id: str,
    actions: list[str],
    *,
    method: str = "POST",
    payload: dict | None = None,
) -> dict:
    last_error = None
    for action in actions:
        if not action:
            continue
        try:
            return call_device_api(
                device_id,
                action,
                method=method,
                payload=payload,
            )
        except ZimraSubmissionError as exc:
            last_error = exc
            if exc.status_code in (404, 405):
                continue
            raise
    if last_error:
        raise last_error
    raise ZimraConfigurationError("No fiscal device action configured.")


def submit_receipt_payload(payload: dict, *, device_id: str) -> dict:
    return call_device_api(
        device_id,
        "submit_receipt",
        method="POST",
        payload=payload,
    )
