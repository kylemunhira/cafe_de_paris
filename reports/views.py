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
from orders.day_end_close import (
    DayEndValidationError,
    parse_counted_from_body,
    parse_report_date_param,
    save_day_end_close,
    serialize_day_end_close,
    validate_fiscal_counted_currencies,
)
from orders.day_end_serialization import parse_counted_by_currency, serialize_day_end_report
from orders.models import DayEndClose
from inventory.services import daily_stock_take_day_end_status, day_end_stock_take_message
from branches.models import Branch
from payments.models import Currency
from django.utils import timezone
from datetime import datetime


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


def _day_end_branch_or_error(request, branch_param):
    try:
        branch_id = effective_branch_id(request.user, branch_param)
    except ValueError as exc:
        return None, Response({"detail": str(exc)}, status=400)

    if branch_id is None:
        if branch_param in (None, ""):
            return None, Response({"detail": "Branch is required."}, status=400)
        try:
            branch_id = int(branch_param)
        except (TypeError, ValueError):
            return None, Response({"detail": "Invalid branch."}, status=400)

    branch = Branch.objects.filter(pk=branch_id, is_active=True).first()
    if not branch:
        return None, Response({"detail": "Branch not found."}, status=404)
    return branch, None


def _day_end_stock_take_blocked_response(branch, report_date, status_info):
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


def _day_end_payload(branch, report, close=None):
    base_currency = Currency.objects.filter(is_base=True).first()
    payload = {
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
    if close is not None:
        payload["day_end_close"] = serialize_day_end_close(close)
        payload["saved"] = True
    return payload


class DayEndReportView(APIView):
    """Day-end cash-up report for POS clients (Android, etc.).

    GET builds a live preview. POST builds, persists variance/activity, and returns
    the same payload shape used for printing.
    """

    def get(self, request):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required to view day-end reports.")

        branch, error = _day_end_branch_or_error(
            request, request.query_params.get("branch")
        )
        if error:
            return error

        report_date = request.query_params.get("date") or timezone.localdate().isoformat()
        status_info = daily_stock_take_day_end_status(branch, report_date)
        if not status_info["completed"]:
            return _day_end_stock_take_blocked_response(branch, report_date, status_info)

        counted = parse_counted_by_currency(request.query_params)
        try:
            validate_fiscal_counted_currencies(branch, counted)
        except DayEndValidationError as exc:
            return Response({"detail": str(exc)}, status=400)

        report = build_day_end_report(
            branch,
            report_date,
            counted_by_currency=counted,
        )
        return Response(_day_end_payload(branch, report))

    def post(self, request):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required to save day-end reports.")

        data = request.data if isinstance(request.data, dict) else {}
        branch, error = _day_end_branch_or_error(
            request, data.get("branch") or request.query_params.get("branch")
        )
        if error:
            return error

        report_date = (
            parse_report_date_param(data.get("date"))
            or request.query_params.get("date")
            or timezone.localdate().isoformat()
        )
        status_info = daily_stock_take_day_end_status(branch, report_date)
        if not status_info["completed"]:
            return _day_end_stock_take_blocked_response(branch, report_date, status_info)

        counted = parse_counted_from_body(data)
        if not counted:
            counted = parse_counted_by_currency(request.query_params)

        try:
            close, report = save_day_end_close(
                branch,
                report_date,
                counted_by_currency=counted,
                user=request.user,
                notes=data.get("notes") or "",
            )
        except DayEndValidationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_day_end_payload(branch, report, close=close))


class DayEndCloseListView(APIView):
    """Saved day-end closes for the Reports → Day End menu."""

    def get(self, request):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required to view day-end closes.")

        try:
            branch_id = effective_branch_id(
                request.user, request.query_params.get("branch")
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        qs = DayEndClose.objects.select_related("branch", "closed_by").prefetch_related(
            "cash_lines__currency"
        )
        if branch_id is not None:
            qs = qs.filter(branch_id=branch_id)

        from_date = request.query_params.get("from")
        to_date = request.query_params.get("to")
        try:
            if from_date:
                qs = qs.filter(
                    report_date__gte=datetime.strptime(from_date, "%Y-%m-%d").date()
                )
            if to_date:
                qs = qs.filter(
                    report_date__lte=datetime.strptime(to_date, "%Y-%m-%d").date()
                )
        except ValueError:
            return Response(
                {"detail": "Invalid date. Use YYYY-MM-DD for from/to."},
                status=400,
            )

        results = [serialize_day_end_close(close) for close in qs[:500]]
        return Response({"count": len(results), "results": results})


class DayEndCloseDetailView(APIView):
    """Single saved day-end close with full activity snapshot."""

    def get(self, request, pk):
        if not user_can_access_pos(request.user):
            raise PermissionDenied("POS access is required to view day-end closes.")

        close = (
            DayEndClose.objects.select_related("branch", "closed_by")
            .prefetch_related("cash_lines__currency")
            .filter(pk=pk)
            .first()
        )
        if not close:
            return Response({"detail": "Day-end close not found."}, status=404)

        try:
            allowed_branch_id = effective_branch_id(request.user, None)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        if allowed_branch_id is not None and close.branch_id != allowed_branch_id:
            raise PermissionDenied("You cannot view day-end closes for this branch.")

        return Response(serialize_day_end_close(close, include_snapshot=True))


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
