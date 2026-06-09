from rest_framework import serializers

from .models import Currency, CurrencyRate


class CurrencySerializer(serializers.ModelSerializer):
    current_rate = serializers.SerializerMethodField()

    class Meta:
        model = Currency
        fields = [
            "id",
            "code",
            "name",
            "symbol",
            "is_base",
            "is_active",
            "current_rate",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Currency name is required.")
        qs = Currency.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f'A currency named "{name}" already exists.'
            )
        return name

    def validate_code(self, value):
        return value.strip().upper() if value else ""

    def get_current_rate(self, obj):
        if obj.is_base:
            return "1"
        rate = (
            obj.rates.filter(is_active=True).order_by("-effective_from", "-created_at").first()
        )
        return str(rate.rate) if rate else None


class CurrencyRateSerializer(serializers.ModelSerializer):
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    currency_name = serializers.CharField(source="currency.name", read_only=True)

    class Meta:
        model = CurrencyRate
        fields = [
            "id",
            "currency",
            "currency_code",
            "currency_name",
            "rate",
            "effective_from",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        currency = attrs.get("currency") or getattr(self.instance, "currency", None)
        rate = attrs.get("rate")
        if currency and currency.is_base and rate is not None and rate != 1:
            raise serializers.ValidationError(
                {"rate": "Base currency exchange rate must be 1."}
            )
        return attrs

