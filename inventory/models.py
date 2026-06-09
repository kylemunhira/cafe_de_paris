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
    status = models.CharField(
        max_length=20,
        choices=StockTransferStatus.choices,
        default=StockTransferStatus.REQUESTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Delivery note #{self.pk} {self.from_branch} -> {self.to_branch}"

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines.all())


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

    class Meta:
        unique_together = ("delivery_note", "product")
        ordering = ["product__name"]

    def __str__(self):
        return f"{self.product} x {self.quantity}"


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
