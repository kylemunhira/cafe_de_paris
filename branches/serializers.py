from rest_framework import serializers

from orders.serializers import staff_display_name

from .models import Branch, DiningTable


class BranchSerializer(serializers.ModelSerializer):
    def validate_code(self, value):
        if not value:
            return ""
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise serializers.ValidationError(
                "Receipt code must be exactly 3 letters (e.g. HIG, CHU)."
            )
        return code

    class Meta:
        model = Branch
        fields = [
            "id",
            "name",
            "code",
            "location",
            "branch_type",
            "is_active",
            "allow_negative_stock",
            "fiscalization_enabled",
            "zimra_device_id",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class DiningTableSerializer(serializers.ModelSerializer):
    is_occupied = serializers.SerializerMethodField()
    occupied_by = serializers.SerializerMethodField()
    occupied_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DiningTable
        fields = [
            "id",
            "branch",
            "name",
            "sort_order",
            "is_active",
            "is_occupied",
            "occupied_by",
            "occupied_by_name",
        ]
        read_only_fields = ["id", "is_occupied", "occupied_by", "occupied_by_name"]

    def _occupancy_order(self, obj):
        occupancy = self.context.get("table_occupancy") or {}
        return occupancy.get(obj.name)

    def get_is_occupied(self, obj):
        return self._occupancy_order(obj) is not None

    def get_occupied_by(self, obj):
        order = self._occupancy_order(obj)
        return order.created_by_id if order else None

    def get_occupied_by_name(self, obj):
        order = self._occupancy_order(obj)
        if not order:
            return None
        return staff_display_name(order.created_by)

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Table name is required.")
        if len(name) > 20:
            raise serializers.ValidationError("Table name must be 20 characters or fewer.")
        return name
