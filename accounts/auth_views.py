from django.contrib.auth import authenticate, get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access_codes import (
    is_valid_access_code_format,
    normalize_access_code,
    resolve_order_taker,
    resolve_pos_override_authorizer,
)
from accounts.branch_access import (
    get_staff_branch_type,
    get_staff_kitchen_station,
    user_can_access_bakery_transfers,
    user_can_access_kitchen,
    user_can_access_pos,
    user_can_approve_fiscal_receipt,
    user_can_collect_payment,
    user_can_manage_dining_tables,
    user_can_manage_fiscal_day,
    user_can_manage_pos_orders,
    user_can_use_desktop_pos,
)
from accounts.models import StaffProfile
from branches.models import BranchType
from branches.serializers import BranchSerializer

User = get_user_model()


def _authenticate_request_user(request):
    """
    Authenticate via access_code or username+password.

    Returns (user, error_response). error_response is set on failure.
    """
    access_code = normalize_access_code(request.data.get("access_code"))
    if access_code:
        if not is_valid_access_code_format(access_code):
            return None, Response(
                {"detail": "Access code must be exactly 4 digits."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = authenticate(request, access_code=access_code)
        if user is None:
            return None, Response(
                {"detail": "Invalid access code."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return user, None

    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    if not username or not password:
        return None, Response(
            {"detail": "Username and password, or a 4-digit access code, are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return None, Response(
            {"detail": "Invalid username or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return user, None


def _inactive_response():
    return Response(
        {"detail": "This account is disabled."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _staff_user_payload(user, profile):
    kitchen_station = get_staff_kitchen_station(user)
    display_name = user.get_full_name() or user.username
    return {
        "id": user.id,
        "username": user.username,
        "display_name": display_name,
        "role": profile.role,
        "can_manage_fiscal_day": user_can_manage_fiscal_day(user),
        "can_approve_fiscal_receipt": user_can_approve_fiscal_receipt(user),
        "can_manage_dining_tables": user_can_manage_dining_tables(user),
        "can_collect_payment": user_can_collect_payment(user),
        "can_manage_pos_orders": user_can_manage_pos_orders(user),
        "is_superuser": user.is_superuser,
        "kitchen_station": kitchen_station or None,
        "kitchen_station_display": profile.get_kitchen_station_display()
        if kitchen_station
        else None,
    }


class DesktopLoginView(APIView):
    """Token login for the offline desktop POS (cashiers, waiters, and branch managers)."""

    permission_classes = [AllowAny]

    def post(self, request):
        user, error = _authenticate_request_user(request)
        if error is not None:
            return error
        if not user.is_active:
            return _inactive_response()
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

        if not user_can_use_desktop_pos(user):
            return Response(
                {"detail": "Desktop POS is for cashiers and waiters only."},
                status=status.HTTP_403_FORBIDDEN,
            )

        server_url = (request.data.get("server_url") or "").strip().rstrip("/")
        token, _ = Token.objects.get_or_create(user=user)

        return Response(
            {
                "token": token.key,
                "user": _staff_user_payload(user, profile),
                "branch": BranchSerializer(profile.branch).data,
                "server_url": server_url or None,
            }
        )


class MobileAppLoginView(APIView):
    """Token login for the Android app (kitchen display and/or POS)."""

    permission_classes = [AllowAny]

    def post(self, request):
        user, error = _authenticate_request_user(request)
        if error is not None:
            return error
        if not user.is_active:
            return _inactive_response()

        can_kitchen = user_can_access_kitchen(user)
        can_pos = user_can_access_pos(user)
        can_bakery = (
            get_staff_branch_type(user) == BranchType.BAKERY
            and user_can_access_bakery_transfers(user)
        )
        if not can_kitchen and not can_pos and not can_bakery:
            return Response(
                {"detail": "This account cannot use the mobile app."},
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

        return Response(
            {
                "token": token.key,
                "user": _staff_user_payload(user, profile),
                "branch": BranchSerializer(profile.branch).data,
                "can_access_kitchen": can_kitchen,
                "can_access_pos": can_pos,
                "can_access_bakery": can_bakery,
            }
        )


class KitchenLoginView(APIView):
    """Token login for the kitchen Android display (kitchen staff only)."""

    permission_classes = [AllowAny]

    def post(self, request):
        user, error = _authenticate_request_user(request)
        if error is not None:
            return error
        if not user.is_active:
            return _inactive_response()
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
        payload = _staff_user_payload(user, profile)
        # Kitchen login historically returned a smaller user object.
        kitchen_user = {
            "id": payload["id"],
            "username": payload["username"],
            "display_name": payload["display_name"],
            "role": payload["role"],
            "kitchen_station": payload["kitchen_station"],
            "kitchen_station_display": payload["kitchen_station_display"],
        }

        return Response(
            {
                "token": token.key,
                "user": kitchen_user,
                "branch": BranchSerializer(profile.branch).data,
            }
        )


class VerifyAccessCodeView(APIView):
    """Verify an access code for POS overrides or order attribution."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = normalize_access_code(request.data.get("access_code"))
        if not code:
            return Response(
                {"detail": "Access code is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        purpose = (request.data.get("purpose") or "override").strip().lower()
        try:
            if purpose == "order":
                authorizer = resolve_order_taker(code)
            else:
                authorizer = resolve_pos_override_authorizer(code)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        profile = authorizer.staff_profile
        return Response(
            {
                "valid": True,
                "user": {
                    "id": authorizer.id,
                    "username": authorizer.username,
                    "display_name": authorizer.get_full_name() or authorizer.username,
                    "role": profile.role,
                },
            }
        )
