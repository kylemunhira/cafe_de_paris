from accounts.branch_access import user_can_access_pos, user_can_collect_payment
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Customer, CustomerAccountTransaction
from .serializers import (
    CustomerAccountTransactionSerializer,
    CustomerDepositSerializer,
    CustomerSerializer,
)
from .services import CustomerAccountError, deposit_to_account
from .statement import build_customer_statement_report


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def _require_customer_access(self):
        if not user_can_access_pos(self.request.user):
            raise PermissionDenied("Only POS staff can manage customers.")

    def create(self, request, *args, **kwargs):
        self._require_customer_access()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._require_customer_access()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._require_customer_access()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._require_customer_access()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="transactions")
    def transactions(self, request, pk=None):
        customer = self.get_object()
        qs = CustomerAccountTransaction.objects.filter(customer=customer).select_related(
            "branch",
            "currency",
            "order",
            "recorded_by",
        )
        branch = request.query_params.get("branch")
        if branch:
            qs = qs.filter(branch_id=branch)
        serializer = CustomerAccountTransactionSerializer(qs[:200], many=True)
        return Response(
            {
                "account_balance": customer.account_balance,
                "transactions": serializer.data,
            }
        )

    @action(detail=True, methods=["get"])
    def statement(self, request, pk=None):
        customer = self.get_object()
        try:
            all_time = request.query_params.get("all") == "1"
            data = build_customer_statement_report(
                customer,
                from_date=request.query_params.get("from"),
                to_date=request.query_params.get("to"),
                branch_id=request.query_params.get("branch"),
                all_time=all_time,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        transactions = data.pop("transactions")
        data["transactions"] = CustomerAccountTransactionSerializer(
            transactions, many=True
        ).data
        return Response(data)

    @action(detail=True, methods=["post"])
    def deposit(self, request, pk=None):
        if not user_can_collect_payment(request.user):
            raise PermissionDenied("Only payment staff can record customer deposits.")
        customer = self.get_object()
        serializer = CustomerDepositSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            txn = deposit_to_account(
                customer=customer,
                branch=data["branch"],
                currency=data["currency"],
                amount_received=data["amount"],
                notes=data.get("notes", ""),
                recorded_by=request.user if request.user.is_authenticated else None,
            )
        except CustomerAccountError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        customer.refresh_from_db()
        return Response(
            {
                "account_balance": customer.account_balance,
                "transaction": CustomerAccountTransactionSerializer(txn).data,
            },
            status=status.HTTP_201_CREATED,
        )
