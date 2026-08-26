RECEIPT_TYPE = "FiscalInvoice"
RECEIPT_PRINT_FORM = "Receipt48"
RECEIPT_LINE_TYPE = "Sale"
DEFAULT_MONEY_TYPE_CODE = "Cash"

# Fallback defaults (test profile). Prefer get_zimra_tax_config() / Django settings.
ZERO_RATED_TAX_CODE = "B"
ZERO_RATED_TAX_ID = 2
STANDARD_TAX_CODE = "E"
DEFAULT_STANDARD_TAX_ID = 517

# Named profiles: only the standard tax ID differs between test and production.
ZIMRA_TAX_PROFILES = {
    "test": {
        "standard_tax_percent": "15.5",
        "standard_tax_code": "E",
        "standard_tax_id": 517,
        "zero_rated_tax_percent": "0",
        "zero_rated_tax_code": "B",
        "zero_rated_tax_id": 2,
    },
    "production": {
        "standard_tax_percent": "15.5",
        "standard_tax_code": "E",
        "standard_tax_id": 515,
        "zero_rated_tax_percent": "0",
        "zero_rated_tax_code": "B",
        "zero_rated_tax_id": 2,
    },
}
