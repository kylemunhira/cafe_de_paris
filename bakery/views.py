from django.db.models import Count, Q

from accounts.branch_access import (
    filter_by_branch_field,
    get_staff_branch_id,
    user_can_access_bakery_transfers,
    user_has_global_branch_access,
)
from audit.mixins import AuditedModelMixin
from inventory.services import InsufficientStockError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import ProductionOrder, ProductionSheet, Recipe
from .serializers import (
    ProductionCompleteSerializer,
    ProductionOrderSerializer,
    ProductionPreviewSerializer,
    ProductionSheetCreateSerializer,
    ProductionSheetLinesUpdateSerializer,
    ProductionSheetSerializer,
    RecipeSerializer,
)
from .services import (
    EmptyProductionSheetError,
    InsufficientIngredientsError,
    InvalidProductionSheetStateError,
    NoRecipeError,
    cancel_production_sheet,
    complete_production_sheet,
    preview_production,
    sync_production_sheet_lines,
)


class RecipeViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    queryset = Recipe.objects.select_related(
        "product",
        "product__category",
        "menu_addon",
        "menu_addon__group",
        "ingredient",
        "ingredient__category",
        "ingredient__group_category",
    ).all()
    serializer_class = RecipeSerializer
    audit_entity_type = "recipe"
    audit_fields = ("product", "menu_addon", "ingredient", "quantity_required")
    audit_label_field = lambda recipe: (  # noqa: E731
        f"{recipe.product or recipe.menu_addon} / {recipe.ingredient}"
    )
    def get_queryset(self):
        queryset = super().get_queryset()
        product_id = self.request.query_params.get("product")
        menu_addon_id = self.request.query_params.get("menu_addon")
        ingredient_id = self.request.query_params.get("ingredient")

        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if menu_addon_id:
            queryset = queryset.filter(menu_addon_id=menu_addon_id)
        if ingredient_id:
            queryset = queryset.filter(ingredient_id=ingredient_id)
        return queryset


class ProductionOrderViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProductionOrder.objects.select_related(
        "branch",
        "product",
        "created_by",
    ).all()
    serializer_class = ProductionOrderSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        branch_id = self.request.query_params.get("branch")
        product_id = self.request.query_params.get("product")
        queryset = filter_by_branch_field(
            queryset, self.request.user, requested_branch_id=branch_id
        )
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        return queryset

    def _ensure_bakery_access(self, branch):
        if not user_can_access_bakery_transfers(self.request.user):
            raise PermissionDenied(
                "Only central bakery staff or HQ admins can record production."
            )
        if user_has_global_branch_access(self.request.user):
            return
        staff_branch_id = get_staff_branch_id(self.request.user)
        if staff_branch_id is None or staff_branch_id != branch.id:
            raise PermissionDenied(
                "You can only record production for your assigned bakery branch."
            )

    @action(detail=False, methods=["post"])
    def preview(self, request):
        serializer = ProductionPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self._ensure_bakery_access(data["branch"])
        try:
            preview = preview_production(
                data["branch"],
                data["product"],
                data["quantity"],
            )
        except NoRecipeError as exc:
            return Response({"product": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(preview)

    def create(self, request, *args, **kwargs):
        serializer = ProductionCompleteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        branch = serializer.validated_data["branch"]
        self._ensure_bakery_access(branch)
        order = serializer.save()
        order = self.get_queryset().get(pk=order.pk)
        return Response(
            ProductionOrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class ProductionSheetViewSet(viewsets.ModelViewSet):
    queryset = ProductionSheet.objects.select_related(
        "branch",
        "created_by",
    ).prefetch_related(
        "lines__product__category",
        "lines__allocations__destination_branch",
    ).all()
    serializer_class = ProductionSheetSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return ProductionSheetCreateSerializer
        if self.action == "update_lines":
            return ProductionSheetLinesUpdateSerializer
        return ProductionSheetSerializer

    def get_queryset(self):
        queryset = super().get_queryset().annotate(
            line_count=Count("lines", distinct=True),
            produced_line_count=Count(
                "lines",
                filter=Q(lines__allocations__quantity__gt=0),
                distinct=True,
            ),
        )
        branch_id = self.request.query_params.get("branch")
        status_filter = self.request.query_params.get("status")
        production_date = self.request.query_params.get("production_date")

        queryset = filter_by_branch_field(
            queryset, self.request.user, requested_branch_id=branch_id
        )
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if production_date:
            queryset = queryset.filter(production_date=production_date)
        return queryset.order_by("-production_date", "-created_at")

    def _ensure_bakery_access(self, branch):
        if not user_can_access_bakery_transfers(self.request.user):
            raise PermissionDenied(
                "Only central bakery staff or HQ admins can manage production sheets."
            )
        if user_has_global_branch_access(self.request.user):
            return
        staff_branch_id = get_staff_branch_id(self.request.user)
        if staff_branch_id is None or staff_branch_id != branch.id:
            raise PermissionDenied(
                "You can only manage production sheets for your assigned bakery."
            )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = serializer.validated_data["branch"]
        self._ensure_bakery_access(branch)
        sheet = serializer.save()
        sheet = self.get_queryset().get(pk=sheet.pk)
        return Response(
            ProductionSheetSerializer(sheet).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        sheet = self.get_object()
        if sheet.status == "draft":
            sync_production_sheet_lines(sheet)
            sheet = self.get_queryset().get(pk=sheet.pk)
        return Response(ProductionSheetSerializer(sheet).data)

    def _serialize_sheet(self, sheet):
        sheet = self.get_queryset().get(pk=sheet.pk)
        return ProductionSheetSerializer(sheet).data

    def _run_transition(self, request, pk, handler):
        sheet = self.get_object()
        self._ensure_bakery_access(sheet.branch)
        try:
            sheet = handler(sheet)
        except InvalidProductionSheetStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except EmptyProductionSheetError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientIngredientsError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "shortages": [
                        {
                            "ingredient_id": item.ingredient.id,
                            "ingredient_name": item.ingredient.name,
                            "required": str(item.required),
                            "available": str(item.available),
                        }
                        for item in exc.shortages
                    ],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InsufficientStockError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "available": str(exc.available),
                    "requested": str(exc.requested),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self._serialize_sheet(sheet))

    @action(detail=True, methods=["patch"], url_path="lines")
    def update_lines(self, request, pk=None):
        sheet = self.get_object()
        self._ensure_bakery_access(sheet.branch)
        serializer = self.get_serializer(sheet, data=request.data)
        serializer.is_valid(raise_exception=True)
        sheet = serializer.save()
        return Response(self._serialize_sheet(sheet))

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._run_transition(request, pk, complete_production_sheet)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._run_transition(request, pk, cancel_production_sheet)
