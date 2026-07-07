from datetime import date
from decimal import Decimal


def json_safe_day_end_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe_day_end_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe_day_end_value(item) for item in value]
    return value


def serialize_day_end_report(report: dict) -> dict:
    return json_safe_day_end_value(report)


def parse_counted_by_currency(query_params) -> dict:
    counted = {}
    for key, value in query_params.items():
        if not key.startswith("counted_"):
            continue
        try:
            currency_id = int(key.split("counted_", 1)[1])
        except (TypeError, ValueError):
            continue
        counted[currency_id] = value
    return counted
