from decimal import Decimal

from rest_framework import serializers

from catalog.models import Product

from .models import Recipe


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

        if product and not product.is_active:
            raise serializers.ValidationError(
                {"product": "Cannot use an inactive product as recipe output."}
            )
        if ingredient and not ingredient.is_active:
            raise serializers.ValidationError(
                {"ingredient": "Cannot use an inactive product as an ingredient."}
            )

        return attrs
