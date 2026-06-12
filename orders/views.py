from accounts.branch_access import filter_by_branch_field
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from zimra_fiscal.exceptions import ZimraConfigurationError, ZimraSubmissionError
from zimra_fiscal.response import fiscal_receipt_summary
from zimra_fiscal.services import create_fiscal_receipt_for_payment

from .models import Order, OrderStatus
from .serializers import OrderCreateSerializer, OrderPaySerializer, OrderSerializer
from .services import ReceiptNumberError, allocate_receipt_number


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related("branch", "payment_currency").prefetch_related(
        "items__product"
    ).all()
    serializer_class = OrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        branch = self.request.query_params.get("branch")
        if status_filter:
            qs = qs.filter(status=status_filter)
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
