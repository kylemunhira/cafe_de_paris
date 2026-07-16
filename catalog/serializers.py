from rest_framework import serializers

from .models import MenuAddon, MenuAddonGroup, Product, ProductCategory, ProductMenuAddonGroup


class ProductCategorySerializer(serializers.ModelSerializer):
    pos_station_display = serializers.CharField(
        source="get_pos_station_display",
        read_only=True,
    )

    class Meta:
        model = ProductCategory
        fields = ["id", "name", "is_asset", "show_on_pos", "pos_station", "pos_station_display"]


class MenuAddonSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuAddon
        fields = [
            "id",
            "group",
            "name",
            "selling_price",
            "tax_rate",
            "sort_order",
            "is_active",
        ]
        extra_kwargs = {
            "group": {"required": True},
            "name": {"required": True},
            "selling_price": {"required": False},
            "tax_rate": {"required": False},
            "sort_order": {"required": False},
            "is_active": {"required": False},
        }

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Name is required.")
        return name

    def validate(self, attrs):
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        group = attrs.get("group")
        if group is None and self.instance is not None:
            group = self.instance.group
        if name and group:
            qs = MenuAddon.objects.filter(group=group, name=name)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": "An option with this name already exists in the group."}
                )
        return attrs


class MenuAddonGroupSerializer(serializers.ModelSerializer):
    addons = MenuAddonSerializer(many=True, read_only=True)

    class Meta:
        model = MenuAddonGroup
        fields = ["id", "name", "selection_type", "sort_order", "addons"]
        extra_kwargs = {
            "name": {"required": True},
            "selection_type": {"required": False},
            "sort_order": {"required": False},
        }

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Name is required.")
        return name


class ProductAddonGroupSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="group.id")
    name = serializers.CharField(source="group.name", read_only=True)
    selection_type = serializers.CharField(source="group.selection_type", read_only=True)
    addons = MenuAddonSerializer(source="group.addons", many=True, read_only=True)

    class Meta:
        model = ProductMenuAddonGroup
        fields = ["id", "name", "selection_type", "addons"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    unit_cost = serializers.SerializerMethodField()
    addon_groups = serializers.SerializerMethodField()
    addon_group_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )

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
            "fiscal_tax_code",
            "is_active",
            "daily_stock_take",
            "created_at",
            "addon_groups",
            "addon_group_ids",
        ]
        read_only_fields = ["created_at"]

    def get_unit_cost(self, obj):
        costs = self.context.get("unit_costs")
        if costs is not None:
            return costs.get(obj.id)
        from bakery.costing import product_unit_cost

        return product_unit_cost(obj)

    def get_addon_groups(self, obj):
        cache = getattr(obj, "_prefetched_objects_cache", None)
        if cache is not None and "addon_group_links" in cache:
            links = obj.addon_group_links.all()
        else:
            links = (
                ProductMenuAddonGroup.objects.filter(product=obj)
                .select_related("group")
                .prefetch_related("group__addons")
            )
        return ProductAddonGroupSerializer(links, many=True).data

    def _save_addon_groups(self, product, group_ids):
        group_ids = list(dict.fromkeys(group_ids or []))
        valid_ids = set(
            MenuAddonGroup.objects.filter(id__in=group_ids).values_list("id", flat=True)
        )
        ProductMenuAddonGroup.objects.filter(product=product).exclude(
            group_id__in=valid_ids
        ).delete()
        existing = set(
            ProductMenuAddonGroup.objects.filter(product=product).values_list(
                "group_id", flat=True
            )
        )
        for group_id in valid_ids:
            if group_id not in existing:
                ProductMenuAddonGroup.objects.create(product=product, group_id=group_id)

    def create(self, validated_data):
        group_ids = validated_data.pop("addon_group_ids", None)
        product = super().create(validated_data)
        if group_ids is not None:
            self._save_addon_groups(product, group_ids)
        return product

    def update(self, instance, validated_data):
        group_ids = validated_data.pop("addon_group_ids", None)
        product = super().update(instance, validated_data)
        if group_ids is not None:
            self._save_addon_groups(product, group_ids)
        return product
