from decimal import Decimal

from rest_framework import serializers

from branches.models import Branch, BranchType
from catalog.constants import is_bakery_transfer_product
from catalog.models import Product

from .models import (
    ProductionOrder,
    ProductionSheet,
    ProductionSheetAllocation,
    ProductionSheetLine,
    Recipe,
)
from .services import (
    InsufficientIngredientsError,
    InvalidProductionBranchError,
    InvalidProductionProductError,
    InvalidProductionSheetStateError,
    NoRecipeError,
    complete_production,
    create_production_sheet,
    destination_column_label,
    production_destination_branches,
    update_production_sheet_lines,
)


class RecipeSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    menu_addon_name = serializers.SerializerMethodField()
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    product_category = serializers.SerializerMethodField()
    ingredient_category = serializers.SerializerMethodField()
    ingredient_unit_cost = serializers.DecimalField(
        source="ingredient.selling_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    line_cost = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = [
            "id",
            "product",
            "product_name",
            "product_category",
            "menu_addon",
            "menu_addon_name",
            "ingredient",
            "ingredient_name",
            "ingredient_category",
            "quantity_required",
            "ingredient_unit_cost",
            "line_cost",
        ]
        extra_kwargs = {
            "product": {"required": False, "allow_null": True},
            "menu_addon": {"required": False, "allow_null": True},
        }

    def get_product_name(self, obj):
        return obj.product.name if obj.product_id else None

    def get_menu_addon_name(self, obj):
        return obj.menu_addon.name if obj.menu_addon_id else None

    def get_product_category(self, obj):
        if obj.product_id and obj.product.category_id:
            return obj.product.category.name
        if obj.menu_addon_id and obj.menu_addon.group_id:
            return obj.menu_addon.group.name
        return None

    def get_ingredient_category(self, obj):
        group = obj.ingredient.group_category
        if group is not None:
            return group.name
        return obj.ingredient.category.name

    def get_line_cost(self, obj):
        return (obj.quantity_required * obj.ingredient.selling_price).quantize(
            Decimal("0.01")
        )

    def validate_quantity_required(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate(self, attrs):
        product = attrs.get("product", getattr(self.instance, "product", None))
        if "product" in attrs and attrs["product"] is None:
            product = None
        menu_addon = attrs.get("menu_addon", getattr(self.instance, "menu_addon", None))
        if "menu_addon" in attrs and attrs["menu_addon"] is None:
            menu_addon = None
        ingredient = attrs.get("ingredient") or getattr(self.instance, "ingredient", None)

        if bool(product) == bool(menu_addon):
            raise serializers.ValidationError(
                "Provide either product or menu_addon (exactly one)."
            )

        if product and ingredient and product == ingredient:
            raise serializers.ValidationError(
                {"ingredient": "Output product and ingredient must differ."}
            )

        # Active checks apply when creating, or when product/ingredient is being set.
        # Quantity-only updates on existing lines must still work if a product was later deactivated.
        creating = self.instance is None
        if creating or "product" in attrs:
            if product and not product.is_active:
                raise serializers.ValidationError(
                    {"product": "Cannot use an inactive product as recipe output."}
                )
        if creating or "menu_addon" in attrs:
            if menu_addon and not menu_addon.is_active:
                raise serializers.ValidationError(
                    {"menu_addon": "Cannot use an inactive add-on as recipe output."}
                )
        if creating or "ingredient" in attrs:
            if ingredient and not ingredient.is_active:
                raise serializers.ValidationError(
                    {"ingredient": "Cannot use an inactive product as an ingredient."}
                )

        if product and ingredient:
            qs = Recipe.objects.filter(product=product, ingredient=ingredient)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"ingredient": "This ingredient is already on the recipe."}
                )
        if menu_addon and ingredient:
            qs = Recipe.objects.filter(menu_addon=menu_addon, ingredient=ingredient)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"ingredient": "This ingredient is already on the recipe."}
                )

        return attrs


class ProductionOrderSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductionOrder
        fields = [
            "id",
            "branch",
            "branch_name",
            "product",
            "product_name",
            "quantity",
            "status",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = [
            "status",
            "created_by",
            "created_by_name",
            "created_at",
        ]

    def get_created_by_name(self, obj):
        user = obj.created_by
        if not user:
            return None
        full_name = user.get_full_name().strip()
        return full_name or user.username


class ProductionPreviewSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True, branch_type=BranchType.BAKERY)
    )
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_product(self, product):
        if not is_bakery_transfer_product(product):
            raise serializers.ValidationError(
                "Only finished bakery products can be produced."
            )
        return product


class ProductionCompleteSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True, branch_type=BranchType.BAKERY)
    )
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_product(self, product):
        if not is_bakery_transfer_product(product):
            raise serializers.ValidationError(
                "Only finished bakery products can be produced."
            )
        return product

    def create(self, validated_data):
        request = self.context.get("request")
        created_by = request.user if request and request.user.is_authenticated else None
        try:
            return complete_production(
                validated_data["branch"],
                validated_data["product"],
                validated_data["quantity"],
                created_by=created_by,
            )
        except NoRecipeError as exc:
            raise serializers.ValidationError({"product": str(exc)}) from exc
        except InvalidProductionBranchError as exc:
            raise serializers.ValidationError({"branch": str(exc)}) from exc
        except InvalidProductionProductError as exc:
            raise serializers.ValidationError({"product": str(exc)}) from exc
        except InsufficientIngredientsError as exc:
            raise serializers.ValidationError(
                {
                    "detail": str(exc),
                    "shortages": [
                        {
                            "ingredient_id": item.ingredient.id,
                            "ingredient_name": item.ingredient.name,
                            "required": item.required,
                            "available": item.available,
                        }
                        for item in exc.shortages
                    ],
                }
            ) from exc


class ProductionSheetAllocationSerializer(serializers.ModelSerializer):
    destination_branch_name = serializers.CharField(
        source="destination_branch.name", read_only=True
    )
    destination_label = serializers.SerializerMethodField()

    class Meta:
        model = ProductionSheetAllocation
        fields = [
            "id",
            "destination_branch",
            "destination_branch_name",
            "destination_label",
            "quantity",
        ]

    def get_destination_label(self, obj):
        return destination_column_label(obj.destination_branch)


class ProductionSheetLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    category_name = serializers.CharField(
        source="product.category.name", read_only=True
    )
    allocations = ProductionSheetAllocationSerializer(many=True, read_only=True)
    total_quantity = serializers.SerializerMethodField()

    class Meta:
        model = ProductionSheetLine
        fields = [
            "id",
            "product",
            "product_name",
            "category_name",
            "allocations",
            "total_quantity",
        ]

    def get_total_quantity(self, obj):
        return obj.total_quantity


class ProductionSheetSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    created_by_name = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()
    line_count = serializers.IntegerField(read_only=True)
    produced_line_count = serializers.IntegerField(read_only=True)
    total_units = serializers.SerializerMethodField()
    destinations = serializers.SerializerMethodField()

    class Meta:
        model = ProductionSheet
        fields = [
            "id",
            "branch",
            "branch_name",
            "production_date",
            "status",
            "status_display",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
            "completed_at",
            "lines",
            "line_count",
            "produced_line_count",
            "total_units",
            "destinations",
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

    def get_lines(self, obj):
        request = self.context.get("request")
        # List views only need counts; full lines load on retrieve / mutations.
        if request and getattr(request, "parser_context", None):
            view = request.parser_context.get("view")
            if view and getattr(view, "action", None) == "list":
                return []
        lines = obj.lines.all()
        return ProductionSheetLineSerializer(lines, many=True).data

    def get_destinations(self, obj):
        destinations = production_destination_branches()
        preferred = ["Highlands qty", "Churchill", "Central stores"]

        def sort_key(branch):
            label = destination_column_label(branch)
            try:
                return (0, preferred.index(label), branch.name)
            except ValueError:
                return (1, branch.name)

        return [
            {
                "id": branch.id,
                "name": branch.name,
                "label": destination_column_label(branch),
                "branch_type": branch.branch_type,
            }
            for branch in sorted(destinations, key=sort_key)
        ]

    def get_total_units(self, obj):
        if self.context.get("request"):
            view = self.context["request"].parser_context.get("view")
            if view and getattr(view, "action", None) == "list":
                return None
        total = Decimal("0")
        for line in obj.lines.all():
            total += line.total_quantity
        return total


class ProductionSheetCreateSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True, branch_type=BranchType.BAKERY)
    )
    production_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def create(self, validated_data):
        notes = validated_data.pop("notes", "")
        request = self.context.get("request")
        created_by = request.user if request and request.user.is_authenticated else None
        try:
            sheet = create_production_sheet(
                created_by=created_by, **validated_data
            )
        except InvalidProductionBranchError as exc:
            raise serializers.ValidationError({"branch": str(exc)}) from exc
        if notes:
            sheet.notes = notes
            sheet.save(update_fields=["notes"])
        return sheet


class ProductionSheetAllocationUpdateSerializer(serializers.Serializer):
    destination_branch = serializers.IntegerField()
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )


class ProductionSheetLineUpdateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    allocations = ProductionSheetAllocationUpdateSerializer(many=True)


class ProductionSheetLinesUpdateSerializer(serializers.Serializer):
    lines = ProductionSheetLineUpdateSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("Provide at least one line to update.")
        return value

    def update(self, instance, validated_data):
        try:
            return update_production_sheet_lines(instance, validated_data["lines"])
        except InvalidProductionSheetStateError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
