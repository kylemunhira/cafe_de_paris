from decimal import Decimal

from rest_framework import serializers

from catalog.models import Product
from payments.models import Currency

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "quantity", "price"]


class OrderItemCreateSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
        source="product",
    )
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    payment_currency_name = serializers.CharField(
        source="payment_currency.name",
        read_only=True,
        default=None,
    )
    payment_currency_symbol = serializers.CharField(
        source="payment_currency.symbol",
        read_only=True,
        default=None,
    )

    class Meta:
        model = Order
        fields = [
            "id",
            "branch",
            "branch_name",
            "customer",
            "order_type",
            "table_number",
            "total_amount",
            "payment_currency",
            "payment_currency_name",
            "payment_currency_symbol",
            "exchange_rate",
            "amount_paid",
            "status",
            "receipt_number",
            "items",
            "created_at",
        ]
        read_only_fields = ["total_amount", "exchange_rate", "amount_paid", "created_at"]


class OrderPaySerializer(serializers.Serializer):
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.filter(is_active=True),
        source="payment_currency",
    )


class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderItemCreateSerializer(many=True)

    class Meta:
        model = Order
        fields = ["branch", "customer", "order_type", "table_number", "items"]

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        order = Order.objects.create(**validated_data)

        for item_data in items_data:
            product = item_data["product"]
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item_data["quantity"],
                price=product.selling_price,
            )

        order.recalculate_total()
        return order
