from django.contrib import admin

from .models import Customer, CustomerAccountTransaction


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "phone",
        "account_type",
        "account_balance",
        "loyalty_points",
        "created_at",
    )
    list_filter = ("account_type",)
    search_fields = ("first_name", "last_name", "phone", "email")


@admin.register(CustomerAccountTransaction)
class CustomerAccountTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "transaction_type",
        "amount",
        "balance_after",
        "branch",
        "created_at",
    )
    list_filter = ("transaction_type", "branch")
    search_fields = ("customer__first_name", "customer__last_name", "notes")
