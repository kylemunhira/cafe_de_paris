from django.utils import timezone

from .models import BranchReceiptSequence, KitchenStatus, OrderStatus


class ReceiptNumberError(Exception):
    pass


class InvalidKitchenStateError(Exception):
    def __init__(self, order, expected, action):
        self.order = order
        self.expected = expected
        self.action = action
        super().__init__(
            f"Order #{order.pk} kitchen status must be '{expected}' to {action}, "
            f"currently '{order.kitchen_status}'"
        )


def start_preparing_order(order):
    if order.status != OrderStatus.OPEN:
        raise InvalidKitchenStateError(order, OrderStatus.OPEN, "start preparing")
    if order.kitchen_status != KitchenStatus.PENDING:
        raise InvalidKitchenStateError(order, KitchenStatus.PENDING, "start preparing")
    order.kitchen_status = KitchenStatus.PREPARING
    order.kitchen_started_at = timezone.now()
    order.save(update_fields=["kitchen_status", "kitchen_started_at"])
    return order


def mark_order_ready(order):
    if order.status != OrderStatus.OPEN:
        raise InvalidKitchenStateError(order, OrderStatus.OPEN, "mark ready")
    if order.kitchen_status != KitchenStatus.PREPARING:
        raise InvalidKitchenStateError(order, KitchenStatus.PREPARING, "mark ready")
    order.kitchen_status = KitchenStatus.READY
    order.kitchen_ready_at = timezone.now()
    order.save(update_fields=["kitchen_status", "kitchen_ready_at"])
    return order


def allocate_receipt_number(branch) -> str:
    code = (branch.code or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ReceiptNumberError(
            f'Branch "{branch.name}" needs a 3-letter receipt code (e.g. HIG, CHU).'
        )

    today = timezone.localdate()
    state, _ = BranchReceiptSequence.objects.select_for_update().get_or_create(
        branch=branch
    )
    if state.sequence_date != today:
        state.sequence_date = today
        state.daily_count = 0
    state.daily_count += 1
    state.save(update_fields=["sequence_date", "daily_count"])

    date_part = today.strftime("%d%m%y")
    return f"{code}{date_part}{state.daily_count}"
