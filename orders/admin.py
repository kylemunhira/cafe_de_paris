from django.contrib import admin

from .models import Expense, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "branch",
        "order_type",
        "status",
        "total_amount",
        "created_at",
    )
    list_filter = ("status", "order_type", "branch")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "quantity", "price")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "expense_date",
        "branch",
        "supplier",
        "description",
        "amount",
        "currency",
        "recorded_by",
        "created_at",
    )
    list_filter = ("branch", "expense_date", "currency", "supplier")
    search_fields = ("description", "supplier__name")
