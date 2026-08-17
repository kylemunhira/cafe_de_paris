from django.contrib import admin

from .models import (
    BranchInventory,
    CentralInvoice,
    CentralInvoiceLine,
    DeliveryNote,
    DeliveryNoteLine,
    StockMovement,
    StockTake,
    StockTakeLine,
    StockTransfer,
    WastageEntry,
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


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "branch",
        "product",
        "delta",
        "quantity_after",
        "reason",
        "created_by",
    )
    list_filter = ("reason", "branch")
    search_fields = ("product__name", "branch__name", "note")
    readonly_fields = (
        "branch",
        "product",
        "quantity_before",
        "delta",
        "quantity_after",
        "reason",
        "note",
        "reference_type",
        "reference_id",
        "created_by",
        "created_at",
    )


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
    fields = (
        "product",
        "system_quantity",
        "counted_quantity",
        "wastage_quantity",
        "notes",
    )


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


@admin.register(WastageEntry)
class WastageEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "branch",
        "product",
        "quantity",
        "reason",
        "status",
        "destination_branch",
        "created_at",
        "processed_at",
    )
    list_filter = ("reason", "status", "branch")
    search_fields = ("product__name", "branch__name", "notes")
    readonly_fields = ("created_at", "processed_at", "created_by", "processed_by")
