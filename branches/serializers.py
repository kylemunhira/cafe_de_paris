from rest_framework import serializers

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
            "fiscalization_enabled",
            "zimra_device_id",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class DiningTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiningTable
        fields = ["id", "branch", "name", "sort_order", "is_active"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Table name is required.")
        if len(name) > 20:
            raise serializers.ValidationError("Table name must be 20 characters or fewer.")
        return name
