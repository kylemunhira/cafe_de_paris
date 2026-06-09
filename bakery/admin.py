from django.contrib import admin

from .models import ProductionOrder, Recipe


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("product", "ingredient", "quantity_required")
    search_fields = ("product__name", "ingredient__name")


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "quantity", "status", "created_at")
    list_filter = ("status",)
