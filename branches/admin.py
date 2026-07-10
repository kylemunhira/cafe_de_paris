from django.contrib import admin

from .models import Branch, DiningTable


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "branch_type",
        "location",
        "is_active",
        "allow_negative_stock",
        "fiscalization_enabled",
        "created_at",
    )
    list_filter = ("branch_type", "is_active", "fiscalization_enabled")
    search_fields = ("name", "location")


@admin.register(DiningTable)
class DiningTableAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "sort_order", "is_active")
    list_filter = ("branch", "is_active")
    search_fields = ("name",)
