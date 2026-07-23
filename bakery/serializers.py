from decimal import Decimal

from rest_framework import serializers

from branches.models import Branch, BranchType
from catalog.constants import is_bakery_transfer_product
from catalog.models import Product

from .models import ProductionOrder, Recipe
from .services import (
    InsufficientIngredientsError,
    InvalidProductionBranchError,
    InvalidProductionProductError,
    NoRecipeError,
    complete_production,
)


class RecipeSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    product_category = serializers.CharField(
        source="product.category.name",
        read_only=True,
    )
    ingredient_category = serializers.CharField(
        source="ingredient.category.name",
        read_only=True,
    )
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
            "ingredient",
            "ingredient_name",
            "ingredient_category",
            "quantity_required",
            "ingredient_unit_cost",
            "line_cost",
        ]

    def get_line_cost(self, obj):
        return (obj.quantity_required * obj.ingredient.selling_price).quantize(
            Decimal("0.01")
        )

    def validate_quantity_required(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate(self, attrs):
        product = attrs.get("product") or getattr(self.instance, "product", None)
        ingredient = attrs.get("ingredient") or getattr(self.instance, "ingredient", None)

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
        if creating or "ingredient" in attrs:
            if ingredient and not ingredient.is_active:
                raise serializers.ValidationError(
                    {"ingredient": "Cannot use an inactive product as an ingredient."}
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
