from django.conf import settings
from django.db import models

from branches.models import Branch
from catalog.models import Product


class BranchInventory(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="inventory_items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="branch_inventory",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("branch", "product")
        verbose_name_plural = "branch inventory"
        ordering = ["branch__name", "product__name"]

    def __str__(self):
        return f"{self.branch} - {self.product}: {self.quantity}"


class StockTransferStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    APPROVED = "approved", "Approved"
    DISPATCHED = "dispatched", "Dispatched"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class TransferInvoicePaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PAID = "paid", "Paid"


class StockTransfer(models.Model):
    from_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="outgoing_transfers",
    )
    to_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_transfers",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=StockTransferStatus.choices,
        default=StockTransferStatus.REQUESTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product} ({self.quantity}) {self.from_branch} -> {self.to_branch}"


class DeliveryNote(models.Model):
    from_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="outgoing_delivery_notes",
    )
    to_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="incoming_delivery_notes",
    )
    invoice_number = models.CharField(
        max_length=32,
        blank=True,
        unique=True,
        null=True,
        help_text="Transfer invoice number for central stores dispatches.",
    )
    status = models.CharField(
        max_length=20,
        choices=StockTransferStatus.choices,
        default=StockTransferStatus.REQUESTED,
    )
    payment_status = models.CharField(
        max_length=10,
        choices=TransferInvoicePaymentStatus.choices,
        default=TransferInvoicePaymentStatus.UNPAID,
        help_text="Payment status for central stores transfer invoices.",
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the receiving branch settled this transfer invoice.",
    )
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfer_invoices_marked_paid",
        help_text="Staff who recorded payment for this transfer invoice.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Delivery note #{self.pk} {self.from_branch} -> {self.to_branch}"

    @property
    def is_transfer_invoice(self):
        return bool(self.invoice_number)

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines.all())

    @property
    def total_amount(self):
        from decimal import Decimal

        return sum(
            (line.unit_price or Decimal("0")) * line.quantity
            for line in self.lines.all()
        )


class DeliveryNoteLine(models.Model):
    delivery_note = models.ForeignKey(
        DeliveryNote,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="delivery_note_lines",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Unit cost on transfer invoices from central stores.",
    )

    class Meta:
        unique_together = ("delivery_note", "product")
        ordering = ["product__name"]

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    @property
    def line_total(self):
        from decimal import Decimal

        if self.unit_price is None:
            return Decimal("0")
        return self.unit_price * self.quantity


class StockTakeType(models.TextChoices):
    DAILY = "daily", "Daily"
    MONTHLY = "monthly", "Monthly"


class StockTakeStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class StockTake(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="stock_takes",
    )
    stock_take_type = models.CharField(
        max_length=10,
        choices=StockTakeType.choices,
    )
    status = models.CharField(
        max_length=12,
        choices=StockTakeStatus.choices,
        default=StockTakeStatus.DRAFT,
    )
    count_date = models.DateField(
        help_text="Calendar date for daily counts; first day of month for monthly counts.",
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_takes_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-count_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "stock_take_type", "count_date"],
                condition=models.Q(status=StockTakeStatus.COMPLETED),
                name="unique_completed_stock_take_per_branch_period",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_stock_take_type_display()} stock take "
            f"#{self.pk} — {self.branch} ({self.count_date})"
        )

    @property
    def line_count(self):
        return self.lines.count()

    @property
    def variance_count(self):
        return sum(1 for line in self.lines.all() if line.variance != 0)


class StockTakeLine(models.Model):
    stock_take = models.ForeignKey(
        StockTake,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_take_lines",
    )
    system_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    counted_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("stock_take", "product")
        ordering = ["product__category__name", "product__name"]

    def __str__(self):
        return f"{self.product} — system {self.system_quantity}"

    @property
    def variance(self):
        if self.counted_quantity is None:
            return None
        return self.counted_quantity - self.system_quantity


class CentralInvoiceStatus(models.TextChoices):
    DISPATCHED = "dispatched", "Dispatched"
    CANCELLED = "cancelled", "Cancelled"


class CentralInvoice(models.Model):
    """Sale or transfer of bakery products from central stores to an external customer."""

    from_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="central_invoices",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="central_invoices",
    )
    invoice_number = models.CharField(max_length=32, unique=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=CentralInvoiceStatus.choices,
        default=CentralInvoiceStatus.DISPATCHED,
    )
    payment_status = models.CharField(
        max_length=10,
        choices=TransferInvoicePaymentStatus.choices,
        default=TransferInvoicePaymentStatus.UNPAID,
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="central_invoices_marked_paid",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Central invoice {self.invoice_number} — {self.customer}"

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines.all())

    @property
    def total_amount(self):
        from decimal import Decimal

        return sum(
            (line.unit_price or Decimal("0")) * line.quantity for line in self.lines.all()
        )


class CentralInvoiceLine(models.Model):
    central_invoice = models.ForeignKey(
        CentralInvoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="central_invoice_lines",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ("central_invoice", "product")
        ordering = ["product__name"]

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity
