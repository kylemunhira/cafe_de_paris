from accounts.branch_access import (
    filter_by_branch_field,
    user_can_approve_purchase_orders,
    user_can_create_purchase_orders,
    user_can_manage_suppliers,
    user_can_receive_purchase_order,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import PurchaseOrder, Supplier
from .serializers import (
    PurchaseOrderCreateSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderUpdateSerializer,
    SupplierSerializer,
)
from .services import (
    InvalidPurchaseOrderStateError,
    approve_purchase_order,
    cancel_purchase_order,
    receive_purchase_order,
    submit_purchase_order,
)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        active_only = self.request.query_params.get("active_only")
        if active_only and active_only.lower() in ("1", "true", "yes"):
            queryset = queryset.filter(is_active=True)
        return queryset

    def _require_supplier_manager(self):
        if not user_can_manage_suppliers(self.request.user):
            raise PermissionDenied("Only HQ admins can manage suppliers.")

    def create(self, request, *args, **kwargs):
        self._require_supplier_manager()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._require_supplier_manager()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._require_supplier_manager()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._require_supplier_manager()
        supplier = self.get_object()
        if supplier.purchase_orders.exists():
            supplier.is_active = False
            supplier.save(update_fields=["is_active"])
            return Response(SupplierSerializer(supplier).data)
        supplier.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related(
        "branch",
        "supplier",
        "created_by",
    ).prefetch_related("lines__product").all()
    serializer_class = PurchaseOrderSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return PurchaseOrderCreateSerializer
        if self.action in ("partial_update", "update"):
            return PurchaseOrderUpdateSerializer
        return PurchaseOrderSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        branch_id = self.request.query_params.get("branch")
        supplier_id = self.request.query_params.get("supplier")

        queryset = filter_by_branch_field(
            queryset, self.request.user, requested_branch_id=branch_id
        )
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        return queryset

    def create(self, request, *args, **kwargs):
        if not user_can_create_purchase_orders(request.user):
            raise PermissionDenied(
                "Only branch managers and HQ admins can record purchases."
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        purchase_order = serializer.save()
        purchase_order = self.get_queryset().get(pk=purchase_order.pk)
        return Response(
            PurchaseOrderSerializer(purchase_order).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        purchase_order = self.get_object()
        serializer = self.get_serializer(purchase_order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        purchase_order = serializer.save()
        purchase_order = self.get_queryset().get(pk=purchase_order.pk)
        return Response(PurchaseOrderSerializer(purchase_order).data)

    def _run_transition(self, request, pk, handler, *, require_approve=False, require_receive=False):
        purchase_order = self.get_object()
        if require_approve and not user_can_approve_purchase_orders(request.user):
            raise PermissionDenied("Only HQ admins can approve purchase orders.")
        if require_receive and not user_can_receive_purchase_order(
            request.user, purchase_order
        ):
            raise PermissionDenied(
                "Only staff at the receiving branch can confirm receipt."
            )
        try:
            purchase_order = handler(purchase_order)
        except InvalidPurchaseOrderStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        purchase_order = self.get_queryset().get(pk=purchase_order.pk)
        return Response(PurchaseOrderSerializer(purchase_order).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._run_transition(request, pk, submit_purchase_order)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._run_transition(
            request, pk, approve_purchase_order, require_approve=True
        )

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        return self._run_transition(
            request, pk, receive_purchase_order, require_receive=True
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._run_transition(request, pk, cancel_purchase_order)
