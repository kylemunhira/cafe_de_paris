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
from .constants import BAKERY_CATEGORIES, BAKERY_SELLABLE_CATEGORIES
from .models import Product, ProductCategory
from .pos_catalog import pos_catalog_products
from .serializers import ProductCategorySerializer, ProductSerializer


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category").all()
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
        if category:
            queryset = queryset.filter(category__name=category)
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
