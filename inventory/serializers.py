from decimal import Decimal

from accounts.branch_access import effective_branch_id, user_has_global_branch_access
from django.db import transaction
from rest_framework import serializers

from branches.models import Branch, BranchType
from catalog.constants import (
    ALL_INGREDIENT_CATEGORIES,
    BAKERY_SELLABLE_CATEGORIES,
    STOCK_TAKE_STATION_LABELS,
    ingredient_categories_for_branch_type,
    is_bakery_transfer_product,
    is_ingredient_product,
    stock_take_station_for_product,
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
    StockMovement,
    StockTake,
    StockTakeLine,
    StockTakeType,
    StockTransfer,
    StockTransferStatus,
    WastageEntry,
    WastageReason,
)
from .services import create_stock_take, create_wastage_entry, update_stock_take_lines


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
    delta = serializers.DecimalField(max_digits=12, decimal_places=3)

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("Delta must not be zero.")
        return value


class InventorySetSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.filter(is_active=True))
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True))
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0"))


class StockMovementSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "branch",
            "branch_name",
            "product",
            "product_name",
            "quantity_before",
            "delta",
            "quantity_after",
            "reason",
            "reason_display",
            "note",
            "reference_type",
            "reference_id",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_created_by_name(self, obj):
        return staff_display_name(obj.created_by) if obj.created_by_id else ""


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
BRANCH_TRANSFER_DESTINATION_TYPES = (BranchType.BRANCH,)


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
    returned_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )

    class Meta:
        model = DeliveryNoteLine
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "received_quantity",
            "damaged_quantity",
            "returned_quantity",
            "line_notes",
            "unit_price",
            "line_total",
        ]


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
    total_received_quantity = serializers.SerializerMethodField()
    total_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    paid_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
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
            "remarks",
            "is_flagged",
            "approved_at",
            "approved_by",
            "approved_by_name",
            "created_at",
            "lines",
            "line_count",
            "total_quantity",
            "total_received_quantity",
            "total_amount",
        ]
        read_only_fields = [
            "status",
            "payment_status",
            "paid_at",
            "paid_by",
            "remarks",
            "is_flagged",
            "approved_at",
            "approved_by",
            "created_at",
        ]

    def get_paid_by_name(self, obj):
        return staff_display_name(obj.paid_by)

    def get_approved_by_name(self, obj):
        return staff_display_name(obj.approved_by)

    def get_line_count(self, obj):
        return obj.lines.count()

    def get_total_quantity(self, obj):
        return obj.total_quantity

    def get_total_received_quantity(self, obj):
        return obj.total_received_quantity


class DeliveryNoteReceiptLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    received_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False
    )
    damaged_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False, default=Decimal("0")
    )
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DeliveryNoteReceiptSerializer(serializers.Serializer):
    remarks = serializers.CharField(required=False, allow_blank=True)
    is_flagged = serializers.BooleanField(required=False, default=False)
    lines = DeliveryNoteReceiptLineSerializer(many=True, required=False)


class DeliveryNoteLineCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)

    def validate_product(self, product):
        if not product.is_active:
            raise serializers.ValidationError(
                "Cannot transfer an inactive product."
            )
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
        from inventory.services import create_bakery_delivery_note

        lines_data = validated_data.pop("lines")
        return create_bakery_delivery_note(
            from_branch=validated_data["from_branch"],
            to_branch=validated_data["to_branch"],
            lines=lines_data,
        )


class StoresDeliveryNoteLineCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)

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


class BranchDeliveryNoteLineCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value


class BranchDeliveryNoteCreateSerializer(serializers.Serializer):
    """Inter-branch stock transfer — stock leaves on dispatch."""

    from_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True, branch_type=BranchType.BRANCH)
    )
    to_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(
            is_active=True,
            branch_type__in=BRANCH_TRANSFER_DESTINATION_TYPES,
        )
    )
    lines = BranchDeliveryNoteLineCreateSerializer(many=True)

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
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if user and not user_has_global_branch_access(user):
            from accounts.branch_access import get_staff_branch_id

            staff_branch_id = get_staff_branch_id(user)
            if staff_branch_id is None or staff_branch_id != attrs["from_branch"].id:
                raise serializers.ValidationError(
                    {"from_branch": "You can only transfer stock from your own branch."}
                )
        return attrs

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
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
        return note


def _validate_stores_delivery_lines(to_branch, lines):
    allowed_categories = ingredient_categories_for_branch_type(to_branch.branch_type)
    for index, line in enumerate(lines):
        if line["product"].category.name not in allowed_categories:
            raise serializers.ValidationError(
                {
                    "lines": {
                        index: {
                            "product": (
                                f"{line['product'].name} is not stocked at "
                                f"{to_branch.name}."
                            )
                        }
                    }
                }
            )


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
    as_draft = serializers.BooleanField(required=False, default=False)

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
        _validate_stores_delivery_lines(attrs["to_branch"], attrs["lines"])
        return attrs

    def create(self, validated_data):
        from .services import assign_transfer_invoice_number

        lines_data = validated_data.pop("lines")
        as_draft = validated_data.pop("as_draft", False)
        status = (
            StockTransferStatus.DRAFT
            if as_draft
            else StockTransferStatus.REQUESTED
        )
        note = DeliveryNote.objects.create(status=status, **validated_data)
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
        if not as_draft:
            assign_transfer_invoice_number(note)
        return note


