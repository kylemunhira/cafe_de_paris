from django.contrib import admin

from .models import Currency, CurrencyRate


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "symbol", "is_base", "is_active", "created_at"]
    list_filter = ["is_active", "is_base"]
    search_fields = ["name", "code"]


@admin.register(CurrencyRate)
class CurrencyRateAdmin(admin.ModelAdmin):
    list_display = [
        "currency",
        "rate",
        "effective_from",
        "is_active",
        "created_at",
    ]
    list_filter = ["is_active", "currency"]
    date_hierarchy = "effective_from"
