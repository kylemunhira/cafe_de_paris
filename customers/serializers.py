from decimal import Decimal

from rest_framework import serializers

from accounts.branch_access import effective_branch_id
from branches.models import Branch
from payments.models import Currency

from .models import Customer, CustomerAccountTransaction


class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    account_type_display = serializers.CharField(
        source="get_account_type_display",
        read_only=True,
    )

    class Meta:
        model = Customer
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "email",
            "account_type",
            "account_type_display",
            "loyalty_points",
            "account_balance",
            "credit_limit",
            "created_at",
        ]
        read_only_fields = ["created_at", "account_balance"]

    def get_full_name(self, obj):
        return str(obj)


class CustomerAccountTransactionSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    currency_name = serializers.CharField(source="currency.name", read_only=True, default=None)
    currency_code = serializers.CharField(source="currency.code", read_only=True, default=None)
    currency_symbol = serializers.CharField(source="currency.symbol", read_only=True, default=None)
    transaction_type_display = serializers.CharField(
        source="get_transaction_type_display",
        read_only=True,
    )
    statement_label = serializers.CharField(read_only=True)
    recorded_by_name = serializers.SerializerMethodField()
    recorded_by_username = serializers.SerializerMethodField()
    order_id = serializers.IntegerField(source="order.id", read_only=True, default=None)

    class Meta:
        model = CustomerAccountTransaction
        fields = [
            "id",
            "customer",
            "branch",
            "branch_name",
            "transaction_type",
            "transaction_type_display",
            "statement_label",
            "amount",
            "balance_after",
            "currency",
            "currency_code",
            "currency_name",
            "currency_symbol",
            "amount_received",
            "order_id",
            "notes",
            "recorded_by",
            "recorded_by_name",
            "recorded_by_username",
            "created_at",
        ]
        read_only_fields = fields

    def get_recorded_by_name(self, obj):
        if not obj.recorded_by:
            return None
        return obj.recorded_by.get_full_name() or obj.recorded_by.username

    def get_recorded_by_username(self, obj):
        if not obj.recorded_by:
            return None
        return obj.recorded_by.username


class CustomerDepositSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.filter(is_active=True),
        source="currency",
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    notes = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    def validate_branch(self, branch):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return branch
        try:
            allowed_branch_id = effective_branch_id(request.user, branch.id)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if allowed_branch_id is not None and branch.id != allowed_branch_id:
            raise serializers.ValidationError(
                "You can only record deposits for your assigned branch."
            )
        return branch
