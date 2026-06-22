from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from zimra_fiscal.exceptions import ZimraConfigurationError, ZimraSubmissionError
from zimra_fiscal.response import fiscal_receipt_summary

from accounts.branch_access import user_can_access_pos
from accounts.models import StaffProfile, StaffRole
from branches.serializers import BranchSerializer
from orders.serializers import OrderSerializer

from .serializers import SyncOrderPushSerializer
from .services import get_branch_catalog_payload, get_currencies_payload, import_client_order


class DesktopSyncPermissionMixin:
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def _cashier_branch(self, request):
        user = request.user
        if not user_can_access_pos(user):
            return None, Response(
                {"detail": "POS access is not allowed for this account."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            profile = user.staff_profile
        except StaffProfile.DoesNotExist:
            return None, Response(
                {"detail": "Staff profile required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if profile.role not in (StaffRole.CASHIER, StaffRole.BRANCH_MANAGER):
            return None, Response(
                {"detail": "Desktop POS is for cashiers only."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return profile.branch, None


class SyncPingView(DesktopSyncPermissionMixin, APIView):
    """Lightweight connectivity check for the desktop POS."""

    def get(self, request):
        branch, error = self._cashier_branch(request)
        if error:
            return error
        return Response({"ok": True, "branch_id": branch.id})


class SyncPullView(DesktopSyncPermissionMixin, APIView):
    """Pull catalog and config for offline POS."""

    def get(self, request):
        branch, error = self._cashier_branch(request)
        if error:
            return error

        catalog = get_branch_catalog_payload(branch)
        return Response(
            {
                "branch": BranchSerializer(branch).data,
                "categories": catalog["categories"],
                "products": catalog["products"],
                "currencies": get_currencies_payload(),
                "inclusive_tax_rate": str(settings.INCLUSIVE_TAX_RATE),
                "synced_at": timezone.now().isoformat(),
            }
        )


class SyncPushView(DesktopSyncPermissionMixin, APIView):
    """Push offline orders to the central server."""

    def post(self, request):
        branch, error = self._cashier_branch(request)
        if error:
            return error

        orders_payload = request.data.get("orders", [])
        if not isinstance(orders_payload, list):
            return Response(
                {"detail": '"orders" must be a list.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        for index, raw in enumerate(orders_payload):
            serializer = SyncOrderPushSerializer(data=raw)
            if not serializer.is_valid():
                return Response(
                    {"detail": f"Order {index}: {serializer.errors}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                order, already_synced, fiscal_receipt = import_client_order(
                    branch, serializer.validated_data, user=request.user
                )
            except (ZimraConfigurationError, ZimraSubmissionError) as exc:
                return Response(
                    {"detail": str(exc)},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            except ValueError as exc:
                return Response(
                    {"detail": str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            item = {
                "client_id": str(serializer.validated_data["client_id"]),
                "server_id": order.id,
                "status": order.status,
                "kitchen_status": order.kitchen_status,
                "receipt_number": order.receipt_number or None,
                "already_synced": already_synced,
            }
            if fiscal_receipt:
                item["fiscal_result"] = fiscal_receipt_summary(fiscal_receipt)
            results.append(item)

        return Response({"results": results})
