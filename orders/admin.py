from django.contrib import admin

from .models import DayEndCashLine, DayEndClose, Expense, Order, OrderItem, OrderPayment


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderPaymentInline(admin.TabularInline):
    model = OrderPayment
    extra = 0
    readonly_fields = ("method", "currency", "amount", "exchange_rate")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "branch",
        "order_type",
        "status",
        "payment_method",
        "total_amount",
        "created_at",
    )
    list_filter = ("status", "order_type", "payment_method", "branch")
    inlines = [OrderItemInline, OrderPaymentInline]


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


class DayEndCashLineInline(admin.TabularInline):
    model = DayEndCashLine
    extra = 0
    readonly_fields = (
        "currency",
        "sales_total",
        "deposits_total",
        "expenses_total",
        "expected_total",
        "net_expected_total",
        "counted_total",
        "variance",
    )


@admin.register(DayEndClose)
class DayEndCloseAdmin(admin.ModelAdmin):
    list_display = (
        "report_date",
        "branch",
        "order_count",
        "gross_total",
        "variance_total",
        "has_counted_entries",
        "closed_by",
        "closed_at",
    )
    list_filter = ("branch", "report_date", "has_counted_entries")
    readonly_fields = (
        "branch",
        "report_date",
        "closed_at",
        "closed_by",
        "order_count",
        "gross_total",
        "expenses_total",
        "variance_total",
        "has_counted_entries",
        "activity_snapshot",
        "notes",
    )
    inlines = [DayEndCashLineInline]