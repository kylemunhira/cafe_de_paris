from accounts.branch_access import (
    filter_by_branch_field,
    user_can_access_pos,
    user_can_approve_fiscal_receipt,
    user_can_collect_payment,
)
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from zimra_fiscal.exceptions import ZimraConfigurationError, ZimraSubmissionError
from zimra_fiscal.response import fiscal_receipt_summary
from zimra_fiscal.services import approve_fiscal_receipt_for_order

from customers.services import (
    CustomerAccountError,
    InsufficientAccountBalance,
    pay_order_from_account,
)

from inventory.services import InsufficientOrderMaterialsError, consume_order_recipe_materials

from .kitchen_station import filter_orders_for_kitchen_station, resolve_kitchen_station_filter
from .models import Expense, FiscalApprovalStatus, Order, OrderStatus, PaymentMethod, TenderMethod
from .serializers import (
    ExpenseCreateSerializer,
    ExpenseSerializer,
    OrderCreateSerializer,
    OrderPaySerializer,
    OrderSerializer,
    OrderUpdateSerializer,
)
from .services import (
    InvalidKitchenStateError,
    OrderCancelError,
    PaymentValidationError,
    ReceiptNumberError,
    allocate_receipt_number,
    cancel_order,
    consolidate_table_orders,
    mark_order_paid_with_tenders,
    mark_order_ready,
    start_preparing_order,
    void_order,
)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related(
        "branch",
        "customer",
        "payment_currency",
        "created_by",
        "paid_by",
        "cancelled_by",
    ).prefetch_related(
        "items__product__category",
        "payments__currency",
        "fiscal_receipt",
    ).all()
    serializer_class = OrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        kitchen_status = self.request.query_params.get("kitchen_status")
        fiscal_approval_status = self.request.query_params.get("fiscal_approval_status")
        fiscal_only = self.request.query_params.get("fiscal_only")
        branch = self.request.query_params.get("branch")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if kitchen_status:
            qs = qs.filter(kitchen_status=kitchen_status)
        if fiscal_approval_status:
            qs = qs.filter(fiscal_approval_status=fiscal_approval_status)
        if fiscal_only in ("1", "true", "yes"):
            qs = qs.filter(branch__fiscalization_enabled=True)
        qs = filter_by_branch_field(qs, self.request.user, requested_branch_id=branch)
        station = resolve_kitchen_station_filter(
            self.request.user,
            self.request.query_params.get("pos_station"),
        )
        return filter_orders_for_kitchen_station(qs, station)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["kitchen_station"] = resolve_kitchen_station_filter(
            self.request.user,
            self.request.query_params.get("pos_station"),
        )
        return context

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        if self.action in ("update", "partial_update"):
            return OrderUpdateSerializer
        return OrderSerializer

    def partial_update(self, request, *args, **kwargs):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required to update orders.")
        return super().partial_update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required to create orders.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        if not user_can_collect_payment(request.user):
            raise PermissionDenied("This account cannot collect payment.")
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
        payment_method = serializer.validated_data.get("payment_method", PaymentMethod.CASH)

        if payment_method == PaymentMethod.ACCOUNT:
            try:
                with transaction.atomic():
                    order = (
                        Order.objects.select_for_update()
                        .select_related("branch")
                        .get(pk=order.pk)
                    )
                    order = consolidate_table_orders(order)
                    pay_order_from_account(order=order, recorded_by=request.user)
            except InsufficientAccountBalance as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except CustomerAccountError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            order.refresh_from_db()
            return Response(OrderSerializer(order).data)

        currency = serializer.validated_data.get("payment_currency")
        payment_lines = serializer.validated_data.get("payments")

        if payment_lines:
            for line in payment_lines:
                if line["currency"].get_current_rate() is None:
                    return Response(
                        {
                            "detail": f'No exchange rate configured for "{line["currency"].name}". '
                            "Add a rate under Payment & Rates → Rates."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            if currency is None:
                return Response(
                    {"currency_id": ["This field is required for cash payments."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
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
            order = consolidate_table_orders(order)
            try:
                receipt_number = allocate_receipt_number(order.branch)
            except ReceiptNumberError as exc:
                return Response(
                    {"detail": str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                consume_order_recipe_materials(order)
            except InsufficientOrderMaterialsError as exc:
                return Response(
                    {
                        "detail": str(exc),
                        "shortages": [
                            {
                                "ingredient_id": item.ingredient.id,
                                "ingredient_name": item.ingredient.name,
                                "required": str(item.required),
                                "available": str(item.available),
                            }
                            for item in exc.shortages
                        ],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not payment_lines:
                payment_lines = [
                    {
                        "currency": currency,
                        "amount": currency.convert_from_base(order.total_amount),
                        "method": (
                            payment_method
                            if payment_method in TenderMethod.values
                            else TenderMethod.CASH
                        ),
                    }
                ]

            try:
                mark_order_paid_with_tenders(
                    order,
                    payment_lines=payment_lines,
                    receipt_number=receipt_number,
                    paid_by=request.user,
                )
            except PaymentValidationError as exc:
                return Response(
                    {"detail": str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        order = (
            Order.objects.select_related(
                "branch",
                "customer",
                "payment_currency",
                "created_by",
                "paid_by",
            )
            .prefetch_related("items__product", "payments__currency", "fiscal_receipt")
            .get(pk=order.pk)
        )
        response_data = OrderSerializer(order).data
        return Response(response_data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required to cancel orders.")
        order = self.get_object()
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=order.pk)
                order = cancel_order(order, cancelled_by=request.user)
        except OrderCancelError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        order = (
            Order.objects.select_related(
                "branch",
                "customer",
                "payment_currency",
                "created_by",
                "paid_by",
                "cancelled_by",
            )
            .prefetch_related("items__product", "payments__currency", "fiscal_receipt")
            .get(pk=order.pk)
        )
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required to void orders.")
        order = self.get_object()
        try:
            with transaction.atomic():
                order = (
                    Order.objects.select_for_update()
                    .select_related("branch")
                    .get(pk=order.pk)
                )
                order = void_order(order, voided_by=request.user)
        except OrderCancelError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        order = (
            Order.objects.select_related(
                "branch",
                "customer",
                "payment_currency",
                "created_by",
                "paid_by",
                "cancelled_by",
            )
            .prefetch_related("items__product", "payments__currency", "fiscal_receipt")
            .get(pk=order.pk)
        )
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="approve-fiscal")
    def approve_fiscal(self, request, pk=None):
        if not user_can_approve_fiscal_receipt(request.user):
            raise PermissionDenied(
                "Branch manager or HQ admin access is required to approve fiscal receipts."
            )

        order = self.get_object()
        if order.status != OrderStatus.PAID:
            return Response(
                {"detail": "Only paid orders can be fiscalized."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not order.branch.fiscalization_enabled:
            return Response(
                {"detail": "This branch is not configured for fiscalization."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if order.fiscal_approval_status != FiscalApprovalStatus.PENDING:
            return Response(
                {"detail": "This order is not awaiting fiscal approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                order = (
                    Order.objects.select_for_update()
                    .select_related("branch")
                    .get(pk=order.pk)
                )
                fiscal_receipt = approve_fiscal_receipt_for_order(
                    order,
                    approved_by=request.user,
                )
        except (ZimraConfigurationError, ZimraSubmissionError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        order.refresh_from_db()
        response_data = OrderSerializer(order).data
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
        "supplier",
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
