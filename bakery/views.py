from rest_framework import viewsets

from .models import Recipe
from .serializers import RecipeSerializer


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
