from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class PosStation(models.TextChoices):
    BAR = "bar", "Bar"
    KITCHEN = "kitchen", "Kitchen"


class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_asset = models.BooleanField(
        default=False,
        help_text="Assets are included in monthly stock takes only, not daily counts.",
    )
    pos_station = models.CharField(
        max_length=20,
        choices=PosStation.choices,
        blank=True,
        default="",
        help_text="Where POS items in this category are prepared (bar or kitchen).",
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
    daily_stock_take = models.BooleanField(
        default=False,
        help_text="Include this product in daily stock counts at branches that stock it.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MenuAddonSelectionType(models.TextChoices):
    MULTIPLE = "multiple", "Multiple"
    SINGLE = "single", "Single"


class MenuAddonGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    selection_type = models.CharField(
        max_length=20,
        choices=MenuAddonSelectionType.choices,
        default=MenuAddonSelectionType.MULTIPLE,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class MenuAddon(models.Model):
    group = models.ForeignKey(
        MenuAddonGroup,
        on_delete=models.CASCADE,
        related_name="addons",
    )
    name = models.CharField(max_length=120)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "name"],
                name="catalog_menuaddon_unique_group_name",
            ),
        ]

    def __str__(self):
        return self.name


class ProductMenuAddonGroup(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="addon_group_links",
    )
    group = models.ForeignKey(
        MenuAddonGroup,
        on_delete=models.CASCADE,
        related_name="product_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "group"],
                name="catalog_productmenuaddongroup_unique",
            ),
        ]
