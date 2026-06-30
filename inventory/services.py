from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from django.db.models import Q

from catalog.constants import INGREDIENTS_CATEGORY
from catalog.models import Product

from .models import (
    BranchInventory,
    DeliveryNote,
    DeliveryNoteLine,
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


def set_inventory_quantity(branch, product, quantity: Decimal) -> BranchInventory:
    if quantity < 0:
        raise ValueError("Quantity cannot be negative.")
    with transaction.atomic():
        inventory, _ = BranchInventory.objects.select_for_update().get_or_create(
            branch=branch,
            product=product,
            defaults={"quantity": Decimal("0")},
        )
        inventory.quantity = quantity
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


def _delivery_note_lines(note: DeliveryNote) -> list:
    return list(
        DeliveryNoteLine.objects.filter(delivery_note_id=note.pk).select_related(
            "product"
        )
    )


def _is_bakery_to_stores_delivery(note: DeliveryNote) -> bool:
    from branches.models import BranchType

    return (
        note.from_branch.branch_type == BranchType.BAKERY
        and note.to_branch.branch_type == BranchType.STORES
    )


def approve_delivery_note(note: DeliveryNote) -> DeliveryNote:
    if note.status != StockTransferStatus.REQUESTED:
        raise InvalidDeliveryNoteStateError(
            note, StockTransferStatus.REQUESTED, "approve"
        )
    if _is_bakery_to_stores_delivery(note):
        with transaction.atomic():
            note = DeliveryNote.objects.select_for_update().select_related(
                "from_branch", "to_branch"
            ).get(pk=note.pk)
            if note.status != StockTransferStatus.REQUESTED:
                raise InvalidDeliveryNoteStateError(
                    note, StockTransferStatus.REQUESTED, "approve"
                )
            lines = _delivery_note_lines(note)
            if not lines:
                raise InvalidDeliveryNoteStateError(
                    note, "at least one product line", "approve"
                )
            for line in lines:
                adjust_inventory(
                    note.from_branch,
                    line.product,
                    -line.quantity,
                )
                adjust_inventory(
                    note.to_branch,
                    line.product,
                    line.quantity,
                )
            note.status = StockTransferStatus.DELIVERED
            note.save(update_fields=["status"])
        return note
    note.status = StockTransferStatus.APPROVED
    note.save(update_fields=["status"])
    return note


def dispatch_delivery_note(note: DeliveryNote) -> DeliveryNote:
    if note.status != StockTransferStatus.APPROVED:
        raise InvalidDeliveryNoteStateError(
            note, StockTransferStatus.APPROVED, "dispatch"
        )
    with transaction.atomic():
        note = DeliveryNote.objects.select_for_update().select_related(
            "from_branch", "to_branch"
        ).get(pk=note.pk)
        if note.status != StockTransferStatus.APPROVED:
            raise InvalidDeliveryNoteStateError(
                note, StockTransferStatus.APPROVED, "dispatch"
            )
        lines = _delivery_note_lines(note)
        if not lines:
            raise InvalidDeliveryNoteStateError(
                note, "at least one product line", "dispatch"
            )
        for line in lines:
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
        note = DeliveryNote.objects.select_for_update().select_related(
            "from_branch", "to_branch"
        ).get(pk=note.pk)
        if note.status != StockTransferStatus.DISPATCHED:
            raise InvalidDeliveryNoteStateError(
                note, StockTransferStatus.DISPATCHED, "deliver"
            )
        lines = _delivery_note_lines(note)
        if not lines:
            raise InvalidDeliveryNoteStateError(
                note, "at least one product line", "deliver"
            )
        for line in lines:
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


class DayEndStockTakeRequiredError(Exception):
    def __init__(self, branch, count_date, *, draft_in_progress=False):
        self.branch = branch
        self.count_date = count_date
        self.draft_in_progress = draft_in_progress
        super().__init__(day_end_stock_take_message(
            branch,
            count_date,
            completed=False,
            draft_in_progress=draft_in_progress,
        ))


def products_for_stock_take(stock_take_type: str):
    """Ingredients only — POS products are made per order, not held as branch stock."""
    queryset = Product.objects.filter(is_active=True).select_related("category")
    if stock_take_type == StockTakeType.MONTHLY:
        queryset = queryset.filter(
            Q(category__name=INGREDIENTS_CATEGORY) | Q(category__is_asset=True)
        )
    else:
        queryset = queryset.filter(category__name=INGREDIENTS_CATEGORY)
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


def daily_stock_take_completed(branch, count_date: date | str | None = None) -> bool:
    if count_date is None:
        count_date = timezone.localdate()
    elif isinstance(count_date, str):
        count_date = date.fromisoformat(count_date)
    return _completed_stock_take_exists(branch, StockTakeType.DAILY, count_date)


def daily_stock_take_day_end_status(branch, count_date: date | str | None = None) -> dict:
    if count_date is None:
        count_date = timezone.localdate()
    elif isinstance(count_date, str):
        count_date = date.fromisoformat(count_date)

    normalized = _normalize_count_date(StockTakeType.DAILY, count_date)
    stock_takes = StockTake.objects.filter(
        branch=branch,
        stock_take_type=StockTakeType.DAILY,
        count_date=normalized,
    )
    return {
        "completed": stock_takes.filter(status=StockTakeStatus.COMPLETED).exists(),
        "draft_in_progress": stock_takes.filter(status=StockTakeStatus.DRAFT).exists(),
    }


def day_end_stock_take_message(branch, count_date, *, completed, draft_in_progress):
    if completed:
        return ""
    if draft_in_progress:
        return (
            f"Finish and post variances on the daily stock take for {branch.name} "
            f"on {count_date} before running day end. In-progress counts do not count."
        )
    return (
        f"Complete a daily stock take for {branch.name} on {count_date} "
        "and post variances before running day end."
    )


def require_daily_stock_take_for_day_end(branch, count_date: date | str | None = None):
    if count_date is None:
        count_date = timezone.localdate()
    elif isinstance(count_date, str):
        count_date = date.fromisoformat(count_date)
    status = daily_stock_take_day_end_status(branch, count_date)
    if not status["completed"]:
        raise DayEndStockTakeRequiredError(
            branch,
            count_date,
            draft_in_progress=status["draft_in_progress"],
        )


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


def sync_stock_take_lines(stock_take: StockTake) -> StockTake:
    """Drop POS lines from in-progress counts and add any missing ingredients."""
    if stock_take.status != StockTakeStatus.DRAFT:
        return stock_take

    valid_product_ids = set(
        products_for_stock_take(stock_take.stock_take_type).values_list("id", flat=True)
    )
    inventory_map = {
        row.product_id: row.quantity
        for row in BranchInventory.objects.filter(branch=stock_take.branch).only(
            "product_id", "quantity"
        )
    }

    with transaction.atomic():
        lines = list(
            stock_take.lines.select_for_update().select_related("product")
        )
        existing_product_ids = {line.product_id for line in lines}

        invalid_line_ids = [
            line.id for line in lines if line.product_id not in valid_product_ids
        ]
        if invalid_line_ids:
            StockTakeLine.objects.filter(id__in=invalid_line_ids).delete()

        missing_product_ids = valid_product_ids - existing_product_ids
        if missing_product_ids:
            products = Product.objects.filter(id__in=missing_product_ids)
            StockTakeLine.objects.bulk_create(
                [
                    StockTakeLine(
                        stock_take=stock_take,
                        product=product,
                        system_quantity=inventory_map.get(product.id, Decimal("0")),
                    )
                    for product in products
                ]
            )

        for line in stock_take.lines.select_for_update():
            if line.product_id not in valid_product_ids:
                continue
            system_quantity = inventory_map.get(line.product_id, Decimal("0"))
            if line.system_quantity != system_quantity:
                line.system_quantity = system_quantity
                line.save(update_fields=["system_quantity"])

    return stock_take


def update_stock_take_lines(stock_take: StockTake, lines_data: list) -> StockTake:
    if stock_take.status != StockTakeStatus.DRAFT:
        raise InvalidStockTakeStateError(
            stock_take, StockTakeStatus.DRAFT, "update lines"
        )

    with transaction.atomic():
        line_map = {
            line.id: line
            for line in stock_take.lines.select_for_update().select_related("product")
        }
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
        products_to_update = []
        for line in lines:
            set_inventory_quantity(
                stock_take.branch,
                line.product,
                line.counted_quantity,
            )
            line.product.remaining_qty = line.counted_quantity
            products_to_update.append(line.product)
        if products_to_update:
            Product.objects.bulk_update(products_to_update, ["remaining_qty"])
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
