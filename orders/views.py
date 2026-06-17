from accounts.branch_access import filter_by_branch_field, user_can_access_pos
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from zimra_fiscal.exceptions import ZimraConfigurationError, ZimraSubmissionError
from zimra_fiscal.response import fiscal_receipt_summary
from zimra_fiscal.services import create_fiscal_receipt_for_payment

from .models import Expense, Order, OrderStatus
from .serializers import (
    ExpenseCreateSerializer,
    ExpenseSerializer,
    OrderCreateSerializer,
    OrderPaySerializer,
    OrderSerializer,
)
from .services import (
    InvalidKitchenStateError,
    ReceiptNumberError,
    allocate_receipt_number,
    mark_order_ready,
    start_preparing_order,
)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related("branch", "payment_currency").prefetch_related(
        "items__product"
    ).all()
    serializer_class = OrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        kitchen_status = self.request.query_params.get("kitchen_status")
        branch = self.request.query_params.get("branch")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if kitchen_status:
            qs = qs.filter(kitchen_status=kitchen_status)
        return filter_by_branch_field(qs, self.request.user, requested_branch_id=branch)

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        order = self.get_object()
        if order.status == OrderStatus.CANCELLED:
            return Response(
                {"detail": "Cancelled orders cannot be paid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if order.status == OrderStatus.PAID:
            return Response(
                {"detail": "Order is already paid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OrderPaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        currency = serializer.validated_data["payment_currency"]

        rate = currency.get_current_rate()
        if rate is None:
            return Response(
                {
                    "detail": f'No exchange rate configured for "{currency.name}". '
                    "Add a rate under Payment & Rates → Rates."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .select_related("branch")
                .get(pk=order.pk)
            )
            try:
                receipt_number = allocate_receipt_number(order.branch)
            except ReceiptNumberError as exc:
                return Response(
                    {"detail": str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            order.payment_currency = currency
            order.exchange_rate = rate
            order.amount_paid = currency.convert_from_base(order.total_amount)
            order.status = OrderStatus.PAID
            order.receipt_number = receipt_number
            order.paid_at = timezone.now()
            order.save(
                update_fields=[
                    "payment_currency",
                    "exchange_rate",
                    "amount_paid",
                    "status",
                    "receipt_number",
                    "paid_at",
                ]
            )

            fiscal_receipt = None
            if order.branch.fiscalization_enabled:
                try:
                    fiscal_receipt = create_fiscal_receipt_for_payment(order)
                except (ZimraConfigurationError, ZimraSubmissionError) as exc:
                    transaction.set_rollback(True)
                    return Response(
                        {"detail": str(exc)},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

        response_data = OrderSerializer(order).data
        if fiscal_receipt:
            response_data["fiscal_receipt"] = fiscal_receipt.payload
            response_data["fiscal_result"] = fiscal_receipt_summary(fiscal_receipt)
            if fiscal_receipt.zimra_response is not None:
                response_data["fiscal_zimra_response"] = fiscal_receipt.zimra_response
        return Response(response_data)

    def _run_kitchen_action(self, request, pk, handler):
        order = self.get_object()
        if order.status != OrderStatus.OPEN:
            return Response(
                {"detail": "Only open orders can be updated in the kitchen."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            order = handler(order)
        except InvalidKitchenStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="start-preparing")
    def start_preparing(self, request, pk=None):
        return self._run_kitchen_action(request, pk, start_preparing_order)

    @action(detail=True, methods=["post"], url_path="mark-ready")
    def mark_ready(self, request, pk=None):
        return self._run_kitchen_action(request, pk, mark_order_ready)


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.select_related(
        "branch",
        "currency",
        "recorded_by",
    ).all()
    serializer_class = ExpenseSerializer
    http_method_names = ["get", "post", "head", "options"]

    def _require_pos_access(self):
        if not user_can_access_pos(self.request.user):
            raise PermissionDenied("POS access is required to manage expenses.")

    def get_queryset(self):
        self._require_pos_access()
        qs = super().get_queryset()
        branch = self.request.query_params.get("branch")
        expense_date = self.request.query_params.get("date")
        from_date = self.request.query_params.get("from")
        to_date = self.request.query_params.get("to")
        qs = filter_by_branch_field(qs, self.request.user, requested_branch_id=branch)
        if expense_date:
            qs = qs.filter(expense_date=expense_date)
        if from_date:
            qs = qs.filter(expense_date__gte=from_date)
        if to_date:
            qs = qs.filter(expense_date__lte=to_date)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return ExpenseCreateSerializer
        return ExpenseSerializer

    def create(self, request, *args, **kwargs):
        self._require_pos_access()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = serializer.save()
        return Response(
            ExpenseSerializer(expense).data,
            status=status.HTTP_201_CREATED,
        )
