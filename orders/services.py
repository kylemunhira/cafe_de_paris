from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import MenuAddon

from .models import (
    BranchReceiptSequence,
    KitchenStatus,
    Order,
    OrderItem,
    OrderItemAddon,
    OrderStatus,
    OrderType,
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
