from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from catalog.models import Product

from .models import (
    BranchInventory,
    DeliveryNote,
    StockTake,
    StockTakeLine,
    StockTakeStatus,
    StockTakeType,
    StockTransfer,
    StockTransferStatus,
)


class InsufficientStockError(Exception):
    def __init__(self, branch, product, available, requested):
        self.branch = branch
        self.product = product
        self.available = available
        self.requested = requested
        super().__init__(
            f"Insufficient stock for {product} at {branch}: "
            f"available {available}, requested {requested}"
        )


class InvalidTransferStateError(Exception):
    def __init__(self, transfer, expected, action):
        self.transfer = transfer
        self.expected = expected
        self.action = action
        super().__init__(
            f"Transfer #{transfer.pk} must be '{expected}' to {action}, "
            f"currently '{transfer.status}'"
        )


class InvalidDeliveryNoteStateError(Exception):
    def __init__(self, note, expected, action):
        self.note = note
        self.expected = expected
        self.action = action
        super().__init__(
            f"Delivery note #{note.pk} must be '{expected}' to {action}, "
            f"currently '{note.status}'"
        )


def adjust_inventory(branch, product, delta: Decimal) -> BranchInventory:
    with transaction.atomic():
        inventory, _ = BranchInventory.objects.select_for_update().get_or_create(
            branch=branch,
            product=product,
            defaults={"quantity": Decimal("0")},
        )
        new_quantity = inventory.quantity + delta
        if new_quantity < 0:
            raise InsufficientStockError(
                branch, product, inventory.quantity, abs(delta)
            )
        inventory.quantity = new_quantity
        inventory.save(update_fields=["quantity", "last_updated"])
        return inventory


def approve_transfer(transfer: StockTransfer) -> StockTransfer:
    if transfer.status != StockTransferStatus.REQUESTED:
        raise InvalidTransferStateError(
            transfer, StockTransferStatus.REQUESTED, "approve"
        )
    transfer.status = StockTransferStatus.APPROVED
    transfer.save(update_fields=["status"])
    return transfer


def dispatch_transfer(transfer: StockTransfer) -> StockTransfer:
    if transfer.status != StockTransferStatus.APPROVED:
        raise InvalidTransferStateError(
            transfer, StockTransferStatus.APPROVED, "dispatch"
        )
    with transaction.atomic():
        adjust_inventory(
            transfer.from_branch,
            transfer.product,
            -transfer.quantity,
        )
        transfer.status = StockTransferStatus.DISPATCHED
        transfer.save(update_fields=["status"])
    return transfer


def deliver_transfer(transfer: StockTransfer) -> StockTransfer:
    if transfer.status != StockTransferStatus.DISPATCHED:
        raise InvalidTransferStateError(
            transfer, StockTransferStatus.DISPATCHED, "deliver"
        )
    with transaction.atomic():
        adjust_inventory(
            transfer.to_branch,
            transfer.product,
            transfer.quantity,
        )
        transfer.status = StockTransferStatus.DELIVERED
        transfer.save(update_fields=["status"])
    return transfer


def cancel_transfer(transfer: StockTransfer) -> StockTransfer:
    if transfer.status not in (
        StockTransferStatus.REQUESTED,
        StockTransferStatus.APPROVED,
    ):
        raise InvalidTransferStateError(
            transfer,
            f"{StockTransferStatus.REQUESTED} or {StockTransferStatus.APPROVED}",
            "cancel",
        )
    transfer.status = StockTransferStatus.CANCELLED
    transfer.save(update_fields=["status"])
    return transfer


def approve_delivery_note(note: DeliveryNote) -> DeliveryNote:
    if note.status != StockTransferStatus.REQUESTED:
        raise InvalidDeliveryNoteStateError(
            note, StockTransferStatus.REQUESTED, "approve"
        )
    note.status = StockTransferStatus.APPROVED
    note.save(update_fields=["status"])
    return note


