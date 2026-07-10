from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .csv_io import (
    export_ingredients_csv,
    export_products_csv,
    import_ingredients_csv,
    import_products_csv,
)
from .menu_items_import import export_menu_items_csv, import_menu_items_csv
from .constants import (
    ARCHIVED_CATEGORY,
    BAKERY_CATEGORIES,
    BAKERY_SELLABLE_CATEGORIES,
    ingredient_categories_for_branch_type,
)
from .models import MenuAddon, MenuAddonGroup, Product, ProductCategory, ProductMenuAddonGroup
from .pos_catalog import pos_catalog_categories, pos_catalog_products
from .serializers import (
    MenuAddonGroupSerializer,
    MenuAddonSerializer,
    ProductCategorySerializer,
    ProductSerializer,
)

PRODUCT_PROTECTED_RELATIONS = (
    "order_items",
    "purchase_order_lines",
    "production_orders",
    "stock_transfers",
    "stock_take_lines",
    "delivery_note_lines",
    "central_invoice_lines",
)


def product_has_protected_references(product):
    return any(getattr(product, rel).exists() for rel in PRODUCT_PROTECTED_RELATIONS)


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        pos_catalog = self.request.query_params.get("pos_catalog")
        if pos_catalog and pos_catalog.lower() in ("1", "true", "yes"):
            queryset = pos_catalog_categories(queryset)
        return queryset

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.products.filter(is_active=True).exists():
            return Response(
                {"detail": "Cannot delete a category while it has active products."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        inactive_products = list(category.products.filter(is_active=False))
        if inactive_products:
            archived_category, _ = ProductCategory.objects.get_or_create(
                name=ARCHIVED_CATEGORY,
            )
            reassign_target = (
                None if archived_category.pk == category.pk else archived_category
            )
            blocked = [
                product.name
                for product in inactive_products
                if product_has_protected_references(product) and reassign_target is None
            ]
            if blocked:
                return Response(
                    {
                        "detail": (
                            "Cannot delete this category while it contains inactive "
                            "products with order or inventory history."
                        ),
                        "products": blocked,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for product in inactive_products:
                if product_has_protected_references(product):
                    product.category = reassign_target
                    product.save(update_fields=["category"])
                else:
                    product.delete()

        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuAddonGroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MenuAddonGroup.objects.prefetch_related("addons").all()
    serializer_class = MenuAddonGroupSerializer


class MenuAddonViewSet(viewsets.ModelViewSet):
    queryset = MenuAddon.objects.select_related("group").all()
    serializer_class = MenuAddonSerializer
    http_method_names = ["get", "patch", "head", "options"]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category").prefetch_related(
        "addon_group_links__group__addons",
    ).all()
    serializer_class = ProductSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "list":
            from bakery.costing import product_unit_costs

            context["unit_costs"] = product_unit_costs()
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        exclude_category = self.request.query_params.get("exclude_category")
        bakery_transfer = self.request.query_params.get("bakery_transfer")
        bakery_manufactured = self.request.query_params.get("bakery_manufactured")
        exclude_bakery = self.request.query_params.get("exclude_bakery")
        pos_catalog = self.request.query_params.get("pos_catalog")
        for_branch = self.request.query_params.get("for_branch")
        if category:
            queryset = queryset.filter(category__name=category)
        if for_branch and str(for_branch).lower() not in ("", "null", "none", "undefined"):
            from branches.models import Branch

            try:
                branch_id = int(for_branch)
            except (TypeError, ValueError):
                branch_id = None
            if branch_id:
                branch = Branch.objects.filter(pk=branch_id).first()
                if branch:
                    categories = ingredient_categories_for_branch_type(branch.branch_type)
                    if categories:
                        queryset = queryset.filter(category__name__in=categories)
                    else:
                        queryset = queryset.none()
        if exclude_category:
            queryset = queryset.exclude(category__name=exclude_category)
        if bakery_transfer and bakery_transfer.lower() in ("1", "true", "yes"):
            queryset = queryset.filter(
                is_active=True,
                category__name__in=BAKERY_SELLABLE_CATEGORIES,
            )
        if bakery_manufactured and bakery_manufactured.lower() in ("1", "true", "yes"):
            queryset = queryset.filter(category__name__in=BAKERY_CATEGORIES)
        if exclude_bakery and exclude_bakery.lower() in ("1", "true", "yes"):
            queryset = queryset.exclude(category__name__in=BAKERY_CATEGORIES)
        if pos_catalog and pos_catalog.lower() in ("1", "true", "yes"):
            queryset = pos_catalog_products(queryset)
        return queryset

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        if product_has_protected_references(product):
            product.is_active = False
            product.save(update_fields=["is_active"])
            serializer = self.get_serializer(product)
            return Response(serializer.data)
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="export-csv")
    def export_csv(self, request):
        response = HttpResponse(export_products_csv(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="products.csv"'
        return response

    @action(detail=False, methods=["post"], url_path="import-csv")
    def import_csv(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "No file uploaded. Use form field name 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload.name.lower().endswith(".csv"):
            return Response(
                {"detail": "Only .csv files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = import_products_csv(upload)
        if result["errors"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="export-ingredients-csv")
    def export_ingredients_csv(self, request):
        response = HttpResponse(export_ingredients_csv(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="ingredients.csv"'
        return response

    @action(detail=False, methods=["post"], url_path="import-ingredients-csv")
    def import_ingredients_csv(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "No file uploaded. Use form field name 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload.name.lower().endswith(".csv"):
            return Response(
                {"detail": "Only .csv files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = import_ingredients_csv(upload)
        if result["errors"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="export-menu-items-csv")
    def export_menu_items_csv(self, request):
        response = HttpResponse(export_menu_items_csv(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="menu_items.csv"'
        return response

    @action(detail=False, methods=["post"], url_path="import-menu-items-csv")
    def import_menu_items_csv(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "No file uploaded. Use form field name 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload.name.lower().endswith(".csv"):
            return Response(
                {"detail": "Only .csv files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        replace = request.query_params.get("replace", "true").lower() in ("1", "true", "yes")
        try:
            result = import_menu_items_csv(upload, replace=replace)
        except ValueError as exc:
            return Response(
                {"detail": str(exc), "errors": [{"row": 0, "message": str(exc)}]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result, status=status.HTTP_200_OK)
