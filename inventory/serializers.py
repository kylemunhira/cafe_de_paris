from decimal import Decimal

from accounts.branch_access import effective_branch_id
from django.db import transaction
from rest_framework import serializers

from branches.models import Branch, BranchType
from catalog.constants import (
    ALL_INGREDIENT_CATEGORIES,
    BAKERY_SELLABLE_CATEGORIES,
    ingredient_categories_for_branch_type,
    is_bakery_transfer_product,
    is_ingredient_product,
)
from catalog.models import Product
from customers.models import Customer
from orders.serializers import staff_display_name

from .models import (
    BranchInventory,
    CentralInvoice,
    CentralInvoiceLine,
    DeliveryNote,
    DeliveryNoteLine,
    StockTake,
    StockTakeLine,
    StockTakeType,
    StockTransfer,
)
from .services import create_stock_take, update_stock_take_lines


class BranchInventorySerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = BranchInventory
        fields = [
            "id",
            "branch",
            "branch_name",
            "product",
            "product_name",
            "quantity",
            "last_updated",
        ]
        read_only_fields = ["last_updated"]


class InventoryAdjustSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.filter(is_active=True))
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True))
    delta = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("Delta must not be zero.")
        return value


class StockTransferSerializer(serializers.ModelSerializer):
    from_branch_name = serializers.CharField(source="from_branch.name", read_only=True)
    to_branch_name = serializers.CharField(source="to_branch.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockTransfer
        fields = [
            "id",
            "from_branch",
            "from_branch_name",
            "to_branch",
            "to_branch_name",
            "product",
            "product_name",
            "quantity",
            "status",
            "created_at",
        ]
        read_only_fields = ["status", "created_at"]


class StockTransferCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTransfer
        fields = ["from_branch", "to_branch", "product", "quantity"]

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate(self, attrs):
        if attrs["from_branch"] == attrs["to_branch"]:
            raise serializers.ValidationError(
                {"to_branch": "Source and destination branches must differ."}
            )
        if not attrs["product"].is_active:
            raise serializers.ValidationError(
                {"product": "Cannot transfer an inactive product."}
            )
        return attrs


BAKERY_TRANSFER_DESTINATION_TYPES = (BranchType.STORES, BranchType.BRANCH)
STORES_TRANSFER_DESTINATION_TYPES = (BranchType.BRANCH, BranchType.HQ, BranchType.BAKERY)


class BakeryTransferCreateSerializer(serializers.ModelSerializer):
    """Stock transfer from central bakery to a branch or HQ."""

    class Meta:
        model = StockTransfer
        fields = ["from_branch", "to_branch", "product", "quantity"]

    def validate_from_branch(self, branch):
        if branch.branch_type != BranchType.BAKERY:
            raise serializers.ValidationError(
                "Transfers must originate from a central bakery."
            )
        if not branch.is_active:
            raise serializers.ValidationError("Bakery branch is not active.")
        return branch

    def validate_to_branch(self, branch):
        if branch.branch_type not in BAKERY_TRANSFER_DESTINATION_TYPES:
            raise serializers.ValidationError(
                "Transfers must be sent to central stores or a branch."
            )
        if not branch.is_active:
            raise serializers.ValidationError("Destination branch is not active.")
        return branch

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_product(self, product):
        if not product.is_active:
            raise serializers.ValidationError("Cannot transfer an inactive product.")
        if not is_bakery_transfer_product(product):
            raise serializers.ValidationError(
                "Only finished bakery products can be transferred to branches. "
                f"Allowed categories: {', '.join(sorted(BAKERY_SELLABLE_CATEGORIES))}."
            )
        return product

    def validate(self, attrs):
        if attrs["from_branch"] == attrs["to_branch"]:
            raise serializers.ValidationError(
                {"to_branch": "Source and destination branches must differ."}
            )
        return attrs


class DeliveryNoteLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    line_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = DeliveryNoteLine
        fields = ["id", "product", "product_name", "quantity", "unit_price", "line_total"]


class DeliveryNoteSerializer(serializers.ModelSerializer):
    from_branch_name = serializers.CharField(source="from_branch.name", read_only=True)
    to_branch_name = serializers.CharField(source="to_branch.name", read_only=True)
    to_branch_location = serializers.CharField(source="to_branch.location", read_only=True)
    from_branch_location = serializers.CharField(
        source="from_branch.location", read_only=True
    )
    lines = DeliveryNoteLineSerializer(many=True, read_only=True)
    line_count = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()
    total_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    paid_by_name = serializers.SerializerMethodField()
    payment_status_display = serializers.CharField(
        source="get_payment_status_display",
        read_only=True,
    )

    class Meta:
        model = DeliveryNote
        fields = [
            "id",
            "from_branch",
            "from_branch_name",
            "from_branch_location",
            "to_branch",
            "to_branch_name",
            "to_branch_location",
            "invoice_number",
            "status",
            "payment_status",
            "payment_status_display",
            "paid_at",
            "paid_by",
            "paid_by_name",
            "created_at",
            "lines",
            "line_count",
            "total_quantity",
            "total_amount",
        ]
        read_only_fields = [
            "status",
            "payment_status",
            "paid_at",
            "paid_by",
            "created_at",
        ]

    def get_paid_by_name(self, obj):
        return staff_display_name(obj.paid_by)

    def get_line_count(self, obj):
        return obj.lines.count()

    def get_total_quantity(self, obj):
        return obj.total_quantity


class DeliveryNoteLineCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_product(self, product):
        if not is_bakery_transfer_product(product):
            raise serializers.ValidationError(
                "Only finished bakery products can be transferred to branches. "
                f"Allowed categories: {', '.join(sorted(BAKERY_SELLABLE_CATEGORIES))}."
            )
        return product

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value


class BakeryDeliveryNoteCreateSerializer(serializers.Serializer):
    from_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True, branch_type=BranchType.BAKERY)
    )
    to_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(
            is_active=True,
            branch_type__in=BAKERY_TRANSFER_DESTINATION_TYPES,
        )
    )
    lines = DeliveryNoteLineCreateSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one product line.")
        product_ids = [line["product"].id for line in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("Each product may only appear once.")
        return value

    def validate(self, attrs):
        if attrs["from_branch"] == attrs["to_branch"]:
            raise serializers.ValidationError(
                {"to_branch": "Source and destination branches must differ."}
            )
        return attrs

    def create(self, validated_data):
        from inventory.services import finalize_bakery_delivery_note_creation

        lines_data = validated_data.pop("lines")
        with transaction.atomic():
            note = DeliveryNote.objects.create(**validated_data)
            DeliveryNoteLine.objects.bulk_create(
                [
                    DeliveryNoteLine(
                        delivery_note=note,
                        product=line["product"],
                        quantity=line["quantity"],
                    )
                    for line in lines_data
                ]
            )
            return finalize_bakery_delivery_note_creation(note)


class StoresDeliveryNoteLineCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_product(self, product):
        if not is_ingredient_product(product):
            allowed = ", ".join(sorted(ALL_INGREDIENT_CATEGORIES))
            raise serializers.ValidationError(
                f"Only ingredients can be transferred from central stores ({allowed})."
            )
        return product

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value


class StoresDeliveryNoteCreateSerializer(serializers.Serializer):
    from_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True, branch_type=BranchType.STORES)
    )
    to_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(
            is_active=True,
            branch_type__in=STORES_TRANSFER_DESTINATION_TYPES,
        )
    )
    lines = StoresDeliveryNoteLineCreateSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one product line.")
        product_ids = [line["product"].id for line in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("Each product may only appear once.")
        return value

    def validate(self, attrs):
        if attrs["from_branch"] == attrs["to_branch"]:
            raise serializers.ValidationError(
                {"to_branch": "Source and destination branches must differ."}
            )
        allowed_categories = ingredient_categories_for_branch_type(attrs["to_branch"].branch_type)
        for index, line in enumerate(attrs["lines"]):
            if line["product"].category.name not in allowed_categories:
                raise serializers.ValidationError(
                    {
                        "lines": {
                            index: {
                                "product": (
                                    f"{line['product'].name} is not stocked at "
                                    f"{attrs['to_branch'].name}."
                                )
                            }
                        }
                    }
                )
        return attrs

    def create(self, validated_data):
        from .services import assign_transfer_invoice_number

        lines_data = validated_data.pop("lines")
        note = DeliveryNote.objects.create(**validated_data)
        DeliveryNoteLine.objects.bulk_create(
            [
                DeliveryNoteLine(
                    delivery_note=note,
                    product=line["product"],
                    quantity=line["quantity"],
                    unit_price=line["product"].selling_price,
                )
                for line in lines_data
            ]
        )
        assign_transfer_invoice_number(note)
        return note


class StockTakeLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    category_name = serializers.CharField(
        source="product.category.name", read_only=True
    )
    variance = serializers.SerializerMethodField()

    class Meta:
        model = StockTakeLine
        fields = [
            "id",
            "product",
            "product_name",
            "category_name",
            "system_quantity",
            "counted_quantity",
            "variance",
            "notes",
        ]

    def get_variance(self, obj):
        if obj.variance is None:
            return None
        return obj.variance


class StockTakeLineUpdateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    counted_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


class StockTakeSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    stock_take_type_display = serializers.CharField(
        source="get_stock_take_type_display", read_only=True
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    created_by_name = serializers.SerializerMethodField()
    lines = StockTakeLineSerializer(many=True, read_only=True)
    line_count = serializers.IntegerField(read_only=True)
    variance_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = StockTake
        fields = [
            "id",
            "branch",
            "branch_name",
            "stock_take_type",
            "stock_take_type_display",
            "status",
            "status_display",
            "count_date",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
            "completed_at",
            "lines",
            "line_count",
            "variance_count",
        ]
        read_only_fields = [
            "status",
            "created_by",
            "created_at",
            "completed_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return obj.created_by.get_full_name() or obj.created_by.username


class StockTakeCreateSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True)
    )
    stock_take_type = serializers.ChoiceField(choices=StockTakeType.choices)
    count_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_branch(self, branch):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return branch
        try:
            allowed_branch_id = effective_branch_id(request.user)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if allowed_branch_id is not None and branch.id != allowed_branch_id:
            raise serializers.ValidationError(
                "You can only create stock takes for your assigned branch."
            )
        return branch

    def create(self, validated_data):
        notes = validated_data.pop("notes", "")
        request = self.context.get("request")
        created_by = request.user if request and request.user.is_authenticated else None
        stock_take = create_stock_take(created_by=created_by, **validated_data)
        if notes:
            stock_take.notes = notes
            stock_take.save(update_fields=["notes"])
        return stock_take


class StockTakeLinesUpdateSerializer(serializers.Serializer):
    lines = StockTakeLineUpdateSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("Provide at least one line to update.")
        return value

    def update(self, instance, validated_data):
        return update_stock_take_lines(instance, validated_data["lines"])


class CentralInvoiceLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    line_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = CentralInvoiceLine
        fields = ["id", "product", "product_name", "quantity", "unit_price", "line_total"]


class CentralInvoiceSerializer(serializers.ModelSerializer):
    from_branch_name = serializers.CharField(source="from_branch.name", read_only=True)
    customer_name = serializers.CharField(source="customer.__str__", read_only=True)
    lines = CentralInvoiceLineSerializer(many=True, read_only=True)
    line_count = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()
    total_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    paid_by_name = serializers.SerializerMethodField()
    payment_status_display = serializers.CharField(
        source="get_payment_status_display",
        read_only=True,
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CentralInvoice
        fields = [
            "id",
            "from_branch",
            "from_branch_name",
            "customer",
            "customer_name",
            "invoice_number",
            "status",
            "status_display",
            "payment_status",
            "payment_status_display",
            "paid_at",
            "paid_by",
            "paid_by_name",
            "notes",
            "created_at",
            "lines",
            "line_count",
            "total_quantity",
            "total_amount",
        ]
        read_only_fields = [
            "invoice_number",
            "status",
            "payment_status",
            "paid_at",
            "paid_by",
            "created_at",
        ]

    def get_paid_by_name(self, obj):
        return staff_display_name(obj.paid_by)

    def get_line_count(self, obj):
        return obj.lines.count()

    def get_total_quantity(self, obj):
        return obj.total_quantity


class CentralInvoiceLineCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
    )

    def validate_product(self, product):
        if not is_bakery_transfer_product(product):
            raise serializers.ValidationError(
                "Only finished bakery products can be sold on central invoices. "
                f"Allowed categories: {', '.join(sorted(BAKERY_SELLABLE_CATEGORIES))}."
            )
        return product

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value


class CentralInvoiceCreateSerializer(serializers.Serializer):
    from_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True, branch_type=BranchType.STORES)
    )
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all()
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = CentralInvoiceLineCreateSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one product line.")
        product_ids = [line["product"].id for line in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("Each product may only appear once.")
        return value

    def create(self, validated_data):
        from inventory.services import finalize_central_invoice_creation

        lines_data = validated_data.pop("lines")
        notes = validated_data.pop("notes", "")
        with transaction.atomic():
            invoice = CentralInvoice.objects.create(notes=notes, **validated_data)
            CentralInvoiceLine.objects.bulk_create(
                [
                    CentralInvoiceLine(
                        central_invoice=invoice,
                        product=line["product"],
                        quantity=line["quantity"],
                        unit_price=line.get("unit_price") or line["product"].selling_price,
                    )
                    for line in lines_data
                ]
            )
            return finalize_central_invoice_creation(invoice)
