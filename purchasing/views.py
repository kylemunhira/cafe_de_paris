from django.http import HttpResponse
from accounts.branch_access import (
    filter_by_branch_field,
    user_can_approve_purchase_orders,
    user_can_create_purchase_orders,
    user_can_manage_suppliers,
    user_can_receive_purchase_order,
)
from audit.mixins import AuditedModelMixin
from audit.services import (
    action_for_update,
    diff_dicts,
    record_entity_change,
    serialize_value,
    snapshot_fields,
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
from .statement import build_supplier_statement_report
from .supplier_import import (
    export_suppliers_csv,
    import_suppliers_csv,
    import_suppliers_xlsx,
)


def _purchase_order_lines_snapshot(purchase_order):
    return [
        {
            "product": line.product_id,
            "quantity": serialize_value(line.quantity),
            "unit_cost": serialize_value(line.unit_cost),
        }
        for line in purchase_order.lines.all().order_by("id")
    ]


class SupplierViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    audit_entity_type = "supplier"
    audit_fields = (
        "name",
        "vat_number",
        "contact_person",
        "email",
        "phone",
        "address",
        "notes",
        "is_active",
    )
    audit_label_field = "name"
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
            before = self.get_audit_snapshot(supplier)
            supplier.is_active = False
            supplier.save(update_fields=["is_active"])
            after = self.get_audit_snapshot(supplier)
            changes = diff_dicts(before, after)
            if changes:
                record_entity_change(
                    action=action_for_update(before, after),
                    entity=supplier,
                    entity_type=self.audit_entity_type,
                    changes=changes,
                    actor=request.user,
                    request=request,
                )
            return Response(SupplierSerializer(supplier).data)
        self._record_delete_audit(supplier)
        supplier.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="export-csv")
    def export_csv(self, request):
        self._require_supplier_manager()
        response = HttpResponse(export_suppliers_csv(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="suppliers.csv"'
        return response

    @action(detail=False, methods=["post"], url_path="import-csv")
    def import_csv(self, request):
        self._require_supplier_manager()
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "No file uploaded. Use form field name 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload.name.lower().endswith(".csv"):
            return Response(
                {"detail": "Only .csv files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = import_suppliers_csv(upload)
        if result["errors"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="import-xlsx")
    def import_xlsx(self, request):
        self._require_supplier_manager()
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "No file uploaded. Use form field name 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload.name.lower().endswith((".xlsx", ".xlsm")):
            return Response(
                {"detail": "Only .xlsx workbooks are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = import_suppliers_xlsx(upload)
        if result["errors"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)

    def _can_view_supplier_purchases(self):
        return user_can_create_purchase_orders(
            self.request.user
        ) or user_can_manage_suppliers(self.request.user)

    @action(detail=True, methods=["get"])
    def statement(self, request, pk=None):
        if not self._can_view_supplier_purchases():
            raise PermissionDenied("You do not have permission to view supplier purchases.")

        supplier = self.get_object()
        try:
            all_time = request.query_params.get("all") == "1"
            data = build_supplier_statement_report(
                supplier,
                from_date=request.query_params.get("from"),
                to_date=request.query_params.get("to"),
                branch_id=request.query_params.get("branch"),
                all_time=all_time,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        purchases = data.pop("purchases")
        data["purchases"] = PurchaseOrderSerializer(purchases, many=True).data
        data["supplier"] = SupplierSerializer(supplier).data
        return Response(data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """All-time purchase history for a supplier."""
        if not self._can_view_supplier_purchases():
            raise PermissionDenied("You do not have permission to view supplier purchases.")

        supplier = self.get_object()
        try:
            data = build_supplier_statement_report(
                supplier,
                branch_id=request.query_params.get("branch"),
                all_time=True,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        purchases = data.pop("purchases")
        data["purchases"] = PurchaseOrderSerializer(purchases, many=True).data
        data["supplier"] = SupplierSerializer(supplier).data
        return Response(data)


class PurchaseOrderViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related(
        "branch",
        "supplier",
        "created_by",
    ).prefetch_related("lines__product").all()
    serializer_class = PurchaseOrderSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    audit_entity_type = "purchase_order"
    audit_fields = ("supplier", "notes", "status")
    audit_label_field = lambda po: f"PO #{po.pk}"  # noqa: E731

    def get_audit_snapshot(self, instance):
        data = super().get_audit_snapshot(instance)
        data["lines"] = _purchase_order_lines_snapshot(instance)
        return data

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
                "Only HQ admins and central stores staff can record purchases."
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
        before = self.get_audit_snapshot(purchase_order)
        serializer = self.get_serializer(purchase_order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        purchase_order = serializer.save()
        purchase_order = self.get_queryset().get(pk=purchase_order.pk)
        after = self.get_audit_snapshot(purchase_order)
        self._record_update_audit(before, after, purchase_order)
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
