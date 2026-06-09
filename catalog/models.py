from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_asset = models.BooleanField(
        default=False,
        help_text="Assets are included in monthly stock takes only, not daily counts.",
    )

    class Meta:
        verbose_name_plural = "product categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=120)
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
    )
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_qty = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Tax percentage, e.g. 15 for 15%",
    )
    hs_code = models.CharField(
        max_length=20,
        blank=True,
        default="00000000",
        help_text="Harmonized System code for fiscal receipts.",
    )
    fiscal_tax_code = models.CharField(
        max_length=5,
        blank=True,
        help_text="ZIMRA tax code, e.g. E (standard rated) or B (zero rated).",
    )
    fiscal_tax_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ZIMRA tax ID for this product's tax category.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