class StoresDeliveryNoteUpdateSerializer(serializers.Serializer):
    to_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(
            is_active=True,
            branch_type__in=STORES_TRANSFER_DESTINATION_TYPES,
        ),
        required=False,
    )
    lines = StoresDeliveryNoteLineCreateSerializer(many=True, required=False)

    def validate_lines(self, value):
        if value is not None:
            if not value:
                raise serializers.ValidationError("Add at least one product line.")
            product_ids = [line["product"].id for line in value]
            if len(product_ids) != len(set(product_ids)):
                raise serializers.ValidationError("Each product may only appear once.")
        return value

    def validate(self, attrs):
        to_branch = attrs.get("to_branch", self.instance.to_branch)
        if self.instance.from_branch_id == to_branch.id:
            raise serializers.ValidationError(
                {"to_branch": "Source and destination branches must differ."}
            )
        lines = attrs.get("lines")
        if lines is not None:
            _validate_stores_delivery_lines(to_branch, lines)
        return attrs

    def update(self, instance, validated_data):
        if instance.status != StockTransferStatus.DRAFT:
            raise serializers.ValidationError(
                "Only draft delivery notes can be edited."
            )
        if instance.from_branch.branch_type != BranchType.STORES:
            raise serializers.ValidationError(
                "Only central stores delivery notes can be edited as drafts."
            )

        lines_data = validated_data.pop("lines", None)
        with transaction.atomic():
            if "to_branch" in validated_data:
                instance.to_branch = validated_data["to_branch"]
            if lines_data is not None:
                instance.lines.all().delete()
                DeliveryNoteLine.objects.bulk_create(
                    [
                        DeliveryNoteLine(
                            delivery_note=instance,
                            product=line["product"],
                            quantity=line["quantity"],
                            unit_price=line["product"].selling_price,
                        )
                        for line in lines_data
                    ]
                )
            instance.save()
        return instance


class StockTakeLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    category_name = serializers.CharField(
        source="product.category.name", read_only=True
    )
    stock_take_station = serializers.SerializerMethodField()
    stock_take_station_display = serializers.SerializerMethodField()
    variance = serializers.SerializerMethodField()

    class Meta:
        model = StockTakeLine
        fields = [
            "id",
            "product",
            "product_name",
            "category_name",
            "stock_take_station",
            "stock_take_station_display",
            "system_quantity",
            "counted_quantity",
            "wastage_quantity",
            "variance",
            "notes",
        ]

    def get_stock_take_station(self, obj):
        return stock_take_station_for_product(obj.product)

    def get_stock_take_station_display(self, obj):
        return STOCK_TAKE_STATION_LABELS[self.get_stock_take_station(obj)]

    def get_variance(self, obj):
        if obj.variance is None:
            return None
        return obj.variance


class StockTakeLineUpdateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    counted_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False, allow_null=True
    )
    wastage_quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=False,
        allow_null=True,
        min_value=0,
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
        stock_take, created = create_stock_take(
            created_by=created_by, **validated_data
        )
        self.stock_take_created = created
        if created and notes:
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
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
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


class WastageEntrySerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    destination_branch_name = serializers.CharField(
        source="destination_branch.name",
        read_only=True,
        allow_null=True,
    )
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    processed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = WastageEntry
        fields = [
            "id",
            "branch",
            "branch_name",
            "product",
            "product_name",
            "quantity",
            "reason",
            "reason_display",
            "destination_branch",
            "destination_branch_name",
            "status",
            "status_display",
            "notes",
            "created_by",
            "created_by_name",
            "processed_by",
            "processed_by_name",
            "created_at",
            "processed_at",
        ]
        read_only_fields = fields

    def get_created_by_name(self, obj):
        return staff_display_name(obj.created_by) if obj.created_by_id else ""

    def get_processed_by_name(self, obj):
        return staff_display_name(obj.processed_by) if obj.processed_by_id else ""


class WastageEntryCreateSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True)
    )
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001")
    )
    reason = serializers.ChoiceField(choices=WastageReason.choices)
    destination_branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    process_now = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        request = self.context.get("request")
        branch = attrs["branch"]
        if request and request.user and request.user.is_authenticated:
            from accounts.branch_access import resolve_branch_filter, NO_BRANCH_ACCESS

            allowed = resolve_branch_filter(
                request.user, requested_branch_id=branch.id
            )
            if allowed is NO_BRANCH_ACCESS or (
                allowed is not None and int(allowed) != int(branch.id)
            ):
                raise serializers.ValidationError(
                    {"branch": "You do not have access to this branch."}
                )
        reason = attrs["reason"]
        destination = attrs.get("destination_branch")
        if reason == WastageReason.BAKERY_REUSE:
            if destination is None:
                raise serializers.ValidationError(
                    {
                        "destination_branch": (
                            "Select the bakery branch receiving this reuse transfer."
                        )
                    }
                )
            if destination.branch_type != BranchType.BAKERY:
                raise serializers.ValidationError(
                    {
                        "destination_branch": (
                            "Bakery reuse destination must be a bakery branch."
                        )
                    }
                )
            if destination.pk == branch.pk:
                raise serializers.ValidationError(
                    {
                        "destination_branch": (
                            "Destination bakery must differ from the source branch."
                        )
                    }
                )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request else None
        process_now = validated_data.pop("process_now", True)
        return create_wastage_entry(
            branch=validated_data["branch"],
            product=validated_data["product"],
            quantity=validated_data["quantity"],
            reason=validated_data["reason"],
            destination_branch=validated_data.get("destination_branch"),
            notes=validated_data.get("notes", ""),
            created_by=user,
            process_now=process_now,
        )