def dispatch_delivery_note(note: DeliveryNote) -> DeliveryNote:
    if note.status != StockTransferStatus.APPROVED:
        raise InvalidDeliveryNoteStateError(
            note, StockTransferStatus.APPROVED, "dispatch"
        )
    with transaction.atomic():
        for line in note.lines.select_related("product"):
            adjust_inventory(
                note.from_branch,
                line.product,
                -line.quantity,
            )
        note.status = StockTransferStatus.DISPATCHED
        note.save(update_fields=["status"])
    return note


def deliver_delivery_note(note: DeliveryNote) -> DeliveryNote:
    if note.status != StockTransferStatus.DISPATCHED:
        raise InvalidDeliveryNoteStateError(
            note, StockTransferStatus.DISPATCHED, "deliver"
        )
    with transaction.atomic():
        for line in note.lines.select_related("product"):
            adjust_inventory(
                note.to_branch,
                line.product,
                line.quantity,
            )
        note.status = StockTransferStatus.DELIVERED
        note.save(update_fields=["status"])
    return note


class DuplicateStockTakeError(Exception):
    def __init__(self, branch, stock_take_type, count_date):
        self.branch = branch
        self.stock_take_type = stock_take_type
        self.count_date = count_date
        super().__init__(
            f"A completed {stock_take_type} stock take already exists for "
            f"{branch} on {count_date}."
        )


class InvalidStockTakeStateError(Exception):
    def __init__(self, stock_take, expected, action):
        self.stock_take = stock_take
        self.expected = expected
        self.action = action
        super().__init__(
            f"Stock take #{stock_take.pk} must be '{expected}' to {action}, "
            f"currently '{stock_take.status}'"
        )


class IncompleteStockTakeError(Exception):
    def __init__(self, stock_take, missing_count):
        self.stock_take = stock_take
        self.missing_count = missing_count
        super().__init__(
            f"Stock take #{stock_take.pk} has {missing_count} line(s) "
            "without a counted quantity."
        )


def products_for_stock_take(stock_take_type: str):
    queryset = Product.objects.filter(is_active=True).select_related("category")
    if stock_take_type == StockTakeType.DAILY:
        queryset = queryset.filter(category__is_asset=False)
    return queryset.order_by("category__name", "name")


def _normalize_count_date(stock_take_type: str, count_date: date) -> date:
    if stock_take_type == StockTakeType.MONTHLY:
        return count_date.replace(day=1)
    return count_date


def _completed_stock_take_exists(branch, stock_take_type: str, count_date: date) -> bool:
    count_date = _normalize_count_date(stock_take_type, count_date)
    return StockTake.objects.filter(
        branch=branch,
        stock_take_type=stock_take_type,
        count_date=count_date,
        status=StockTakeStatus.COMPLETED,
    ).exists()


def create_stock_take(branch, stock_take_type: str, count_date: date, created_by=None) -> StockTake:
    count_date = _normalize_count_date(stock_take_type, count_date)
    if _completed_stock_take_exists(branch, stock_take_type, count_date):
        raise DuplicateStockTakeError(branch, stock_take_type, count_date)

    inventory_map = {
        row.product_id: row.quantity
        for row in BranchInventory.objects.filter(branch=branch).only(
            "product_id", "quantity"
        )
    }

    with transaction.atomic():
        stock_take = StockTake.objects.create(
            branch=branch,
            stock_take_type=stock_take_type,
            count_date=count_date,
            created_by=created_by,
        )
        StockTakeLine.objects.bulk_create(
            [
                StockTakeLine(
                    stock_take=stock_take,
                    product=product,
                    system_quantity=inventory_map.get(product.id, Decimal("0")),
                )
                for product in products_for_stock_take(stock_take_type)
            ]
        )
    return stock_take


