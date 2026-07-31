from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from catalog.constants import is_ingredient_product
from inventory.services import adjust_inventory

from .models import PurchaseOrder, PurchaseOrderStatus

_PRICE_QUANT = Decimal("0.01")


class InvalidPurchaseOrderStateError(Exception):
    def __init__(self, purchase_order, expected, action):
        self.purchase_order = purchase_order
        self.expected = expected
        self.action = action
        super().__init__(
            f"Purchase order #{purchase_order.pk} must be '{expected}' to {action}, "
            f"currently '{purchase_order.status}'"
        )


def _update_ingredient_price_from_line(line) -> None:
    """Copy purchase unit cost onto the ingredient product cost (selling_price)."""
    if line.unit_cost is None or line.unit_cost <= 0:
        return
    product = line.product
    if not is_ingredient_product(product):
        return
    new_price = Decimal(line.unit_cost).quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
    if product.selling_price == new_price:
        return
    product.selling_price = new_price
    product.save(update_fields=["selling_price"])


def apply_purchase_order_inventory(purchase_order: PurchaseOrder) -> None:
    from inventory.models import StockMovementReason

    for line in purchase_order.lines.select_related("product", "product__category"):
        adjust_inventory(
            purchase_order.branch,
            line.product,
            line.quantity,
            reason=StockMovementReason.PURCHASE,
            reference_type="purchase_order",
            reference_id=purchase_order.pk,
            user=purchase_order.created_by,
        )
        _update_ingredient_price_from_line(line)


def submit_purchase_order(purchase_order: PurchaseOrder) -> PurchaseOrder:
    if purchase_order.status != PurchaseOrderStatus.DRAFT:
        raise InvalidPurchaseOrderStateError(
            purchase_order, PurchaseOrderStatus.DRAFT, "submit"
        )
    if not purchase_order.lines.exists():
        raise InvalidPurchaseOrderStateError(
            purchase_order, "at least one line item", "submit"
        )
    purchase_order.status = PurchaseOrderStatus.SUBMITTED
    purchase_order.submitted_at = timezone.now()
    purchase_order.save(update_fields=["status", "submitted_at"])
    return purchase_order


def approve_purchase_order(purchase_order: PurchaseOrder) -> PurchaseOrder:
    if purchase_order.status != PurchaseOrderStatus.SUBMITTED:
        raise InvalidPurchaseOrderStateError(
            purchase_order, PurchaseOrderStatus.SUBMITTED, "approve"
        )
    purchase_order.status = PurchaseOrderStatus.APPROVED
    purchase_order.approved_at = timezone.now()
    purchase_order.save(update_fields=["status", "approved_at"])
    return purchase_order


def receive_purchase_order(purchase_order: PurchaseOrder) -> PurchaseOrder:
    if purchase_order.status != PurchaseOrderStatus.APPROVED:
        raise InvalidPurchaseOrderStateError(
            purchase_order, PurchaseOrderStatus.APPROVED, "receive"
        )
    with transaction.atomic():
        apply_purchase_order_inventory(purchase_order)
        purchase_order.status = PurchaseOrderStatus.RECEIVED
        purchase_order.received_at = timezone.now()
        purchase_order.save(update_fields=["status", "received_at"])
    return purchase_order


def cancel_purchase_order(purchase_order: PurchaseOrder) -> PurchaseOrder:
    if purchase_order.status not in (
        PurchaseOrderStatus.DRAFT,
        PurchaseOrderStatus.SUBMITTED,
        PurchaseOrderStatus.APPROVED,
    ):
        raise InvalidPurchaseOrderStateError(
            purchase_order,
            f"{PurchaseOrderStatus.DRAFT}, {PurchaseOrderStatus.SUBMITTED}, "
            f"or {PurchaseOrderStatus.APPROVED}",
            "cancel",
        )
    purchase_order.status = PurchaseOrderStatus.CANCELLED
    purchase_order.save(update_fields=["status"])
    return purchase_order
