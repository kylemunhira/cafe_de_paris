from accounts.branch_access import (
    filter_by_branch_field,
    get_staff_branch_id,
    user_can_access_pos,
    user_can_manage_pos_orders,
)
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from orders.bill_reprint_serializers import BillReprintRequestSerializer
from orders.models import BillReprintRequest, BillReprintRequestStatus
from orders.services import (
    BillReprintRequestError,
    approve_bill_reprint_request,
    cancel_bill_reprint_request,
    reject_bill_reprint_request,
)


class BillReprintRequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = BillReprintRequestSerializer

    def get_queryset(self):
        qs = BillReprintRequest.objects.select_related(
            "order__branch",
            "requested_by",
            "approved_by",
        ).all()
        qs = filter_by_branch_field(qs, self.request.user, branch_field="order__branch")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if not user_can_manage_pos_orders(self.request.user):
            branch_id = get_staff_branch_id(self.request.user)
            if branch_id:
                qs = qs.filter(order__branch_id=branch_id)
            else:
                qs = qs.filter(requested_by=self.request.user)
        return qs

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if user_can_manage_pos_orders(request.user):
            pass
        elif instance.requested_by_id == request.user.id:
            pass
        elif (
            user_can_access_pos(request.user)
            and get_staff_branch_id(request.user) == instance.order.branch_id
        ):
            pass
        else:
            raise PermissionDenied("You may not view this bill reprint request.")
        serializer = self.getSerializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if not user_can_manage_pos_orders(request.user):
            raise PermissionDenied(
                "Manager or admin access is required to approve bill reprints."
            )
        instance = self.get_object()
        if instance.status != BillReprintRequestStatus.PENDING:
            return Response(
                {"detail": "This bill reprint request is no longer pending."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            approved, order = approve_bill_reprint_request(instance, request.user)
        except BillReprintRequestError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        data = BillReprintRequestSerializer(approved).data
        data["bill_print_count"] = order.bill_print_count
        return Response(data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        if not user_can_manage_pos_orders(request.user):
            raise PermissionDenied(
                "Manager or admin access is required to reject bill reprints."
            )
        instance = self.get_object()
        if instance.status != BillReprintRequestStatus.PENDING:
            return Response(
                {"detail": "This bill reprint request is no longer pending."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            rejected = reject_bill_reprint_request(instance, request.user)
        except BillReprintRequestError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BillReprintRequestSerializer(rejected).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required.")
        instance = self.get_object()
        try:
            cancelled = cancel_bill_reprint_request(instance, request.user)
        except BillReprintRequestError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BillReprintRequestSerializer(cancelled).data)
