from decimal import Decimal

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import MenuAddon

from .models import (
    BranchReceiptSequence,
    FiscalApprovalStatus,
    KitchenStatus,
    Order,
    OrderItem,
    OrderItemAddon,
    OrderPayment,
    OrderStatus,
    OrderType,
    PaymentMethod,
    TenderMethod,
)


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


def find_open_table_order(*, branch, table_number):
    table_number = (table_number or "").strip()
    if not table_number:
        return None
    return (
        Order.objects.filter(
            branch=branch,
            order_type=OrderType.DINE_IN,
            table_number=table_number,
            status=OrderStatus.OPEN,
        )
        .order_by("-created_at")
        .first()
    )


def add_items_to_order(order, items_data):
    if order.status != OrderStatus.OPEN:
        raise ValidationError("Only open orders can receive new items.")

    kitchen_needs_reset = False
    for item_data in items_data:
        product = item_data["product"]
        addon_ids = item_data.get("addon_ids") or []
        notes = (item_data.get("notes") or "").strip()

        allowed_addon_ids = set(
            MenuAddon.objects.filter(
                is_active=True,
                group__product_links__product=product,
            ).values_list("id", flat=True)
        )
        selected_addons = []
        if addon_ids:
            addons = MenuAddon.objects.filter(
                id__in=addon_ids,
                is_active=True,
            ).select_related("group")
            by_group = {}
            for addon in addons:
                if addon.id not in allowed_addon_ids:
                    raise ValidationError(
                        {
                            "items": (
                                f'Add-on "{addon.name}" is not available for {product.name}.'
                            )
                        }
                    )
                existing = by_group.get(addon.group_id)
                if existing and addon.group.selection_type == "single":
                    raise ValidationError(
                        {
                            "items": (
                                f'Choose one option from "{addon.group.name}" for {product.name}.'
                            )
                        }
                    )
                by_group[addon.group_id] = addon
                selected_addons.append(addon)

        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            quantity=item_data["quantity"],
            price=product.selling_price,
            notes=notes,
        )
        for addon in selected_addons:
            OrderItemAddon.objects.create(
                order_item=order_item,
                menu_addon=addon,
                name=addon.name,
                price=addon.selling_price,
            )
        kitchen_needs_reset = True

    if kitchen_needs_reset and order.kitchen_status != KitchenStatus.PENDING:
        order.kitchen_status = KitchenStatus.PENDING
        order.kitchen_started_at = None
        order.kitchen_ready_at = None
        order.save(
            update_fields=[
                "kitchen_status",
                "kitchen_started_at",
                "kitchen_ready_at",
            ]
        )

    order.recalculate_total()
    return order


def consolidate_table_orders(order):
    table_number = (order.table_number or "").strip()
    if (
        order.status != OrderStatus.OPEN
        or order.order_type != OrderType.DINE_IN
        or not table_number
    ):
        return order

    siblings = list(
        Order.objects.filter(
            branch=order.branch,
            order_type=OrderType.DINE_IN,
            table_number=table_number,
            status=OrderStatus.OPEN,
        )
        .exclude(pk=order.pk)
        .prefetch_related("items")
    )
    if not siblings:
        return order

    for sibling in siblings:
        OrderItem.objects.filter(order=sibling).update(order=order)
        sibling.delete()

    order.recalculate_total()
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


class PaymentValidationError(Exception):
    """Raised when tender payment lines are invalid."""


class OrderCancelError(Exception):
    """Raised when an order cannot be cancelled or voided."""


def cancel_order(order, *, cancelled_by=None):
    """Cancel an unpaid (open) order. No inventory changes."""
    if order.status != OrderStatus.OPEN:
        raise OrderCancelError("Only open orders can be cancelled.")
    order.status = OrderStatus.CANCELLED
    order.cancelled_at = timezone.now()
    order.cancelled_by = cancelled_by
    order.save(update_fields=["status", "cancelled_at", "cancelled_by"])
    return order


def void_order(order, *, voided_by=None):
    """
    Void a paid order that has not been fiscalised.
    Restores recipe materials and refunds account payments.
    """
    from customers.services import CustomerAccountError, refund_order_to_account
    from inventory.services import restore_order_recipe_materials

    if order.status != OrderStatus.PAID:
        raise OrderCancelError("Only paid orders can be voided.")
    if order.fiscal_approval_status == FiscalApprovalStatus.APPROVED:
        raise OrderCancelError("Fiscalised orders cannot be voided.")

    restore_order_recipe_materials(order)

    if order.payment_method == PaymentMethod.ACCOUNT:
        try:
            refund_order_to_account(order=order, recorded_by=voided_by)
        except CustomerAccountError as exc:
            raise OrderCancelError(str(exc)) from exc

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = timezone.now()
    order.cancelled_by = voided_by
    order.save(update_fields=["status", "cancelled_at", "cancelled_by"])
    return order


def infer_tender_method(currency) -> str:
    label = f"{currency.name or ''} {currency.code or ''}".lower()
    if "ecocash" in label or "eco cash" in label:
        return TenderMethod.ECOCASH
    if "bank" in label:
        return TenderMethod.BANK
    return TenderMethod.CASH


