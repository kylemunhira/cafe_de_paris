from django.db import transaction

from .client import resolve_device_id, submit_receipt_payload
from .exceptions import ZimraConfigurationError, ZimraSubmissionError
from .models import BranchFiscalState, FiscalReceipt, FiscalReceiptStatus
from .constants import DEFAULT_MONEY_TYPE_CODE
from .receipt import build_fiscal_receipt_payload
from .response import apply_zimra_response


def _allocate_fiscal_counters(branch):
    state, _ = BranchFiscalState.objects.select_for_update().get_or_create(
        branch=branch
    )
    state.receipt_counter += 1
    state.receipt_global_no += 1
    state.save(
        update_fields=[
            "receipt_counter",
            "receipt_global_no",
        ]
    )
    return state.receipt_counter, state.receipt_global_no


@transaction.atomic
def create_fiscal_receipt_for_payment(order):
    order = (
        type(order)
        .objects.select_related("branch", "payment_currency")
        .prefetch_related("items__product")
        .get(pk=order.pk)
    )

    if not order.receipt_number:
        raise ZimraConfigurationError(
            "Order must have a receipt number before fiscal submission."
        )

    receipt_counter, receipt_global_no = _allocate_fiscal_counters(order.branch)
    invoice_no = order.receipt_number
    payload = build_fiscal_receipt_payload(
        order,
        receipt_counter=receipt_counter,
        receipt_global_no=receipt_global_no,
        invoice_no=invoice_no,
        money_type_code=DEFAULT_MONEY_TYPE_CODE,
    )
    fiscal_receipt = FiscalReceipt.objects.create(
        order=order,
        branch=order.branch,
        receipt_counter=receipt_counter,
        receipt_global_no=receipt_global_no,
        invoice_no=invoice_no,
        payload=payload,
    )
    submit_fiscal_receipt_to_zimra(fiscal_receipt)
    return fiscal_receipt


def submit_fiscal_receipt_to_zimra(fiscal_receipt: FiscalReceipt) -> FiscalReceipt:
    device_id = resolve_device_id(fiscal_receipt.branch)
    try:
        result = submit_receipt_payload(fiscal_receipt.payload, device_id=device_id)
    except (ZimraConfigurationError, ZimraSubmissionError):
        fiscal_receipt.status = FiscalReceiptStatus.FAILED
        fiscal_receipt.save(update_fields=["status"])
        raise

    return apply_zimra_response(fiscal_receipt, result)
