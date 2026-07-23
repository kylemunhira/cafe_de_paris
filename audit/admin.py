from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action",
        "entity_type",
        "entity_id",
        "entity_label",
        "actor",
        "branch",
    )
    list_filter = ("action", "entity_type", "branch")
    search_fields = ("entity_label", "entity_id", "actor__username", "request_path")
    readonly_fields = (
        "created_at",
        "actor",
        "branch",
        "action",
        "entity_type",
        "entity_id",
        "entity_label",
        "changes",
        "request_path",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
