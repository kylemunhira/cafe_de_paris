from decimal import Decimal

from django.conf import settings
from django.db import models

from branches.models import Branch
from catalog.models import Product
from customers.models import Customer
from payments.models import Currency


class OrderStatus(models.TextChoices):
    OPEN = "open", "Open"
    PAID = "paid", "Paid"
    CANCELLED = "cancelled", "Cancelled"


class KitchenStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PREPARING = "preparing", "Preparing"
    READY = "ready", "Ready"


class OrderType(models.TextChoices):
    DINE_IN = "dine_in", "Dine In"
    TAKEAWAY = "takeaway", "Takeaway"


class Order(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    order_type = models.CharField(
        max_length=20,
        choices=OrderType.choices,
        default=OrderType.TAKEAWAY,
    )
    table_number = models.CharField(max_length=20, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Exchange rate applied at payment (units per 1 base unit).",
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.OPEN,
    )
    kitchen_status = models.CharField(
        max_length=20,
        choices=KitchenStatus.choices,
        default=KitchenStatus.PENDING,
        help_text="Preparation progress for open POS orders.",
    )
    kitchen_started_at = models.DateTimeField(null=True, blank=True)
    kitchen_ready_at = models.DateTimeField(null=True, blank=True)
    receipt_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text="Assigned at payment, e.g. HIG0906267 (code + DDMMYY + daily count).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When payment was collected (used for day-end reports).",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk} - {self.branch}"

    def recalculate_total(self):
        total = self.items.aggregate(
            total=models.Sum(models.F("quantity") * models.F("price"))
        )["total"] or Decimal("0")
        self.total_amount = total
        self.save(update_fields=["total_amount"])


class BranchReceiptSequence(models.Model):
    branch = models.OneToOneField(
        Branch,
        on_delete=models.CASCADE,
        related_name="receipt_sequence",
    )
    sequence_date = models.DateField(null=True, blank=True)
    daily_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "branch receipt sequence"
        verbose_name_plural = "branch receipt sequences"

    def __str__(self):
        return f"Receipt sequence for {self.branch}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    @property
    def line_total(self):
        return self.quantity * self.price

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.order.recalculate_total()

    def delete(self, *args, **kwargs):
        order = self.order
        super().delete(*args, **kwargs)
        order.recalculate_total()


class Expense(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    expense_date = models.DateField(
        help_text="Business day this expense applies to (for day-end reports).",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    description = models.CharField(max_length=200)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.description} — {self.amount} ({self.branch})"
