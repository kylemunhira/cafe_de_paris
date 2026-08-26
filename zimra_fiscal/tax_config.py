"""Resolve ZIMRA tax code / ID settings for the active environment."""

from decimal import Decimal

from django.conf import settings

from .constants import ZIMRA_TAX_PROFILES


def get_zimra_env() -> str:
    env = (getattr(settings, "ZIMRA_ENV", "test") or "test").strip().lower()
    if env in ("prod", "live"):
        return "production"
    if env not in ZIMRA_TAX_PROFILES:
        return "test"
    return env


def get_zimra_tax_config() -> dict:
    """Return active ZIMRA tax mapping (codes, IDs, percents).

    Profile is selected by ZIMRA_ENV (test|production). Individual settings
    can override any field.
    """
    profile = dict(ZIMRA_TAX_PROFILES[get_zimra_env()])

    overrides = {
        "standard_tax_percent": getattr(settings, "ZIMRA_STANDARD_TAX_PERCENT", None),
        "standard_tax_code": getattr(settings, "ZIMRA_STANDARD_TAX_CODE", None),
        "standard_tax_id": getattr(settings, "ZIMRA_STANDARD_TAX_ID", None),
        "zero_rated_tax_percent": getattr(settings, "ZIMRA_ZERO_RATED_TAX_PERCENT", None),
        "zero_rated_tax_code": getattr(settings, "ZIMRA_ZERO_RATED_TAX_CODE", None),
        "zero_rated_tax_id": getattr(settings, "ZIMRA_ZERO_RATED_TAX_ID", None),
    }
    for key, value in overrides.items():
        if value is None or value == "":
            continue
        if key.endswith("_id"):
            profile[key] = int(value)
        elif key.endswith("_percent"):
            profile[key] = str(value)
        else:
            profile[key] = str(value).strip()

    profile["standard_tax_percent"] = Decimal(str(profile["standard_tax_percent"]))
    profile["zero_rated_tax_percent"] = Decimal(str(profile["zero_rated_tax_percent"]))
    profile["env"] = get_zimra_env()
    return profile