def normalize_tender_lines(payment_lines):
    """Validate and return tender lines as [{currency, method, amount, rate}, ...]."""
    if not payment_lines:
        raise PaymentValidationError("At least one payment line is required.")

    seen = set()
    normalized = []
    for line in payment_lines:
        currency = line["currency"]
        if currency.id in seen:
            raise PaymentValidationError(
                "Each payment currency can only appear once on a split payment."
            )
        seen.add(currency.id)
        amount = Decimal(line["amount"]).quantize(Decimal("0.01"))
        if amount <= 0:
            raise PaymentValidationError("Each payment amount must be greater than zero.")
        rate = currency.get_current_rate()
        if rate is None:
            raise PaymentValidationError(
                f'No exchange rate configured for "{currency.name}".'
            )
        method = line.get("method") or infer_tender_method(currency)
        if method not in TenderMethod.values:
            method = TenderMethod.CASH
        normalized.append(
            {
                "currency": currency,
                "method": method,
                "amount": amount,
                "rate": rate,
                "base_amount": currency.convert_to_base(amount),
            }
        )
    return normalized


def validate_tender_total(payment_lines, order_total: Decimal):
    """Ensure tenders cover the bill. Overpayment is allowed (treated as change)."""
    total_base = sum((line["base_amount"] for line in payment_lines), Decimal("0"))
    due = order_total.quantize(Decimal("0.01"))
    if total_base < due:
        raise PaymentValidationError(
            f"Payment lines total {total_base} in base currency but order total is {order_total}."
        )
    return (total_base - due).quantize(Decimal("0.01"))


def apply_tender_change(payment_lines, order_total: Decimal):
    """
    If tendered base exceeds the bill, reduce line amounts so stored payments
    equal the order total. Returns (applied_lines, change_base).
    """
    change_base = validate_tender_total(payment_lines, order_total)
    if change_base == 0:
        return payment_lines, Decimal("0.00")

    remaining_change = change_base
    applied = []
    for line in reversed(payment_lines):
        if remaining_change <= 0:
            applied.append(dict(line))
            continue
        if line["base_amount"] <= remaining_change:
            remaining_change = (remaining_change - line["base_amount"]).quantize(
                Decimal("0.01")
            )
            continue
        new_base = (line["base_amount"] - remaining_change).quantize(Decimal("0.01"))
        currency = line["currency"]
        applied.append(
            {
                **line,
                "base_amount": new_base,
                "amount": currency.convert_from_base(new_base),
            }
        )
        remaining_change = Decimal("0.00")

    applied.reverse()
    if not applied:
        raise PaymentValidationError("Payment lines total less than order total after change.")
    return applied, change_base


def resolve_order_payment_method(payment_lines) -> str:
    if len(payment_lines) == 1:
        return payment_lines[0]["method"]
    return PaymentMethod.MULTI


def save_order_tender_payments(order, payment_lines):
    """Replace tender lines on the order and set rollup payment fields."""
    OrderPayment.objects.filter(order=order).delete()
    for line in payment_lines:
        OrderPayment.objects.create(
            order=order,
            method=line["method"],
            currency=line["currency"],
            amount=line["amount"],
            exchange_rate=line["rate"],
        )

    primary = payment_lines[0]
    if len(payment_lines) == 1:
        order.payment_currency = primary["currency"]
        order.exchange_rate = primary["rate"]
        order.amount_paid = primary["amount"]
    else:
        # Rollup stays in base currency for multi-currency splits.
        from payments.models import Currency

        base = Currency.objects.filter(is_base=True).first()
        order.payment_currency = base or primary["currency"]
        order.exchange_rate = Decimal("1") if base else primary["rate"]
        order.amount_paid = order.total_amount
    order.payment_method = resolve_order_payment_method(payment_lines)


def mark_order_paid_with_tenders(
    order,
    *,
    payment_lines,
    receipt_number,
    paid_by=None,
    paid_at=None,
):
    """Apply tender payment(s), allocate receipt fields, and mark the order paid.

    Returns (order, change_base) where change_base is tendered surplus in base currency.
    """
    lines = normalize_tender_lines(payment_lines)
    applied_lines, change_base = apply_tender_change(lines, order.total_amount)

    if order.branch.fiscalization_enabled:
        if len(lines) > 1:
            raise PaymentValidationError(
                "Split payments are only available on non-fiscal branches."
            )

    save_order_tender_payments(order, applied_lines)
    # Keep amount_paid as the full amount tendered for single-currency change display.
    if len(lines) == 1:
        order.amount_paid = lines[0]["amount"]
    order.status = OrderStatus.PAID
    order.receipt_number = receipt_number
    order.paid_at = paid_at or timezone.now()
    order.paid_by = paid_by
    if order.branch.fiscalization_enabled:
        order.fiscal_approval_status = FiscalApprovalStatus.PENDING
    order.save(
        update_fields=[
            "payment_currency",
            "exchange_rate",
            "amount_paid",
            "payment_method",
            "status",
            "receipt_number",
            "paid_at",
            "paid_by",
            "fiscal_approval_status",
        ]
    )
    return order, change_base
