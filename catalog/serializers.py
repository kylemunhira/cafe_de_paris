from rest_framework import serializers

from .models import Product, ProductCategory


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name", "is_asset"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    unit_cost = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "selling_price",
            "unit_cost",
            "remaining_qty",
            "tax_rate",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_unit_cost(self, obj):
        costs = self.context.get("unit_costs")
        if costs is not None:
            return costs.get(obj.id)
        from bakery.costing import product_unit_cost

        return product_unit_cost(obj)
