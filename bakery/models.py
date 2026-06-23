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
    quantity_required = models.DecimalField(max_digits=12, decimal_places=2)

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
