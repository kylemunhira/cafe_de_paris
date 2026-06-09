from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from zimra_fiscal.exceptions import ZimraConfigurationError, ZimraSubmissionError
from zimra_fiscal.services import create_fiscal_receipt_for_payment

from catalog.models import ProductCategory
from catalog.serializers import ProductCategorySerializer, ProductSerializer
from orders.models import Order, OrderItem, OrderStatus
from orders.services import ReceiptNumberError, allocate_receipt_number
from payments.serializers import CurrencySerializer

from .models import SyncedClientOrder


def get_branch_catalog_payload(branch):
    """Products and categories a cashier POS needs for the assigned branch."""
    products = (
        ProductSerializer.Meta.model.objects.filter(is_active=True)
        .exclude(category__name="Ingredients")
        .select_related("category")
        .order_by("name")
    )
    category_ids = products.values_list("category_id", flat=True).distinct()
    categories = ProductCategory.objects.filter(id__in=category_ids).order_by("name")

    return {
        "categories": ProductCategorySerializer(categories, many=True).data,
        "products": ProductSerializer(products, many=True).data,
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


def _create_order(branch, validated_data):
    items_data = validated_data["items"]
    order = Order.objects.create(
        branch=branch,
        order_type=validated_data["order_type"],
        table_number=validated_data.get("table_number", ""),
    )
    for item_data in items_data:
        product = item_data["product"]
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=item_data["quantity"],
            price=product.selling_price,
        )
    order.recalculate_total()
    return order


def _pay_order(order, payment_data):
    currency = payment_data["payment_currency"]
    rate = currency.get_current_rate()
    if rate is None:
        raise ValueError(
            f'No exchange rate configured for "{currency.name}". '
            "Add a rate under Payment & Rates → Rates."
        )

    receipt_number = allocate_receipt_number(order.branch)
    order.payment_currency = currency
    order.exchange_rate = rate
    order.amount_paid = currency.convert_from_base(order.total_amount)
    order.status = OrderStatus.PAID
    order.receipt_number = receipt_number
    order.save(
        update_fields=[
            "payment_currency",
            "exchange_rate",
            "amount_paid",
            "status",
            "receipt_number",
        ]
    )

    fiscal_receipt = None
    if order.branch.fiscalization_enabled:
        fiscal_receipt = create_fiscal_receipt_for_payment(order)

    return fiscal_receipt


@transaction.atomic
def import_client_order(branch, validated_data):
    """
    Create (or return existing) central order from a desktop payload.
    Raises ValueError for business rule failures, Zimra errors for fiscal failures.
    """
    client_id = validated_data["client_id"]
    existing = _existing_synced_order(client_id)
    if existing:
        return existing, True, None

    order = _create_order(branch, validated_data)

    fiscal_receipt = None
    payment = validated_data.get("payment")
    if payment:
        try:
            fiscal_receipt = _pay_order(order, payment)
        except (ZimraConfigurationError, ZimraSubmissionError):
            raise
        except ReceiptNumberError as exc:
            raise ValueError(str(exc)) from exc

    SyncedClientOrder.objects.create(client_id=client_id, order=order)
    return order, False, fiscal_receipt
