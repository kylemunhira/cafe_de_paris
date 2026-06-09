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


def build_submit_url(device_id: str) -> str:
    base_url = getattr(settings, "ZIMRA_FISCAL_BASE_URL", "").rstrip("/")
    if not base_url:
        raise ZimraConfigurationError("ZIMRA_FISCAL_BASE_URL is not configured.")
    return f"{base_url}/api/submit_receipt/{device_id}"


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


def submit_receipt_payload(payload: dict, *, device_id: str) -> dict:
    url = build_submit_url(device_id)
    body = json.dumps(payload).encode("utf-8")
    logger.info("ZIMRA POST %s (device %s)", url, device_id)
    _log_json("request payload", payload)
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
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
            f"ZIMRA rejected the receipt (HTTP {exc.code}).",
            status_code=exc.code,
            response_body=parsed,
        ) from exc
    except URLError as exc:
        logger.error("ZIMRA connection failed: %s", exc.reason)
        raise ZimraSubmissionError(
            f"Could not reach ZIMRA fiscal server: {exc.reason}",
        ) from exc
