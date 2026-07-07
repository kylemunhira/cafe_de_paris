from accounts.branch_access import (
    effective_branch_id,
    user_can_access_fiscal_receipts,
    user_can_access_pos,
    user_can_create_purchase_orders,
)
from django.http import HttpResponse
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from customers.reports import build_customer_balances_report
from purchasing.reports import build_supplier_spend_summary_report

from .ingredients import build_ingredient_stock_report, build_ingredient_usage_report
from .services import build_profit_report, build_report_summary, export_sales_csv
from .vat import build_vat_report
from orders.day_end import build_day_end_report
from orders.day_end_serialization import parse_counted_by_currency, serialize_day_end_report
from inventory.services import daily_stock_take_day_end_status, day_end_stock_take_message
from branches.models import Branch
from payments.models import Currency
from django.utils import timezone


class ReportSummaryView(APIView):
    def get(self, request):
        try:
            branch_id = effective_branch_id(
                request.user, request.query_params.get("branch")
            )
            data = build_report_summary(
                from_date=request.query_params.get("from"),
                to_date=request.query_params.get("to"),
                branch_id=branch_id,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data)


class ReportProfitView(APIView):
    def get(self, request):
        try:
            branch_id = effective_branch_id(
                request.user, request.query_params.get("branch")
            )
            data = build_profit_report(
                from_date=request.query_params.get("from"),
                to_date=request.query_params.get("to"),
                branch_id=branch_id,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data)


class ReportExportCsvView(APIView):
    def get(self, request):
        try:
            branch_id = effective_branch_id(
                request.user, request.query_params.get("branch")
            )
            csv_text = export_sales_csv(
                from_date=request.query_params.get("from"),
                to_date=request.query_params.get("to"),
                branch_id=branch_id,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="sales-report.csv"'
        return response


class ReportCustomerBalancesView(APIView):
    def get(self, request):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("Only POS staff can view customer balance reports.")

        data = build_customer_balances_report(
            search=request.query_params.get("search"),
            non_zero_only=request.query_params.get("non_zero_only") == "1",
        )
        return Response(data)


class ReportSupplierSpendView(APIView):
    def get(self, request):
        if not user_can_create_purchase_orders(request.user):
            raise PermissionDenied("Only purchase staff can view supplier spend reports.")

        try:
            branch_id = effective_branch_id(
                request.user, request.query_params.get("branch")
            )
            data = build_supplier_spend_summary_report(
                search=request.query_params.get("search"),
                from_date=request.query_params.get("from"),
                to_date=request.query_params.get("to"),
                branch_id=branch_id,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data)


class ReportIngredientStockView(APIView):
    def get(self, request):
        try:
            branch_id = effective_branch_id(
                request.user, request.query_params.get("branch")
            )
            data = build_ingredient_stock_report(
                branch_id=branch_id,
                search=request.query_params.get("search"),
                active_only=request.query_params.get("active_only", "1") != "0",
                low_stock_only=request.query_params.get("low_stock_only") == "1",
                low_stock_threshold=request.query_params.get("low_stock_threshold"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data)


class ReportIngredientUsageView(APIView):
    def get(self, request):
        try:
            branch_id = effective_branch_id(
                request.user, request.query_params.get("branch")
            )
            data = build_ingredient_usage_report(
                report_date=request.query_params.get("date"),
                branch_id=branch_id,
                search=request.query_params.get("search"),
                active_only=request.query_params.get("active_only", "1") != "0",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data)


class DayEndReportView(APIView):
    """Day-end cash-up report for POS clients (Android, etc.)."""

    def get(self, request):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required to view day-end reports.")

        try:
            branch_id = effective_branch_id(
                request.user, request.query_params.get("branch")
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        branch = Branch.objects.filter(pk=branch_id, is_active=True).first()
        if not branch:
            return Response({"detail": "Branch not found."}, status=404)

        report_date = request.query_params.get("date") or timezone.localdate().isoformat()
        status_info = daily_stock_take_day_end_status(branch, report_date)
        if not status_info["completed"]:
            return Response(
                {
                    "detail": day_end_stock_take_message(
                        branch,
                        report_date,
                        completed=False,
                        draft_in_progress=status_info["draft_in_progress"],
                    ),
                    "completed": False,
                    "draft_in_progress": status_info["draft_in_progress"],
                    "count_date": report_date,
                    "branch": branch.id,
                    "branch_name": branch.name,
                },
                status=403,
            )

        report = build_day_end_report(
            branch,
            report_date,
            counted_by_currency=parse_counted_by_currency(request.query_params),
        )
        base_currency = Currency.objects.filter(is_base=True).first()
        return Response(
            {
                "branch": {
                    "id": branch.id,
                    "name": branch.name,
                    "location": branch.location,
                },
                "base_currency": (
                    {
                        "id": base_currency.id,
                        "code": base_currency.code,
                        "name": base_currency.name,
                        "symbol": base_currency.symbol,
                    }
                    if base_currency
                    else None
                ),
                "printed_at": timezone.now().isoformat(),
                "report": serialize_day_end_report(report),
            }
        )


class ReportVATView(APIView):
    def get(self, request):
        if not user_can_access_fiscal_receipts(request.user):
            raise PermissionDenied("Only fiscal staff can view VAT reports.")

        try:
            branch_id = effective_branch_id(
                request.user, request.query_params.get("branch")
            )
            data = build_vat_report(
                from_date=request.query_params.get("from"),
                to_date=request.query_params.get("to"),
                branch_id=branch_id,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data)
