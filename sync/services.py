from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from zimra_fiscal.exceptions import ZimraConfigurationError, ZimraSubmissionError

from branches.dining_tables import ensure_default_dining_tables
from branches.models import DiningTable
from branches.serializers import DiningTableSerializer
from catalog.pos_catalog import pos_catalog_categories, pos_catalog_products
from catalog.serializers import ProductCategorySerializer, ProductSerializer
from inventory.services import InsufficientOrderMaterialsError, consume_order_recipe_materials
from orders.models import Order, OrderStatus, OrderType
from orders.services import (
    PaymentValidationError,
    ReceiptNumberError,
    add_items_to_order,
    allocate_receipt_number,
    consolidate_table_orders,
    find_open_table_order,
    mark_order_paid_with_tenders,
)
from payments.serializers import CurrencySerializer

from .models import SyncedClientOrder


def get_branch_catalog_payload(branch):
    """Products and categories a cashier POS needs for the assigned branch."""
    ensure_default_dining_tables(branch)
    products = pos_catalog_products()
    categories = pos_catalog_categories()

    return {
        "categories": ProductCategorySerializer(categories, many=True).data,
        "products": ProductSerializer(products, many=True).data,
        "dining_tables": DiningTableSerializer(
            DiningTable.objects.filter(branch=branch, is_active=True),
            many=True,
        ).data,
    }


def get_currencies_payload():
    from payments.models import Currency

    currencies = Currency.objects.filter(is_active=True).order_by("name")
    return CurrencySerializer(currencies, many=True).data


def _existing_synced_order(client_id):
    record = (
        SyncedClientOrder.objects.select_related("order")
        .filter(client_id=client_id)
        .first()
    )
    return record.order if record else None


def _normalize_item_quantity(quantity):
    return Decimal(str(quantity)).quantize(Decimal("0.01"))


def _order_item_signature(*, product_id, quantity, notes="", addon_ids=()):
    return (
        product_id,
        _normalize_item_quantity(quantity),
        (notes or "").strip(),
        tuple(sorted(addon_ids or ())),
    )


def _signature_from_order_item(item):
    addon_ids = [addon.menu_addon_id for addon in item.addons.all()]
    return _order_item_signature(
        product_id=item.product_id,
        quantity=item.quantity,
        notes=item.notes,
        addon_ids=addon_ids,
    )


def _signature_from_items_data(item_data):
    return _order_item_signature(
        product_id=item_data["product"].id,
        quantity=item_data["quantity"],
        notes=item_data.get("notes") or "",
        addon_ids=item_data.get("addon_ids") or (),
    )


def _reconcile_open_order_items(order, items_data):
    """
    Add desktop payload lines that are not yet on the server order.
    Desktop sends the full joined order each sync, so diff before appending.
    """
    if order.status != OrderStatus.OPEN or not items_data:
        return order

    on_server = Counter()
    for item in order.items.prefetch_related("addons"):
        on_server[_signature_from_order_item(item)] += 1

    wanted = Counter(_signature_from_items_data(data) for data in items_data)
    to_add = wanted - on_server
    if not to_add:
        return order

    new_items = []
    for signature, count in to_add.items():
        template = next(
            data for data in items_data if _signature_from_items_data(data) == signature
        )
        new_items.extend([template] * count)

    if new_items:
        add_items_to_order(order, new_items)
    return order


def _prepare_existing_order_for_sync(order, items_data):
    if order.status != OrderStatus.OPEN:
        return order
    order = consolidate_table_orders(order)
    return _reconcile_open_order_items(order, items_data)


def _create_order(branch, validated_data, user=None):
    items_data = validated_data["items"]
    table_number = (validated_data.get("table_number") or "").strip()
    order_type = validated_data.get("order_type")

    existing = None
    if order_type == OrderType.DINE_IN and table_number:
        existing = find_open_table_order(branch=branch, table_number=table_number)

    if existing:
        add_items_to_order(existing, items_data)
        return existing

    order = Order.objects.create(
        branch=branch,
        order_type=validated_data["order_type"],
        table_number=validated_data.get("table_number", ""),
        created_by=user,
    )
    add_items_to_order(order, items_data)
    return order


def _pay_order(order, payment_data, user=None):
    receipt_number = allocate_receipt_number(order.branch)
    paid_at = payment_data.get("paid_at") or timezone.now()
    try:
        consume_order_recipe_materials(order)
    except InsufficientOrderMaterialsError as exc:
        raise ValueError(str(exc)) from exc

    payment_lines = payment_data.get("payments")
    if payment_lines:
        lines = [
            {
                "currency": line["currency"],
                "amount": line["amount"],
                "method": line.get("method"),
            }
            for line in payment_lines
        ]
    else:
        currency = payment_data["payment_currency"]
        if currency.get_current_rate() is None:
            raise ValueError(
                f'No exchange rate configured for "{currency.name}". '
                "Add a rate under Payment & Rates → Rates."
            )
        lines = [
            {
                "currency": currency,
                "amount": currency.convert_from_base(order.total_amount),
                "method": "cash",
            }
        ]

    try:
        mark_order_paid_with_tenders(
            order,
            payment_lines=lines,
            receipt_number=receipt_number,
            paid_by=user,
            paid_at=paid_at,
        )
    except PaymentValidationError as exc:
        raise ValueError(str(exc)) from exc

    return None


def _apply_payment_if_needed(order, payment, user=None):
    if not payment or order.status == OrderStatus.PAID:
        return None
    try:
        return _pay_order(order, payment, user=user)
    except (ZimraConfigurationError, ZimraSubmissionError):
        raise
    except ReceiptNumberError as exc:
        raise ValueError(str(exc)) from exc


@transaction.atomic
def import_client_order(branch, validated_data, user=None):
    """
    Create (or return existing) central order from a desktop payload.
    Raises ValueError for business rule failures, Zimra errors for fiscal failures.
    """
    client_id = validated_data["client_id"]
    payment = validated_data.get("payment")
    existing = _existing_synced_order(client_id)
    if existing:
        existing = _prepare_existing_order_for_sync(existing, validated_data["items"])
        fiscal_receipt = _apply_payment_if_needed(existing, payment, user=user)
        return existing, True, fiscal_receipt

    order = _create_order(branch, validated_data, user=user)
    fiscal_receipt = _apply_payment_if_needed(order, payment, user=user)

    SyncedClientOrder.objects.create(client_id=client_id, order=order)
    return order, False, fiscal_receipt
