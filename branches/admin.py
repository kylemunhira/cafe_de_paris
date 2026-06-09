from django.contrib import admin

from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "branch_type",
        "location",
        "is_active",
        "fiscalization_enabled",
        "created_at",
    )
    list_filter = ("branch_type", "is_active", "fiscalization_enabled")
    search_fields = ("name", "location")
