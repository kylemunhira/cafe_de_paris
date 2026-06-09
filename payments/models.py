from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Currency(models.Model):
    code = models.CharField(max_length=10, blank=True)
    name = models.CharField(max_length=100, unique=True)
    symbol = models.CharField(max_length=10, blank=True)
    is_base = models.BooleanField(
        default=False,
        help_text="Base currency for exchange rates (only one allowed).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "currencies"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.is_base:
            qs = Currency.objects.filter(is_base=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({"is_base": "Only one base currency is allowed."})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.is_base:
            Currency.objects.filter(is_base=True).exclude(pk=self.pk).update(
                is_base=False
            )
        super().save(*args, **kwargs)

    def get_current_rate(self):
        if self.is_base:
            return Decimal("1")
        rate = (
            self.rates.filter(is_active=True)
            .order_by("-effective_from", "-created_at")
            .first()
        )
        return rate.rate if rate else None

    def convert_from_base(self, base_amount: Decimal) -> Decimal:
        rate = self.get_current_rate()
        if rate is None:
            raise ValidationError(f'No exchange rate configured for "{self.name}".')
        return (base_amount * rate).quantize(Decimal("0.01"))


class CurrencyRate(models.Model):
    currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text="Units of this currency per 1 unit of the base currency.",
    )
    effective_from = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-created_at"]

    def __str__(self):
        return f"{self.currency.name} @ {self.rate} ({self.effective_from})"

    def clean(self):
        super().clean()
        if self.currency_id and self.currency.is_base:
            if self.rate != Decimal("1"):
                raise ValidationError(
                    {"rate": "Base currency exchange rate must be 1."}
                )
