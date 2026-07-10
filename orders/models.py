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


class FiscalApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending fiscal approval"
    APPROVED = "approved", "Fiscal receipt issued"
    FAILED = "failed", "Fiscal submission failed"


class KitchenStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PREPARING = "preparing", "Preparing"
    READY = "ready", "Ready"


class OrderType(models.TextChoices):
    DINE_IN = "dine_in", "Dine In"
    TAKEAWAY = "takeaway", "Takeaway"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    BANK = "bank", "Bank"
    ECOCASH = "ecocash", "EcoCash"
    ACCOUNT = "account", "Customer account"
    MULTI = "multi", "Split payment"


class TenderMethod(models.TextChoices):
    """Tender types that can appear on a split (non-account) payment."""

    CASH = "cash", "Cash"
    BANK = "bank", "Bank"
    ECOCASH = "ecocash", "EcoCash"


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
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        blank=True,
        default="",
        help_text="How the order was paid (cash, bank, EcoCash, account, or split).",
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
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_created",
        help_text="POS cashier who placed the order.",
    )
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_paid",
        help_text="POS cashier who collected payment.",
    )
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the order was cancelled (unpaid) or voided (paid).",
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_cancelled",
        help_text="Staff who cancelled or voided the order.",
    )
    fiscal_approval_status = models.CharField(
        max_length=20,
        choices=FiscalApprovalStatus.choices,
        blank=True,
        default="",
        help_text="Fiscal branches: proforma pending approval until sent to ZIMRA.",
    )
    fiscal_approved_at = models.DateTimeField(null=True, blank=True)
    fiscal_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_fiscal_approved",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk} - {self.branch}"

    def recalculate_total(self):
        from orders.tax import line_amount

        total = Decimal("0")
        for item in self.items.prefetch_related("addons"):
            total += line_amount(item.quantity, item.price)
            for addon in item.addons.all():
                total += line_amount(item.quantity, addon.price)
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


class OrderPayment(models.Model):
    """One currency tender line on a paid order."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    method = models.CharField(
        max_length=20,
        choices=TenderMethod.choices,
        default=TenderMethod.CASH,
        help_text="Inferred from the payment currency name when possible.",
    )
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="order_payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "currency"],
                name="orders_orderpayment_unique_order_currency",
            ),
        ]

    def __str__(self):
        return f"{self.currency} {self.amount} on order #{self.order_id}"


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
    notes = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    @property
    def line_total(self):
        from orders.tax import line_amount

        base = line_amount(self.quantity, self.price)
        addon_total = sum(
            line_amount(self.quantity, addon.price) for addon in self.addons.all()
        )
        return base + addon_total

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.order.recalculate_total()

    def delete(self, *args, **kwargs):
        order = self.order
        super().delete(*args, **kwargs)
        order.recalculate_total()


class OrderItemAddon(models.Model):
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="addons",
    )
    menu_addon = models.ForeignKey(
        "catalog.MenuAddon",
        on_delete=models.PROTECT,
        related_name="order_item_addons",
    )
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.order_item.order.recalculate_total()

    def delete(self, *args, **kwargs):
        order = self.order_item.order
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
    supplier = models.ForeignKey(
        "purchasing.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )
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


class DayEndClose(models.Model):
    """Persisted POS day-end cash-up (variance + activity snapshot)."""

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="day_end_closes",
    )
    report_date = models.DateField(
        help_text="Business day this cash-up covers.",
    )
    closed_at = models.DateTimeField(auto_now=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="day_end_closes",
    )
    notes = models.CharField(max_length=255, blank=True, default="")
    order_count = models.PositiveIntegerField(default=0)
    gross_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expenses_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    variance_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    has_counted_entries = models.BooleanField(default=False)
    activity_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Frozen day-end report payload at close time.",
    )

    class Meta:
        ordering = ["-report_date", "-closed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("branch", "report_date"),
                name="orders_dayendclose_unique_branch_date",
            ),
        ]

    def __str__(self):
        return f"Day end {self.report_date} — {self.branch}"


class DayEndCashLine(models.Model):
    """Per-currency cash-up line for a saved day-end close."""

    day_end = models.ForeignKey(
        DayEndClose,
        on_delete=models.CASCADE,
        related_name="cash_lines",
    )
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="day_end_cash_lines",
    )
    sales_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposits_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expenses_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_expected_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    counted_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    variance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["currency__name"]
        constraints = [
            models.UniqueConstraint(
                fields=("day_end", "currency"),
                name="orders_dayendcashline_unique_day_currency",
            ),
        ]

    def __str__(self):
        return f"{self.day_end} — {self.currency}"
