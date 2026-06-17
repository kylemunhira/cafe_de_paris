from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from branches.models import Branch, BranchType

from .models import StaffProfile, StaffRole

User = get_user_model()


class StaffUserSerializer(serializers.ModelSerializer):
    branch = serializers.PrimaryKeyRelatedField(
        source="staff_profile.branch",
        queryset=Branch.objects.filter(is_active=True),
    )
    branch_name = serializers.CharField(
        source="staff_profile.branch.name",
        read_only=True,
    )
    role = serializers.ChoiceField(
        source="staff_profile.role",
        choices=StaffRole.choices,
        default=StaffRole.CASHIER,
    )
    role_display = serializers.CharField(
        source="staff_profile.get_role_display",
        read_only=True,
    )
    pos_access = serializers.BooleanField(
        source="staff_profile.pos_access",
        required=False,
    )
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "branch",
            "branch_name",
            "role",
            "role_display",
            "pos_access",
            "is_active",
            "date_joined",
            "password",
        ]
        read_only_fields = ["id", "date_joined", "branch_name", "role_display"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.fields["password"].required = False

    def validate_username(self, value):
        queryset = User.objects.filter(username__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        profile_data = validated_data.pop("staff_profile")
        branch = profile_data["branch"]
        role = profile_data.get("role", StaffRole.CASHIER)
        pos_access = profile_data.get("pos_access")
        if pos_access is None:
            pos_access = branch.branch_type == BranchType.BRANCH
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        StaffProfile.objects.create(
            user=user,
            branch=branch,
            role=role,
            pos_access=pos_access,
        )
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_data = validated_data.pop("staff_profile", {})
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()

        profile = instance.staff_profile
        if "branch" in profile_data:
            profile.branch = profile_data["branch"]
        if "role" in profile_data:
            profile.role = profile_data["role"]
        if "pos_access" in profile_data:
            profile.pos_access = profile_data["pos_access"]
        profile.save()
        return instance
