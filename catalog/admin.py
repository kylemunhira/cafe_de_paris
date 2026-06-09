from django.contrib import admin

from .models import Product, ProductCategory


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_asset")
    list_filter = ("is_asset",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "selling_price",
        "remaining_qty",
        "tax_rate",
        "is_active",
        "created_at",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name",)
