from accounts.branch_access import (
    filter_by_branch_field,
    filter_by_branch_participation,
    get_staff_branch_id,
    user_can_access_bakery_transfers,
    user_can_access_stores_transfers,
    user_can_approve_delivery,
    user_can_manage_outgoing_delivery,
    user_can_receive_delivery,
)
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import BranchInventory, DeliveryNote, StockTake, StockTransfer
from branches.models import BranchType

from .serializers import (
    BAKERY_TRANSFER_DESTINATION_TYPES,
    BakeryDeliveryNoteCreateSerializer,
    BakeryTransferCreateSerializer,
    BranchInventorySerializer,
    DeliveryNoteSerializer,
    InventoryAdjustSerializer,
    STORES_TRANSFER_DESTINATION_TYPES,
    StoresDeliveryNoteCreateSerializer,
    StockTakeCreateSerializer,
    StockTakeLinesUpdateSerializer,
    StockTakeSerializer,
    StockTransferCreateSerializer,
    StockTransferSerializer,
)
from .services import (
    DuplicateStockTakeError,
    IncompleteStockTakeError,
    InsufficientStockError,
    InvalidDeliveryNoteStateError,
    InvalidStockTakeStateError,
    InvalidTransferStateError,
    adjust_inventory,
    approve_delivery_note,
    approve_transfer,
    cancel_delivery_note,
    cancel_stock_take,
    cancel_transfer,
    complete_stock_take,
    deliver_delivery_note,
    deliver_transfer,
    dispatch_delivery_note,
    dispatch_transfer,
    InvalidDeliveryNotePaymentError,
    mark_delivery_note_paid,
)


class BranchInventoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BranchInventory.objects.select_related("branch", "product").all()
    serializer_class = BranchInventorySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        branch_id = self.request.query_params.get("branch")
        product_id = self.request.query_params.get("product")
        category = self.request.query_params.get("category")
        low_stock = self.request.query_params.get("low_stock")

        queryset = filter_by_branch_field(
            queryset, self.request.user, requested_branch_id=branch_id
        )
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if category:
            queryset = queryset.filter(product__category__name=category)
        if low_stock and low_stock.lower() in ("1", "true", "yes"):
            try:
                threshold = Decimal(
                    self.request.query_params.get("threshold", "10")
                )
            except InvalidOperation:
                threshold = Decimal("10")
            queryset = queryset.filter(quantity__lte=threshold)
        return queryset

    @action(detail=False, methods=["post"])
    def adjust(self, request):
        serializer = InventoryAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            inventory = adjust_inventory(
                data["branch"],
                data["product"],
                data["delta"],
            )
        except InsufficientStockError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "available": str(exc.available),
                    "requested": str(exc.requested),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(BranchInventorySerializer(inventory).data)


