from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from catalog.models import Product
from payments.models import Currency

from customers.models import Customer

from .models import (
    Expense,
    FiscalApprovalStatus,
    Order,
    OrderItem,
    OrderItemAddon,
    OrderPayment,
    OrderStatus,
    OrderType,
    PaymentMethod,
    TenderMethod,
)
from .services import add_items_to_order, find_open_table_order, reprice_order_items


def staff_display_name(user):
    if not user:
        return None
    return user.get_full_name() or user.username


class OrderItemAddonSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItemAddon
        fields = ["id", "menu_addon", "name", "price"]


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    pos_station = serializers.CharField(
        source="product.category.pos_station",
        read_only=True,
    )
    addons = OrderItemAddonSerializer(many=True, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "pos_station",
            "quantity",
            "price",
            "notes",
            "addons",
        ]


class OrderItemCreateSerializer(serializers.Serializer):
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


class OrderPaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    currency_name = serializers.CharField(source="currency.name", read_only=True)
    currency_symbol = serializers.CharField(source="currency.symbol", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = OrderPayment
        fields = [
            "id",
            "method",
            "method_display",
            "currency",
            "currency_code",
            "currency_name",
            "currency_symbol",
            "amount",
            "exchange_rate",
        ]


class OrderPaymentLineSerializer(serializers.Serializer):
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.filter(is_active=True),
        source="currency",
    )
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    method = serializers.ChoiceField(
        choices=TenderMethod.choices,
        required=False,
    )


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payments = OrderPaymentSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    payment_currency_name = serializers.CharField(
        source="payment_currency.name",
        read_only=True,
        default=None,
    )
    payment_currency_code = serializers.CharField(
        source="payment_currency.code",
        read_only=True,
        default=None,
    )
    payment_currency_symbol = serializers.CharField(
        source="payment_currency.symbol",
        read_only=True,
        default=None,
    )
    payment_method_display = serializers.CharField(
        source="get_payment_method_display",
        read_only=True,
        default=None,
    )

    kitchen_status_display = serializers.CharField(
        source="get_kitchen_status_display", read_only=True
    )
    created_by_name = serializers.SerializerMethodField()
    paid_by_name = serializers.SerializerMethodField()
    cancelled_by_name = serializers.SerializerMethodField()
    fiscal_approved_by_name = serializers.SerializerMethodField()
    fiscal_receipt_number = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    customer_account_balance = serializers.SerializerMethodField()
    branch_fiscalization_enabled = serializers.BooleanField(
        source="branch.fiscalization_enabled",
        read_only=True,
    )

    class Meta:
        model = Order
        fields = [
            "id",
            "branch",
            "branch_name",
            "branch_fiscalization_enabled",
            "customer",
            "customer_name",
            "customer_account_balance",
            "order_type",
            "table_number",
            "total_amount",
            "payment_currency",
            "payment_currency_name",
            "payment_currency_code",
            "payment_currency_symbol",
            "exchange_rate",
            "amount_paid",
            "payment_method",
            "payment_method_display",
            "payments",
            "status",
            "kitchen_status",
            "kitchen_status_display",
            "kitchen_started_at",
            "kitchen_ready_at",
            "receipt_number",
            "fiscal_receipt_number",
            "fiscal_approval_status",
            "fiscal_approved_at",
            "fiscal_approved_by",
            "fiscal_approved_by_name",
            "created_by",
            "created_by_name",
            "paid_by",
            "paid_by_name",
            "cancelled_at",
            "cancelled_by",
            "cancelled_by_name",
            "items",
            "created_at",
        ]
        read_only_fields = ["total_amount", "exchange_rate", "amount_paid", "created_at"]

    def get_created_by_name(self, obj):
        return staff_display_name(obj.created_by)

    def get_paid_by_name(self, obj):
        return staff_display_name(obj.paid_by)

    def get_cancelled_by_name(self, obj):
        return staff_display_name(obj.cancelled_by)

    def get_fiscal_approved_by_name(self, obj):
        return staff_display_name(obj.fiscal_approved_by)

    def get_fiscal_receipt_number(self, obj):
        fiscal_receipt = getattr(obj, "fiscal_receipt", None)
        if fiscal_receipt is None:
            return None
        return fiscal_receipt.invoice_no

    def get_customer_name(self, obj):
        if not obj.customer_id:
            return None
        return str(obj.customer)

    def get_customer_account_balance(self, obj):
        if not obj.customer_id:
            return None
        return obj.customer.account_balance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        station = self.context.get("kitchen_station")
        if station:
            data["items"] = [
                item for item in data["items"] if item.get("pos_station") == station
            ]
        return data


