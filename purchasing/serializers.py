from decimal import Decimal

from accounts.branch_access import effective_branch_id
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from branches.models import Branch, BranchType
from catalog.constants import (
    ALL_INGREDIENT_CATEGORIES,
    ingredient_categories_for_branch_type,
    is_ingredient_product,
)
from catalog.models import Product

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier
from .services import apply_purchase_order_inventory


def _validate_purchase_lines_for_branch(branch, lines):
    """Central stores and bakery POs may only include ingredients valid for that branch."""
    errors = []
    allowed_categories = ingredient_categories_for_branch_type(branch.branch_type)
    for index, line in enumerate(lines):
        product = line["product"]
        if branch.branch_type in (BranchType.BAKERY, BranchType.STORES):
            if product.category.name not in allowed_categories:
                branch_label = (
                    "Central stores"
                    if branch.branch_type == BranchType.STORES
                    else "Bakery"
                )
                allowed = ", ".join(sorted(allowed_categories))
                errors.append(
                    {
                        "lines": {
                            index: {
                                "product": (
                                    f"{branch_label} purchase orders can only include "
                                    f"raw materials ({allowed})."
                                )
                            }
                        }
                    }
                )
    if errors:
        merged = {}
        for entry in errors:
            for field, value in entry.items():
                merged.setdefault(field, {}).update(value)
        raise serializers.ValidationError(merged)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "vat_number",
            "contact_person",
            "email",
            "phone",
            "address",
            "notes",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    line_total = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True
    )

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "unit_cost",
            "line_total",
        ]


class PurchaseOrderLineCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True).select_related("category")
    )
    quantity = serializers.DecimalField(max_digits=16, decimal_places=4)
    unit_cost = serializers.DecimalField(
        max_digits=16, decimal_places=4, required=False, default=Decimal("0")
    )

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_unit_cost(self, value):
        if value < Decimal("0"):
            raise serializers.ValidationError("Unit cost cannot be negative.")
        return value


class PurchaseOrderSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    created_by_name = serializers.SerializerMethodField()
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    subtotal_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    vat_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    total_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    line_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "branch",
            "branch_name",
            "supplier",
            "supplier_name",
            "status",
            "status_display",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
            "submitted_at",
            "approved_at",
            "received_at",
            "lines",
            "subtotal_amount",
            "vat_amount",
            "total_amount",
            "line_count",
        ]
        read_only_fields = [
            "status",
            "created_by",
            "created_at",
            "submitted_at",
            "approved_at",
            "received_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return obj.created_by.get_full_name() or obj.created_by.username


class PurchaseOrderCreateSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True, branch_type=BranchType.STORES)
    )
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.filter(is_active=True)
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = PurchaseOrderLineCreateSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one product line.")
        product_ids = [line["product"].id for line in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("Each product may only appear once.")
        return value

    def validate_branch(self, branch):
        if branch.branch_type != BranchType.STORES:
            raise serializers.ValidationError(
                "Purchases can only be recorded for central stores."
            )
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return branch
        try:
            allowed_branch_id = effective_branch_id(request.user)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if allowed_branch_id is not None and branch.id != allowed_branch_id:
            raise serializers.ValidationError(
                "You can only create purchase orders for your assigned branch."
            )
        return branch

    def validate(self, attrs):
        branch = attrs.get("branch")
        lines = attrs.get("lines")
        if branch and lines:
            _validate_purchase_lines_for_branch(branch, lines)
        return attrs

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        notes = validated_data.pop("notes", "")
        request = self.context.get("request")
        created_by = request.user if request and request.user.is_authenticated else None

        with transaction.atomic():
            now = timezone.now()
            purchase_order = PurchaseOrder.objects.create(
                notes=notes,
                created_by=created_by,
                status=PurchaseOrderStatus.RECEIVED,
                submitted_at=now,
                approved_at=now,
                received_at=now,
                **validated_data,
            )
            PurchaseOrderLine.objects.bulk_create(
                [
                    PurchaseOrderLine(
                        purchase_order=purchase_order,
                        product=line["product"],
                        quantity=line["quantity"],
                        unit_cost=line.get("unit_cost", Decimal("0")),
                    )
                    for line in lines_data
                ]
            )
            apply_purchase_order_inventory(purchase_order)
        return purchase_order


class PurchaseOrderUpdateSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.filter(is_active=True), required=False
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = PurchaseOrderLineCreateSerializer(many=True, required=False)

    def validate_lines(self, value):
        if value is not None:
            if not value:
                raise serializers.ValidationError("Add at least one product line.")
            product_ids = [line["product"].id for line in value]
            if len(product_ids) != len(set(product_ids)):
                raise serializers.ValidationError("Each product may only appear once.")
        return value

    def validate(self, attrs):
        lines = attrs.get("lines")
        if lines is not None:
            _validate_purchase_lines_for_branch(self.instance.branch, lines)
        return attrs

    def update(self, instance, validated_data):
        if instance.status != PurchaseOrderStatus.DRAFT:
            raise serializers.ValidationError(
                "Only draft purchase orders can be edited."
            )

        lines_data = validated_data.pop("lines", None)

        with transaction.atomic():
            if "supplier" in validated_data:
                instance.supplier = validated_data["supplier"]
            if "notes" in validated_data:
                instance.notes = validated_data["notes"]
            if lines_data is not None:
                instance.lines.all().delete()
                PurchaseOrderLine.objects.bulk_create(
                    [
                        PurchaseOrderLine(
                            purchase_order=instance,
                            product=line["product"],
                            quantity=line["quantity"],
                            unit_cost=line.get("unit_cost", Decimal("0")),
                        )
                        for line in lines_data
                    ]
                )
            instance.save()
        return instance
