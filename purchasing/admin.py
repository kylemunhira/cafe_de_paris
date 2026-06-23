from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderLine, Supplier


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "vat_number",
        "contact_person",
        "phone",
        "email",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "vat_number", "contact_person", "email", "phone")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "branch",
        "supplier",
        "status",
        "created_by",
        "created_at",
        "received_at",
    )
    list_filter = ("status", "branch", "supplier")
    inlines = [PurchaseOrderLineInline]
