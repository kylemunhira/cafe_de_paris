from django.contrib.auth import authenticate, get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.branch_access import user_can_access_kitchen, user_can_access_pos, user_can_manage_dining_tables, user_can_manage_fiscal_day
from accounts.models import StaffProfile, StaffRole
from branches.serializers import BranchSerializer

User = get_user_model()


class DesktopLoginView(APIView):
    """Token login for the offline desktop POS (cashiers only)."""

    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        server_url = (request.data.get("server_url") or "").strip().rstrip("/")

        if not username or not password:
            return Response(
                {"detail": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {"detail": "This account is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not user_can_access_pos(user):
            return Response(
                {"detail": "POS access is not allowed for this account."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            profile = user.staff_profile
        except StaffProfile.DoesNotExist:
            return Response(
                {"detail": "Staff profile required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if profile.role not in (StaffRole.CASHIER, StaffRole.BRANCH_MANAGER):
            return Response(
                {"detail": "Desktop POS is for cashiers only."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)
        display_name = user.get_full_name() or user.username

        return Response(
            {
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "display_name": display_name,
                    "role": profile.role,
                    "can_manage_fiscal_day": user_can_manage_fiscal_day(user),
                    "can_manage_dining_tables": user_can_manage_dining_tables(user),
                },
                "branch": BranchSerializer(profile.branch).data,
                "server_url": server_url or None,
            }
        )


class KitchenLoginView(APIView):
    """Token login for the kitchen Android display (kitchen staff only)."""

    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""

        if not username or not password:
            return Response(
                {"detail": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {"detail": "This account is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not user_can_access_kitchen(user):
            return Response(
                {"detail": "Kitchen access is not allowed for this account."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            profile = user.staff_profile
        except StaffProfile.DoesNotExist:
            return Response(
                {"detail": "Staff profile required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)
        display_name = user.get_full_name() or user.username

        return Response(
            {
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "display_name": display_name,
                    "role": profile.role,
                },
                "branch": BranchSerializer(profile.branch).data,
            }
        )
