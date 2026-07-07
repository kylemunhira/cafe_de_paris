from django.contrib import admin

from .models import (
    BranchInventory,
    CentralInvoice,
    CentralInvoiceLine,
    DeliveryNote,
    DeliveryNoteLine,
    StockTake,
    StockTakeLine,
    StockTransfer,
)


class CentralInvoiceLineInline(admin.TabularInline):
    model = CentralInvoiceLine
    extra = 0


@admin.register(CentralInvoice)
class CentralInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "from_branch",
        "customer",
        "status",
        "payment_status",
        "created_at",
    )
    list_filter = ("status", "payment_status", "from_branch")
    inlines = [CentralInvoiceLineInline]


class DeliveryNoteLineInline(admin.TabularInline):
    model = DeliveryNoteLine
    extra = 0


@admin.register(BranchInventory)
class BranchInventoryAdmin(admin.ModelAdmin):
    list_display = ("branch", "product", "quantity", "last_updated")
    list_filter = ("branch",)
    search_fields = ("product__name", "branch__name")


@admin.register(DeliveryNote)
class DeliveryNoteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "from_branch",
        "to_branch",
        "invoice_number",
        "status",
        "payment_status",
        "created_at",
    )
    list_filter = ("status", "payment_status", "from_branch", "to_branch")
    inlines = [DeliveryNoteLineInline]


class StockTakeLineInline(admin.TabularInline):
    model = StockTakeLine
    extra = 0
    readonly_fields = ("product", "system_quantity")


@admin.register(StockTake)
class StockTakeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "branch",
        "stock_take_type",
        "count_date",
        "status",
        "created_at",
        "completed_at",
    )
    list_filter = ("stock_take_type", "status", "branch")
    inlines = [StockTakeLineInline]


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "from_branch",
        "to_branch",
        "quantity",
        "status",
        "created_at",
    )
    list_filter = ("status", "from_branch", "to_branch")
