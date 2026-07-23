from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from audit.mixins import AuditedModelMixin

from .branch_access import user_can_manage_users
from .models import StaffRole
from .serializers import StaffUserSerializer

User = get_user_model()


class StaffUserViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    serializer_class = StaffUserSerializer
    audit_entity_type = "user"
    audit_fields = ("username", "email", "is_active")
    audit_label_field = "username"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not user_can_manage_users(request.user):
            raise PermissionDenied("You do not have permission to manage users.")

    def get_queryset(self):
        return (
            User.objects.filter(staff_profile__isnull=False)
            .select_related("staff_profile__branch")
            .order_by("username")
        )

    def get_audit_snapshot(self, instance):
        data = super().get_audit_snapshot(instance)
        profile = getattr(instance, "staff_profile", None)
        if profile is not None:
            data["branch"] = profile.branch_id
            data["role"] = profile.role
            data["pos_access"] = profile.pos_access
            data["kitchen_station"] = profile.kitchen_station
        data["password_changed"] = False
        return data

    def perform_update(self, serializer):
        instance = serializer.instance
        before = self.get_audit_snapshot(instance)
        password_provided = bool(
            getattr(self.request, "data", {}).get("password")
            if self.request is not None
            else False
        )
        super(AuditedModelMixin, self).perform_update(serializer)
        after = self.get_audit_snapshot(serializer.instance)
        if password_provided:
            after["password_changed"] = True
            before["password_changed"] = False
        self._record_update_audit(before, after, serializer.instance)

    def get_audit_branch(self, instance):
        profile = getattr(instance, "staff_profile", None)
        if profile is not None:
            return profile.branch
        return super().get_audit_branch(instance)

    @action(detail=False, methods=["get"])
    def roles(self, request):
        return Response(
            [{"value": value, "label": label} for value, label in StaffRole.choices]
        )

    @action(detail=False, methods=["get"])
    def roles(self, request):
        return Response(
            [{"value": value, "label": label} for value, label in StaffRole.choices]
        )
