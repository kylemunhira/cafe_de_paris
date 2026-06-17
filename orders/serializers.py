from decimal import Decimal

from rest_framework import serializers

from catalog.models import Product
from payments.models import Currency

from .models import Expense, Order, OrderItem


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

    kitchen_status_display = serializers.CharField(
        source="get_kitchen_status_display", read_only=True
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
            "kitchen_status",
            "kitchen_status_display",
            "kitchen_started_at",
            "kitchen_ready_at",
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


class ExpenseSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    currency_name = serializers.CharField(source="currency.name", read_only=True)
    currency_symbol = serializers.CharField(source="currency.symbol", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id",
            "branch",
            "branch_name",
            "expense_date",
            "amount",
            "currency",
            "currency_code",
            "currency_name",
            "currency_symbol",
            "description",
            "recorded_by",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = ["recorded_by", "created_at"]

    def get_recorded_by_name(self, obj):
        if not obj.recorded_by:
            return None
        return obj.recorded_by.get_full_name() or obj.recorded_by.username


class ExpenseCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ["branch", "expense_date", "amount", "currency", "description"]

    def validate_amount(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_description(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Description is required.")
        return value

    def validate_branch(self, branch):
        from accounts.branch_access import effective_branch_id

        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return branch
        try:
            allowed_branch_id = effective_branch_id(request.user, branch.id)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if allowed_branch_id is not None and branch.id != allowed_branch_id:
            raise serializers.ValidationError(
                "You can only record expenses for your assigned branch."
            )
        return branch

    def create(self, validated_data):
        request = self.context.get("request")
        recorded_by = request.user if request and request.user.is_authenticated else None
        return Expense.objects.create(recorded_by=recorded_by, **validated_data)
