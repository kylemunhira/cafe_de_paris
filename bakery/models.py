from decimal import Decimal

from django.conf import settings
from django.db import models

from branches.models import Branch
from catalog.models import Product


class Recipe(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="recipes_as_output",
    )
    ingredient = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="recipes_as_ingredient",
    )
    quantity_required = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        unique_together = ("product", "ingredient")
        verbose_name_plural = "recipes"
        ordering = ["product__name", "ingredient__name"]

    def __str__(self):
        return f"{self.product} needs {self.quantity_required} of {self.ingredient}"


class ProductionOrderStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class ProductionOrder(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="production_orders",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="production_orders",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=ProductionOrderStatus.choices,
        default=ProductionOrderStatus.PLANNED,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="production_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Production #{self.pk} - {self.product} x {self.quantity}"


class ProductionSheetStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class ProductionSheet(models.Model):
    """Daily bakery production entry — quantities destined for each branch."""

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="production_sheets",
        help_text="Central bakery where production is recorded.",
    )
    production_date = models.DateField()
    status = models.CharField(
        max_length=12,
        choices=ProductionSheetStatus.choices,
        default=ProductionSheetStatus.DRAFT,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="production_sheets_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-production_date", "-created_at"]

    def __str__(self):
        return f"Production sheet #{self.pk} — {self.branch} {self.production_date}"


class ProductionSheetLine(models.Model):
    sheet = models.ForeignKey(
        ProductionSheet,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="production_sheet_lines",
    )

    class Meta:
        unique_together = ("sheet", "product")
        ordering = ["product__category__name", "product__name"]

    def __str__(self):
        return f"{self.product} on sheet #{self.sheet_id}"

    @property
    def total_quantity(self):
        total = Decimal("0")
        for allocation in self.allocations.all():
            if allocation.quantity is not None:
                total += allocation.quantity
        return total


class ProductionSheetAllocation(models.Model):
    line = models.ForeignKey(
        ProductionSheetLine,
        on_delete=models.CASCADE,
        related_name="allocations",
    )
    destination_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="production_sheet_allocations",
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        unique_together = ("line", "destination_branch")
        ordering = ["destination_branch__name"]

    def __str__(self):
        return (
            f"{self.line.product} → {self.destination_branch}: "
            f"{self.quantity if self.quantity is not None else '—'}"
        )
