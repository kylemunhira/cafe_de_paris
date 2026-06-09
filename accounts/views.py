from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .branch_access import user_can_manage_users
from .models import StaffRole
from .serializers import StaffUserSerializer

User = get_user_model()


class StaffUserViewSet(viewsets.ModelViewSet):
    serializer_class = StaffUserSerializer

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

    @action(detail=False, methods=["get"])
    def roles(self, request):
        return Response(
            [{"value": value, "label": label} for value, label in StaffRole.choices]
        )
