from rest_framework import serializers

from catalog.constants import ALL_INGREDIENT_CATEGORIES

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


class PosMenuAddonSerializer(serializers.ModelSerializer):
    """Lean addon payload for Android POS (omit tax/sort fields)."""

    class Meta:
        model = MenuAddon
        fields = ["id", "name", "selling_price", "is_active"]


class PosProductAddonGroupSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="group.id")
    name = serializers.CharField(source="group.name", read_only=True)
    selection_type = serializers.CharField(source="group.selection_type", read_only=True)
    addons = PosMenuAddonSerializer(source="group.addons", many=True, read_only=True)

    class Meta:
        model = ProductMenuAddonGroup
        fields = ["id", "name", "selection_type", "addons"]


class PosProductSerializer(serializers.ModelSerializer):
    """Minimal product shape for Android POS catalog downloads."""

    category_name = serializers.CharField(source="category.name", read_only=True)
    addon_groups = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "selling_price",
            "addon_groups",
        ]

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
        return PosProductAddonGroupSerializer(links, many=True).data


class ProductBranchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    group_category_name = serializers.CharField(
        source="group_category.name",
        read_only=True,
        allow_null=True,
    )
    unit_cost = serializers.SerializerMethodField()
    addon_groups = serializers.SerializerMethodField()
    addon_group_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )
    branches = serializers.SerializerMethodField()
    branch_ids = serializers.ListField(
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
            "group_category",
            "group_category_name",
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
            "branches",
            "branch_ids",
        ]
        read_only_fields = ["created_at"]
        extra_kwargs = {
            "group_category": {"required": False, "allow_null": True},
        }

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Name is required.")
        return name

    @staticmethod
    def _category_is_ingredient(category):
        if category is None:
            return False
        return getattr(category, "name", None) in ALL_INGREDIENT_CATEGORIES

    @classmethod
    def _duplicate_name_error(cls, conflicts):
        conflict = conflicts[0]
        category_name = conflict.category.name if conflict.category_id else "Unknown"
        group = getattr(conflict, "group_category", None)
        if group is not None:
            category_name = f"{category_name} / {group.name}"
        return (
            f'A product named "{conflict.name}" is already active under '
            f"{category_name} (id={conflict.id}). "
            "Deactivate or rename that product first."
        )

    def validate(self, attrs):
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        is_active = attrs.get("is_active")
        if is_active is None:
            is_active = True if self.instance is None else self.instance.is_active

        category = attrs.get("category")
        if category is None and self.instance is not None:
            category = self.instance.category

        if "group_category" in attrs:
            group_category = attrs.get("group_category")
        elif self.instance is not None:
            group_category = self.instance.group_category
        else:
            group_category = None

        # Active product names must be unique within a category.
        # Ingredients also key uniqueness on group_category (the Category
        # shown on the ingredients screen), so "Coke" under BARISTA does
        # not clash with "Coke" under another group or with no group.
        creating = self.instance is None
        name_changing = False
        if self.instance is not None and "name" in attrs:
            name_changing = (attrs["name"] or "").casefold() != (self.instance.name or "").casefold()
        category_changing = (
            self.instance is not None
            and "category" in attrs
            and attrs["category"] is not None
            and attrs["category"].pk != self.instance.category_id
        )
        group_changing = False
        if self.instance is not None and "group_category" in attrs:
            new_group_id = attrs["group_category"].pk if attrs["group_category"] else None
            group_changing = new_group_id != self.instance.group_category_id
        activating = (
            self.instance is not None
            and "is_active" in attrs
            and bool(attrs["is_active"])
            and not self.instance.is_active
        )
        should_check_unique = (
            creating or name_changing or category_changing or group_changing or activating
        )

        if name and is_active and should_check_unique and category is not None:
            qs = (
                Product.objects.filter(
                    name__iexact=name,
                    category=category,
                    is_active=True,
                )
                .select_related("category", "group_category")
                .order_by("id")
            )
            if self._category_is_ingredient(category):
                qs = qs.filter(group_category=group_category)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            conflicts = list(qs)
            if conflicts:
                raise serializers.ValidationError(
                    {"name": self._duplicate_name_error(conflicts)}
                )
        return attrs

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

    def get_branches(self, obj):
        cache = getattr(obj, "_prefetched_objects_cache", None)
        if cache is not None and "available_at_branches" in cache:
            branch_rows = obj.available_at_branches.all()
        else:
            branch_rows = obj.available_at_branches.filter(is_active=True).order_by("name")
        return ProductBranchSerializer(
            [{"id": branch.id, "name": branch.name} for branch in branch_rows],
            many=True,
        ).data

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

    def _save_branch_availability(self, product, branch_ids):
        if branch_ids is None:
            return
        from branches.models import Branch

        if not branch_ids:
            product.available_at_branches.clear()
            return
        valid_ids = list(
            Branch.objects.filter(id__in=branch_ids, is_active=True)
            .values_list("id", flat=True)
        )
        product.available_at_branches.set(valid_ids)

    def create(self, validated_data):
        group_ids = validated_data.pop("addon_group_ids", None)
        branch_ids = validated_data.pop("branch_ids", None)
        name = validated_data["name"]
        category = validated_data.get("category")
        group_category = validated_data.get("group_category")
        inactive_qs = Product.objects.filter(name__iexact=name, is_active=False)
        # Only revive an inactive row in the same category so creating
        # Soft Drinks "Coke" does not overwrite Ingredients "Coke".
        if category is not None:
            inactive_qs = inactive_qs.filter(category=category)
        if self._category_is_ingredient(category):
            inactive_qs = inactive_qs.filter(group_category=group_category)
        inactive = inactive_qs.order_by("id").first()
        if inactive:
            for attr, value in validated_data.items():
                setattr(inactive, attr, value)
            inactive.is_active = validated_data.get("is_active", True)
            inactive.save()
            product = inactive
        else:
            product = super().create(validated_data)
        if group_ids is not None:
            self._save_addon_groups(product, group_ids)
        if branch_ids is not None:
            self._save_branch_availability(product, branch_ids)
        return product

    def update(self, instance, validated_data):
        group_ids = validated_data.pop("addon_group_ids", None)
        branch_ids = validated_data.pop("branch_ids", None)
        product = super().update(instance, validated_data)
        if group_ids is not None:
            self._save_addon_groups(product, group_ids)
        if branch_ids is not None:
            self._save_branch_availability(product, branch_ids)
        return product
