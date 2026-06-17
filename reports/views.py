from accounts.branch_access import effective_branch_id
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import build_profit_report, build_report_summary, export_sales_csv


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
