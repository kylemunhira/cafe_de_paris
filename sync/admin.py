from django.contrib import admin

from .models import SyncedClientOrder


@admin.register(SyncedClientOrder)
class SyncedClientOrderAdmin(admin.ModelAdmin):
    list_display = ("client_id", "order", "synced_at")
    search_fields = ("client_id", "order__receipt_number")
    readonly_fields = ("client_id", "order", "synced_at")