class OrderPaySerializer(serializers.Serializer):
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.filter(is_active=True),
        source="payment_currency",
        required=False,
        allow_null=True,
    )
    payment_method = serializers.ChoiceField(
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    payments = OrderPaymentLineSerializer(many=True, required=False)

    def validate(self, attrs):
        payment_method = attrs.get("payment_method", PaymentMethod.CASH)
        payments = attrs.get("payments")

        if payment_method == PaymentMethod.ACCOUNT:
            if payments:
                raise serializers.ValidationError(
                    {"payments": "Cannot mix account payment with tender lines."}
                )
            return attrs

        if payments is not None:
            if not payments:
                raise serializers.ValidationError(
                    {"payments": "At least one payment line is required."}
                )
            currency_ids = [line["currency"].id for line in payments]
            if len(currency_ids) != len(set(currency_ids)):
                raise serializers.ValidationError(
                    {"payments": "Each payment currency can only appear once."}
                )
            return attrs

        if payment_method == PaymentMethod.MULTI:
            raise serializers.ValidationError(
                {"payments": "Split payments require a payments list."}
            )

        if not attrs.get("payment_currency"):
            raise serializers.ValidationError(
                {"currency_id": "This field is required for cash payments."}
            )

        return attrs
class OrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["customer"]

    def validate_customer(self, customer):
        if customer is None:
            return customer
        if not Customer.objects.filter(pk=customer.pk).exists():
            raise serializers.ValidationError("Customer not found.")
        return customer

    def validate(self, attrs):
        if self.instance.status != OrderStatus.OPEN:
            raise serializers.ValidationError("Only open orders can be updated.")
        return attrs

    def update(self, instance, validated_data):
        previous_customer_id = instance.customer_id
        order = super().update(instance, validated_data)
        if order.customer_id != previous_customer_id:
            reprice_order_items(order)
        return order

    def to_representation(self, instance):
        return OrderSerializer(instance, context=self.context).data


class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderItemCreateSerializer(many=True)

    class Meta:
        model = Order
        fields = ["branch", "customer", "order_type", "table_number", "items"]

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        branch = validated_data["branch"]
        table_number = (validated_data.get("table_number") or "").strip()
        order_type = validated_data.get("order_type")

        existing = None
        if order_type == OrderType.DINE_IN and table_number:
            existing = find_open_table_order(branch=branch, table_number=table_number)

        if existing:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=existing.pk)
                add_items_to_order(order, items_data)
            return order

        order = Order.objects.create(created_by=user, **validated_data)
        add_items_to_order(order, items_data)
        return order


class ExpenseSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    currency_name = serializers.CharField(source="currency.name", read_only=True)
    currency_symbol = serializers.CharField(source="currency.symbol", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
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
            "supplier",
            "supplier_name",
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
        fields = [
            "branch",
            "expense_date",
            "amount",
            "currency",
            "description",
            "supplier",
        ]

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

    def validate_supplier(self, supplier):
        if supplier is not None and not supplier.is_active:
            raise serializers.ValidationError("Supplier is inactive.")
        return supplier

    def create(self, validated_data):
        request = self.context.get("request")
        recorded_by = request.user if request and request.user.is_authenticated else None
        return Expense.objects.create(recorded_by=recorded_by, **validated_data)
