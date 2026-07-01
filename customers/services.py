from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from payments.models import Currency

from orders.models import FiscalApprovalStatus, Order, OrderStatus, PaymentMethod
from orders.services import ReceiptNumberError, allocate_receipt_number

from inventory.services import InsufficientOrderMaterialsError, consume_order_recipe_materials

from .models import Customer, CustomerAccountTransaction, CustomerAccountTransactionType


class CustomerAccountError(Exception):
    pass


class InsufficientAccountBalance(CustomerAccountError):
    pass


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


@transaction.atomic
def deposit_to_account(
    *,
    customer: Customer,
    branch,
    currency: Currency,
    amount_received: Decimal,
    notes: str = "",
    recorded_by=None,
) -> CustomerAccountTransaction:
    if amount_received <= Decimal("0"):
        raise CustomerAccountError("Deposit amount must be greater than zero.")

    rate = currency.get_current_rate()
    if rate is None:
        raise CustomerAccountError(
            f'No exchange rate configured for "{currency.name}". '
            "Add a rate under Payment & Rates → Rates."
        )

    if currency.is_base:
        credit_amount = _quantize(amount_received)
    else:
        credit_amount = _quantize(amount_received / rate)

    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    new_balance = _quantize(customer.account_balance + credit_amount)
    customer.account_balance = new_balance
    customer.save(update_fields=["account_balance"])

    return CustomerAccountTransaction.objects.create(
        customer=customer,
        branch=branch,
        transaction_type=CustomerAccountTransactionType.DEPOSIT,
        amount=credit_amount,
        balance_after=new_balance,
        currency=currency,
        amount_received=_quantize(amount_received),
        notes=notes.strip(),
        recorded_by=recorded_by,
    )


@transaction.atomic
def pay_order_from_account(*, order: Order, recorded_by=None) -> CustomerAccountTransaction:
    if order.status == OrderStatus.CANCELLED:
        raise CustomerAccountError("Cancelled orders cannot be paid.")
    if order.status == OrderStatus.PAID:
        raise CustomerAccountError("Order is already paid.")
    if not order.customer_id:
        raise CustomerAccountError("Link a customer to this order before paying from account.")

    order = Order.objects.select_for_update().select_related("branch").get(pk=order.pk)
    charge_amount = _quantize(order.total_amount)
    if charge_amount <= Decimal("0"):
        raise CustomerAccountError("Order total must be greater than zero.")

    customer = Customer.objects.select_for_update().get(pk=order.customer_id)
    if customer.account_balance < charge_amount:
        raise InsufficientAccountBalance(
            f"Insufficient account balance. Available: {customer.account_balance}, "
            f"required: {charge_amount}."
        )

    new_balance = _quantize(customer.account_balance - charge_amount)
    customer.account_balance = new_balance
    customer.save(update_fields=["account_balance"])

    try:
        receipt_number = allocate_receipt_number(order.branch)
    except ReceiptNumberError as exc:
        raise CustomerAccountError(str(exc)) from exc

    try:
        consume_order_recipe_materials(order)
    except InsufficientOrderMaterialsError as exc:
        raise CustomerAccountError(str(exc)) from exc

    base_currency = Currency.objects.filter(is_base=True, is_active=True).first()
    if base_currency is None:
        raise CustomerAccountError("No base currency is configured.")

    order.payment_currency = base_currency
    order.exchange_rate = Decimal("1")
    order.amount_paid = charge_amount
    order.payment_method = PaymentMethod.ACCOUNT
    order.status = OrderStatus.PAID
    order.receipt_number = receipt_number
    order.paid_at = timezone.now()
    order.paid_by = recorded_by
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

    return CustomerAccountTransaction.objects.create(
        customer=customer,
        branch=order.branch,
        transaction_type=CustomerAccountTransactionType.PAYMENT,
        amount=-charge_amount,
        balance_after=new_balance,
        order=order,
        notes=f"Order #{order.pk}",
        recorded_by=recorded_by,
    )