def update_stock_take_lines(stock_take: StockTake, lines_data: list) -> StockTake:
    if stock_take.status != StockTakeStatus.DRAFT:
        raise InvalidStockTakeStateError(
            stock_take, StockTakeStatus.DRAFT, "update lines"
        )

    line_map = {
        line.id: line
        for line in stock_take.lines.select_for_update().select_related("product")
    }

    with transaction.atomic():
        for entry in lines_data:
            line = line_map.get(entry["id"])
            if line is None:
                continue
            if "counted_quantity" in entry:
                line.counted_quantity = entry["counted_quantity"]
            if "notes" in entry:
                line.notes = entry["notes"] or ""
            line.save(update_fields=["counted_quantity", "notes"])
    return stock_take


def complete_stock_take(stock_take: StockTake) -> StockTake:
    if stock_take.status != StockTakeStatus.DRAFT:
        raise InvalidStockTakeStateError(
            stock_take, StockTakeStatus.DRAFT, "complete"
        )

    lines = list(stock_take.lines.select_related("product"))
    missing = sum(1 for line in lines if line.counted_quantity is None)
    if missing:
        raise IncompleteStockTakeError(stock_take, missing)

    count_date = _normalize_count_date(stock_take.stock_take_type, stock_take.count_date)
    if _completed_stock_take_exists(
        stock_take.branch, stock_take.stock_take_type, count_date
    ):
        raise DuplicateStockTakeError(
            stock_take.branch, stock_take.stock_take_type, count_date
        )

    with transaction.atomic():
        for line in lines:
            variance = line.counted_quantity - line.system_quantity
            if variance != 0:
                adjust_inventory(stock_take.branch, line.product, variance)
        stock_take.status = StockTakeStatus.COMPLETED
        stock_take.completed_at = timezone.now()
        stock_take.save(update_fields=["status", "completed_at"])
    return stock_take


def cancel_stock_take(stock_take: StockTake) -> StockTake:
    if stock_take.status != StockTakeStatus.DRAFT:
        raise InvalidStockTakeStateError(
            stock_take, StockTakeStatus.DRAFT, "cancel"
        )
    stock_take.status = StockTakeStatus.CANCELLED
    stock_take.save(update_fields=["status"])
    return stock_take


def cancel_delivery_note(note: DeliveryNote) -> DeliveryNote:
    if note.status not in (
        StockTransferStatus.REQUESTED,
        StockTransferStatus.APPROVED,
    ):
        raise InvalidDeliveryNoteStateError(
            note,
            f"{StockTransferStatus.REQUESTED} or {StockTransferStatus.APPROVED}",
            "cancel",
        )
    note.status = StockTransferStatus.CANCELLED
    note.save(update_fields=["status"])
    return note


class InvalidDeliveryNotePaymentError(Exception):
    def __init__(self, note, detail):
        self.note = note
        super().__init__(detail)


def mark_delivery_note_paid(note: DeliveryNote, user) -> DeliveryNote:
    from django.utils import timezone

    from .models import TransferInvoicePaymentStatus

    if not note.invoice_number:
        raise InvalidDeliveryNotePaymentError(
            note,
            "Only transfer invoices can be marked as paid.",
        )
    if note.payment_status == TransferInvoicePaymentStatus.PAID:
        raise InvalidDeliveryNotePaymentError(
            note,
            f"Transfer invoice {note.invoice_number} is already paid.",
        )
    note.payment_status = TransferInvoicePaymentStatus.PAID
    note.paid_at = timezone.now()
    note.paid_by = user
    note.save(update_fields=["payment_status", "paid_at", "paid_by"])
    return note


def assign_transfer_invoice_number(note: DeliveryNote) -> DeliveryNote:
    """Assign an invoice number when central stores dispatches to a branch."""
    from branches.models import BranchType

    if note.from_branch.branch_type != BranchType.STORES or note.invoice_number:
        return note
    from_code = (note.from_branch.code or "STR").upper()
    to_code = (note.to_branch.code or "BRN").upper()
    note.invoice_number = f"{from_code}{to_code}{note.pk:05d}"
    note.save(update_fields=["invoice_number"])
    return note
