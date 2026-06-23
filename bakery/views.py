from accounts.branch_access import (
    filter_by_branch_field,
    get_staff_branch_id,
    user_can_access_bakery_transfers,
    user_has_global_branch_access,
)
from branches.models import BranchType
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import ProductionOrder, Recipe
from .serializers import (
    ProductionCompleteSerializer,
    ProductionOrderSerializer,
    ProductionPreviewSerializer,
    RecipeSerializer,
)
from .services import NoRecipeError, preview_production


class RecipeViewSet(viewsets.ModelViewSet):
    queryset = Recipe.objects.select_related(
        "product",
        "product__category",
        "ingredient",
        "ingredient__category",
    ).all()
    serializer_class = RecipeSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        product_id = self.request.query_params.get("product")
        ingredient_id = self.request.query_params.get("ingredient")

        if product_id:
            queryset = queryset.filter(product_id=product_id)
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