class StockTransferViewSet(viewsets.ModelViewSet):
    queryset = StockTransfer.objects.select_related(
        "from_branch",
        "to_branch",
        "product",
    ).all()
    serializer_class = StockTransferSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return StockTransferCreateSerializer
        return StockTransferSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        branch_id = self.request.query_params.get("branch")
        bakery_only = self.request.query_params.get("bakery_only")

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        queryset = filter_by_branch_participation(
            queryset, self.request.user, requested_branch_id=branch_id
        )
        if bakery_only and bakery_only.lower() in ("1", "true", "yes"):
            queryset = queryset.filter(
                from_branch__branch_type=BranchType.BAKERY,
                to_branch__branch_type__in=BAKERY_TRANSFER_DESTINATION_TYPES,
            )
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transfer = serializer.save()
        return Response(
            StockTransferSerializer(transfer).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="from-bakery")
    def create_from_bakery(self, request):
        serializer = BakeryTransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transfer = serializer.save()
        return Response(
            StockTransferSerializer(transfer).data,
            status=status.HTTP_201_CREATED,
        )

    def _run_transition(self, request, pk, handler):
        transfer = self.get_object()
        try:
            transfer = handler(transfer)
        except InvalidTransferStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientStockError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "available": str(exc.available),
                    "requested": str(exc.requested),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(StockTransferSerializer(transfer).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._run_transition(request, pk, approve_transfer)

    @action(detail=True, methods=["post"], url_path="dispatch")
    def dispatch_stock(self, request, pk=None):
        return self._run_transition(request, pk, dispatch_transfer)

    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        return self._run_transition(request, pk, deliver_transfer)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._run_transition(request, pk, cancel_transfer)


class DeliveryNoteViewSet(viewsets.ModelViewSet):
    queryset = DeliveryNote.objects.select_related(
        "from_branch",
        "to_branch",
        "paid_by",
    ).prefetch_related("lines__product").all()
    serializer_class = DeliveryNoteSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        branch_id = self.request.query_params.get("branch")
        bakery_only = self.request.query_params.get("bakery_only")
        stores_only = self.request.query_params.get("stores_only")
        invoiced_only = self.request.query_params.get("invoiced_only")
        payment_status = self.request.query_params.get("payment_status")
        incoming = self.request.query_params.get("incoming")

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if incoming and incoming.lower() in ("1", "true", "yes"):
            staff_branch_id = get_staff_branch_id(self.request.user)
            if staff_branch_id is not None:
                queryset = queryset.filter(to_branch_id=staff_branch_id)
            else:
                queryset = filter_by_branch_participation(
                    queryset, self.request.user, requested_branch_id=branch_id
                )
        else:
            queryset = filter_by_branch_participation(
                queryset, self.request.user, requested_branch_id=branch_id
            )
        if bakery_only and bakery_only.lower() in ("1", "true", "yes"):
            queryset = queryset.filter(
                from_branch__branch_type=BranchType.BAKERY,
                to_branch__branch_type__in=BAKERY_TRANSFER_DESTINATION_TYPES,
            )
        if stores_only and stores_only.lower() in ("1", "true", "yes"):
            queryset = queryset.filter(
                from_branch__branch_type=BranchType.STORES,
                to_branch__branch_type__in=STORES_TRANSFER_DESTINATION_TYPES,
            )
        if invoiced_only and invoiced_only.lower() in ("1", "true", "yes"):
            queryset = queryset.exclude(invoice_number__isnull=True).exclude(
                invoice_number=""
            )
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        return queryset

    @action(detail=False, methods=["post"], url_path="from-stores")
    def create_from_stores(self, request):
        if not user_can_access_stores_transfers(request.user):
            raise PermissionDenied(
                "Only central stores staff or HQ admins can create delivery notes."
            )
        serializer = StoresDeliveryNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.save()
        note = self.get_queryset().get(pk=note.pk)
        return Response(
            DeliveryNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="from-bakery")
    def create_from_bakery(self, request):
        if not user_can_access_bakery_transfers(request.user):
            raise PermissionDenied(
                "Only central bakery staff or HQ admins can create delivery notes."
            )
        serializer = BakeryDeliveryNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.save()
        note = self.get_queryset().get(pk=note.pk)
        return Response(
            DeliveryNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )

    def _run_transition(
        self, request, pk, handler, outgoing=False, receiving=False, approval=False
    ):
        note = self.get_object()
        if approval and not user_can_approve_delivery(request.user, note):
            from_branch_type = note.from_branch.branch_type
            if from_branch_type == BranchType.BAKERY:
                detail = "Only central bakery or the receiving branch can approve this delivery."
            elif from_branch_type == BranchType.STORES:
                detail = "Only central stores or the receiving branch can approve this delivery."
            else:
                detail = "Only the sending or receiving branch can approve this delivery."
            raise PermissionDenied(detail)
        if outgoing and not user_can_manage_outgoing_delivery(request.user, note):
            from_branch_type = note.from_branch.branch_type
            if from_branch_type == BranchType.BAKERY:
                detail = "Only central bakery staff or HQ admins can manage outgoing deliveries."
            elif from_branch_type == BranchType.STORES:
                detail = "Only central stores staff or HQ admins can manage outgoing deliveries."
            else:
                detail = "Only the sending branch can manage outgoing deliveries."
            raise PermissionDenied(detail)
        if receiving and not user_can_receive_delivery(request.user, note):
            raise PermissionDenied(
                "Only the receiving branch can confirm receipt of this delivery."
            )
        try:
            note = handler(note)
        except InvalidDeliveryNoteStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientStockError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "available": str(exc.available),
                    "requested": str(exc.requested),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        note = self.get_queryset().get(pk=note.pk)
        return Response(DeliveryNoteSerializer(note).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._run_transition(
            request, pk, approve_delivery_note, approval=True
        )

    @action(detail=True, methods=["post"], url_path="dispatch")
    def dispatch_stock(self, request, pk=None):
        return self._run_transition(
            request, pk, dispatch_delivery_note, outgoing=True
        )

    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        return self._run_transition(
            request, pk, deliver_delivery_note, receiving=True
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._run_transition(
            request, pk, cancel_delivery_note, outgoing=True
        )

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        if not user_can_access_stores_transfers(request.user):
            raise PermissionDenied(
                "Only central stores staff or HQ admins can record transfer invoice payment."
            )
        note = self.get_object()
        try:
            note = mark_delivery_note_paid(note, request.user)
        except InvalidDeliveryNotePaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        note = self.get_queryset().get(pk=note.pk)
        return Response(DeliveryNoteSerializer(note).data)


class StockTakeViewSet(viewsets.ModelViewSet):
    queryset = StockTake.objects.select_related(
        "branch",
        "created_by",
    ).prefetch_related("lines__product__category").all()
    serializer_class = StockTakeSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return StockTakeCreateSerializer
        if self.action == "update_lines":
            return StockTakeLinesUpdateSerializer
        return StockTakeSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        branch_id = self.request.query_params.get("branch")
        stock_take_type = self.request.query_params.get("stock_take_type")
        status_filter = self.request.query_params.get("status")

        queryset = filter_by_branch_field(
            queryset, self.request.user, requested_branch_id=branch_id
        )
        if stock_take_type:
            queryset = queryset.filter(stock_take_type=stock_take_type)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            stock_take = serializer.save()
        except DuplicateStockTakeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        stock_take = self.get_queryset().get(pk=stock_take.pk)
        return Response(
            StockTakeSerializer(stock_take).data,
            status=status.HTTP_201_CREATED,
        )

    def _run_transition(self, request, pk, handler):
        stock_take = self.get_object()
        try:
            stock_take = handler(stock_take)
        except InvalidStockTakeStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except IncompleteStockTakeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DuplicateStockTakeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientStockError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "available": str(exc.available),
                    "requested": str(exc.requested),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        stock_take = self.get_queryset().get(pk=stock_take.pk)
        return Response(StockTakeSerializer(stock_take).data)

    @action(detail=True, methods=["patch"], url_path="lines")
    def update_lines(self, request, pk=None):
        stock_take = self.get_object()
        serializer = self.get_serializer(stock_take, data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            stock_take = serializer.save()
        except InvalidStockTakeStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        stock_take = self.get_queryset().get(pk=stock_take.pk)
        return Response(StockTakeSerializer(stock_take).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._run_transition(request, pk, complete_stock_take)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._run_transition(request, pk, cancel_stock_take)
