from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.mixins import AuditedModelMixin
from audit.models import AuditAction
from audit.services import action_for_update, diff_dicts, record_entity_change, snapshot_fields

from .csv_io import (
    export_ingredients_csv,
    export_products_csv,
    import_ingredients_csv,
    import_products_csv,
)
from .menu_items_import import export_menu_items_csv, import_menu_items_csv
from .constants import (
    ALL_INGREDIENT_CATEGORIES,
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
    PosProductSerializer,
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


def _branch_id_from_request(request):
    branch_param = request.query_params.get("branch")
    if not branch_param or str(branch_param).lower() in ("", "null", "none", "undefined"):
        return None
    try:
        branch_id = int(branch_param)
    except (TypeError, ValueError):
        return None
    from branches.models import Branch

    if not Branch.objects.filter(pk=branch_id, is_active=True).exists():
        return None
    return branch_id


def product_has_protected_references(product):
    return any(getattr(product, rel).exists() for rel in PRODUCT_PROTECTED_RELATIONS)


class ProductCategoryViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    audit_entity_type = "product_category"
    audit_fields = ("name", "is_asset", "show_on_pos", "pos_station")
    audit_label_field = "name"

    def get_queryset(self):
        queryset = super().get_queryset()
        pos_catalog = self.request.query_params.get("pos_catalog")
        if pos_catalog and pos_catalog.lower() in ("1", "true", "yes"):
            queryset = pos_catalog_categories(queryset, branch=_branch_id_from_request(self.request))
        for_ingredient_group = self.request.query_params.get("for_ingredient_group")
        if for_ingredient_group and for_ingredient_group.lower() in ("1", "true", "yes"):
            from django.db.models import Q

            reserved = set(ALL_INGREDIENT_CATEGORIES) | {
                ARCHIVED_CATEGORY,
                "Components",
                "Extras",
            }
            queryset = (
                queryset.exclude(name__in=reserved)
                .filter(
                    Q(show_on_pos=False)
                    | Q(grouped_products__category__name__in=ALL_INGREDIENT_CATEGORIES)
                )
                .distinct()
            )
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
                    before = snapshot_fields(
                        product,
                        ("name", "category", "is_active"),
                    )
                    product.category = reassign_target
                    product.save(update_fields=["category"])
                    after = snapshot_fields(
                        product,
                        ("name", "category", "is_active"),
                    )
                    changes = diff_dicts(before, after)
                    if changes:
                        record_entity_change(
                            action=AuditAction.UPDATE,
                            entity=product,
                            entity_type="product",
                            changes=changes,
                            actor=request.user,
                            request=request,
                        )
                else:
                    record_entity_change(
                        action=AuditAction.DELETE,
                        entity=product,
                        entity_type="product",
                        changes=snapshot_fields(
                            product,
                            (
                                "name",
                                "category",
                                "selling_price",
                                "tax_rate",
                                "is_active",
                            ),
                        ),
                        actor=request.user,
                        request=request,
                    )
                    product.delete()

        self._record_delete_audit(category)
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuAddonGroupViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    queryset = MenuAddonGroup.objects.prefetch_related("addons").all()
    serializer_class = MenuAddonGroupSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    audit_entity_type = "menu_addon_group"
    audit_fields = ("name", "selection_type", "sort_order")
    audit_label_field = "name"


class MenuAddonViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    queryset = MenuAddon.objects.select_related("group").all()
    serializer_class = MenuAddonSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    audit_entity_type = "menu_addon"
    audit_fields = (
        "group",
        "name",
        "selling_price",
        "tax_rate",
        "sort_order",
        "is_active",
    )
    audit_label_field = "name"


class ProductViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    queryset = Product.objects.select_related(
        "category",
        "group_category",
    ).prefetch_related(
        "addon_group_links__group__addons",
        "available_at_branches",
    ).all()
    serializer_class = ProductSerializer
    audit_entity_type = "product"
    audit_fields = (
        "name",
        "category",
        "group_category",
        "selling_price",
        "remaining_qty",
        "tax_rate",
        "hs_code",
        "fiscal_tax_code",
        "fiscal_tax_id",
        "is_active",
        "daily_stock_take",
    )
    audit_label_field = "name"

    def _is_pos_catalog_request(self):
        pos_catalog = self.request.query_params.get("pos_catalog")
        return bool(pos_catalog and pos_catalog.lower() in ("1", "true", "yes"))

    def get_serializer_class(self):
        if self.action == "list" and self._is_pos_catalog_request():
            return PosProductSerializer
        return super().get_serializer_class()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "list":
            # POS terminals do not display unit cost; skip bakery costing for speed.
            if self._is_pos_catalog_request():
                context["unit_costs"] = {}
            else:
                from bakery.costing import product_unit_costs

                context["unit_costs"] = product_unit_costs()
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        exclude_category = self.request.query_params.get("exclude_category")
        exclude_ingredients = self.request.query_params.get("exclude_ingredients")
        ingredients_only = self.request.query_params.get("ingredients_only")
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
        if exclude_ingredients and exclude_ingredients.lower() in ("1", "true", "yes"):
            queryset = queryset.exclude(category__name__in=ALL_INGREDIENT_CATEGORIES)
        if ingredients_only and ingredients_only.lower() in ("1", "true", "yes"):
            queryset = queryset.filter(category__name__in=ALL_INGREDIENT_CATEGORIES)
        if bakery_transfer and bakery_transfer.lower() in ("1", "true", "yes"):
            queryset = queryset.filter(
                is_active=True,
                category__name__in=BAKERY_SELLABLE_CATEGORIES,
            )
        # Admin list pages (Products / Bakery Products) include inactive rows
        # so staff can find and reactivate them. Operational filters
        # (bakery_transfer, pos_catalog) still require is_active=True.
        if bakery_manufactured and bakery_manufactured.lower() in ("1", "true", "yes"):
            queryset = queryset.filter(category__name__in=BAKERY_CATEGORIES)
        if exclude_bakery and exclude_bakery.lower() in ("1", "true", "yes"):
            queryset = queryset.exclude(category__name__in=BAKERY_CATEGORIES)
        if pos_catalog and pos_catalog.lower() in ("1", "true", "yes"):
            queryset = pos_catalog_products(
                queryset,
                branch=_branch_id_from_request(self.request),
            )
        return queryset

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        if product_has_protected_references(product):
            before = self.get_audit_snapshot(product)
            product.is_active = False
            product.save(update_fields=["is_active"])
            after = self.get_audit_snapshot(product)
            changes = diff_dicts(before, after)
            if changes:
                record_entity_change(
                    action=action_for_update(before, after),
                    entity=product,
                    entity_type=self.audit_entity_type,
                    changes=changes,
                    actor=request.user,
                    request=request,
                )
            serializer = self.get_serializer(product)
            return Response(serializer.data)
        self._record_delete_audit(product)
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
        branch = None
        branch_id = request.query_params.get("branch")
        if branch_id:
            from branches.models import Branch

            try:
                branch = Branch.objects.get(pk=int(branch_id))
            except (TypeError, ValueError, Branch.DoesNotExist):
                return Response(
                    {"detail": "Invalid branch."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        response = HttpResponse(
            export_ingredients_csv(branch=branch),
            content_type="text/csv; charset=utf-8",
        )
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

        branch = None
        branch_id = request.data.get("branch") or request.query_params.get("branch")
        if branch_id:
            from branches.models import Branch

            try:
                branch = Branch.objects.get(pk=int(branch_id))
            except (TypeError, ValueError, Branch.DoesNotExist):
                return Response(
                    {"detail": "Invalid branch."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        from .constants import (
            BRANCH_INGREDIENTS_CATEGORY,
            INGREDIENTS_CATEGORY,
        )
        from branches.models import BranchType

        category_name = INGREDIENTS_CATEGORY
        if branch is not None and branch.branch_type == BranchType.BRANCH:
            category_name = BRANCH_INGREDIENTS_CATEGORY

        result = import_ingredients_csv(
            upload,
            category_name=category_name,
            branch=branch,
            user=request.user if request.user.is_authenticated else None,
        )
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
