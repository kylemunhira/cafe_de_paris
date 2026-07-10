from decimal import Decimal

from django.conf import settings
from django.db import models

from branches.models import Branch
from payments.models import Currency


class Customer(models.Model):
    """Company-wide customer master data — shared across all branches."""

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    loyalty_points = models.PositiveIntegerField(default=0)
    account_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Prepaid balance in base currency.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.phone or f"Customer #{self.pk}"


class CustomerAccountTransactionType(models.TextChoices):
    DEPOSIT = "deposit", "Deposit"
    PAYMENT = "payment", "Payment"
    REFUND = "refund", "Refund"


class CustomerAccountTransaction(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="account_transactions",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="customer_account_transactions",
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=CustomerAccountTransactionType.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Positive for deposits, negative for payments (base currency).",
    )
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="customer_account_transactions",
        help_text="Cash currency received (deposits only).",
    )
    amount_received = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount received in payment currency (deposits only).",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_transactions",
    )
    notes = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_account_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer} {self.transaction_type} {self.amount}"

    @property
    def balance_before(self):
        return self.balance_after - self.amount

    @property
    def statement_label(self):
        if self.transaction_type == CustomerAccountTransactionType.DEPOSIT:
            return "Payment received"
        if self.transaction_type == CustomerAccountTransactionType.REFUND:
            return "Refund"
        return "Withdrawal"
