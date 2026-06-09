from django.contrib import admin

from .models import BranchFiscalState, FiscalReceipt


@admin.register(BranchFiscalState)
class BranchFiscalStateAdmin(admin.ModelAdmin):
    list_display = (
        "branch",
        "receipt_counter",
        "receipt_global_no",
        "invoice_sequence",
    )
    search_fields = ("branch__name",)


@admin.register(FiscalReceipt)
class FiscalReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "fiscal_invoice_number",
        "invoice_no",
        "order",
        "branch",
        "receipt_counter",
        "verification_code",
        "status",
        "created_at",
    )
    list_filter = ("status", "branch")
    search_fields = ("invoice_no", "fiscal_invoice_number", "verification_code", "order__id")
    readonly_fields = (
        "payload",
        "zimra_response",
        "device_branch_name",
        "device_serial_no",
        "fiscal_day_number",
        "fiscal_invoice_number",
        "qr_string",
        "qr_url",
        "verification_code",
        "created_at",
    )
