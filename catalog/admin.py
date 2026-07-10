from django.contrib import admin

from .models import MenuAddon, MenuAddonGroup, Product, ProductCategory, ProductMenuAddonGroup


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_asset", "pos_station")
    list_filter = ("is_asset", "pos_station")
    search_fields = ("name",)


class MenuAddonInline(admin.TabularInline):
    model = MenuAddon
    extra = 0


@admin.register(MenuAddonGroup)
class MenuAddonGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "selection_type", "sort_order")
    list_filter = ("selection_type",)
    search_fields = ("name",)
    inlines = [MenuAddonInline]


class ProductMenuAddonGroupInline(admin.TabularInline):
    model = ProductMenuAddonGroup
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "selling_price",
        "remaining_qty",
        "tax_rate",
        "is_active",
        "daily_stock_take",
        "created_at",
    )
    list_filter = ("category", "is_active", "daily_stock_take")
    search_fields = ("name",)
    inlines = [ProductMenuAddonGroupInline]
