from decimal import Decimal

from rest_framework import serializers

from catalog.models import Product
from payments.models import Currency


class SyncOrderItemSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
        source="product",
    )
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=200)
    addon_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )


class SyncOrderPaymentSerializer(serializers.Serializer):
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.filter(is_active=True),
        source="payment_currency",
    )
    paid_at = serializers.DateTimeField(required=False)


class SyncOrderPushSerializer(serializers.Serializer):
    client_id = serializers.UUIDField()
    order_type = serializers.ChoiceField(choices=["dine_in", "takeaway"])
    table_number = serializers.CharField(required=False, allow_blank=True, default="")
    created_at = serializers.DateTimeField(required=False)
    items = SyncOrderItemSerializer(many=True)
    payment = SyncOrderPaymentSerializer(required=False, allow_null=True)
