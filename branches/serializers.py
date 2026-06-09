from rest_framework import serializers

from .models import Branch


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
