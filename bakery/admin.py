from django.contrib import admin

from .models import (
    ProductionOrder,
    ProductionSheet,
    ProductionSheetAllocation,
    ProductionSheetLine,
    Recipe,
)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("product", "ingredient", "quantity_required")
    search_fields = ("product__name", "ingredient__name")


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "branch", "product", "quantity", "status", "created_by", "created_at")
    list_filter = ("status", "branch")


class ProductionSheetAllocationInline(admin.TabularInline):
    model = ProductionSheetAllocation
    extra = 0


class ProductionSheetLineInline(admin.TabularInline):
    model = ProductionSheetLine
    extra = 0
    show_change_link = True


@admin.register(ProductionSheet)
class ProductionSheetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "branch",
        "production_date",
        "status",
        "created_by",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "branch", "production_date")
    inlines = [ProductionSheetLineInline]


@admin.register(ProductionSheetLine)
class ProductionSheetLineAdmin(admin.ModelAdmin):
    list_display = ("id", "sheet", "product")
    list_filter = ("sheet__production_date",)
    inlines = [ProductionSheetAllocationInline]
