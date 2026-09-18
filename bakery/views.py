from django.db.models import Count, Q

from accounts.branch_access import (
    filter_by_branch_field,
    get_staff_branch_id,
    user_can_access_bakery_transfers,
    user_can_access_order_papers,
    user_can_create_order_papers,
    user_can_manage_bakery_order_papers,
    user_has_global_branch_access,
)
from audit.mixins import AuditedModelMixin
from inventory.services import InsufficientStockError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import OrderPaper, OrderPaperStatus, ProductionOrder, ProductionSheet, Recipe
from .serializers import (
    OrderPaperAcceptSerializer,
    OrderPaperCreateSerializer,
    OrderPaperSerializer,
    OrderPaperUpdateSerializer,
    ProductionCompleteSerializer,
    ProductionOrderSerializer,
    ProductionPreviewSerializer,
    ProductionSheetCreateSerializer,
    ProductionSheetFromOrderPapersSerializer,
    ProductionSheetLinesUpdateSerializer,
    ProductionSheetSerializer,
    RecipeSerializer,
)
from .services import (
    EmptyOrderPaperError,
    EmptyProductionSheetError,
    InsufficientIngredientsError,
    InvalidOrderPaperStateError,
    InvalidProductionSheetStateError,
    NoRecipeError,
    cancel_order_paper,
    cancel_production_sheet,
    complete_production_sheet,
    order_paper_demand_totals,
    preview_production,
    submit_order_paper,
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

    @action(detail=False, methods=["post"], url_path="from-order-papers")
    def from_order_papers(self, request):
        if not user_can_manage_bakery_order_papers(request.user):
            raise PermissionDenied(
                "Only bakery staff or HQ admins can create production from order papers."
            )
        serializer = ProductionSheetFromOrderPapersSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        bakery = serializer.validated_data["branch"]
        self._ensure_bakery_access(bakery)
        sheet = serializer.save()
        sheet = self.get_queryset().get(pk=sheet.pk)
        return Response(
            ProductionSheetSerializer(sheet, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class OrderPaperViewSet(viewsets.ModelViewSet):
    queryset = OrderPaper.objects.select_related(
        "requesting_branch",
        "bakery",
        "created_by",
        "production_sheet",
    ).prefetch_related(
        "lines__product__category",
    ).all()
    serializer_class = OrderPaperSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return OrderPaperCreateSerializer
        if self.action in ("update", "partial_update"):
            return OrderPaperUpdateSerializer
        if self.action == "accept":
            return OrderPaperAcceptSerializer
        return OrderPaperSerializer

    def get_queryset(self):
        queryset = super().get_queryset().annotate(
            line_count=Count("lines", distinct=True),
        )
        user = self.request.user
        if not user_can_access_order_papers(user):
            return queryset.none()

        status_filter = self.request.query_params.get("status")
        needed_date = self.request.query_params.get("needed_date")
        bakery_id = self.request.query_params.get("bakery")
        requesting_branch_id = self.request.query_params.get("requesting_branch")

        if user_can_manage_bakery_order_papers(user) and (
            user_has_global_branch_access(user)
            or not user_can_create_order_papers(user)
        ):
            # Bakery / HQ: see papers destined for their bakery (or all for HQ).
            if user_has_global_branch_access(user):
                queryset = filter_by_branch_field(
                    queryset,
                    user,
                    branch_field="bakery",
                    requested_branch_id=bakery_id,
                )
            else:
                staff_branch_id = get_staff_branch_id(user)
                queryset = queryset.filter(bakery_id=staff_branch_id)
                if bakery_id and str(staff_branch_id) != str(bakery_id):
                    return queryset.none()
            if requesting_branch_id:
                queryset = queryset.filter(requesting_branch_id=requesting_branch_id)
        else:
            # Branch / stores requesters: only their own papers.
            queryset = filter_by_branch_field(
                queryset,
                user,
                branch_field="requesting_branch",
                requested_branch_id=requesting_branch_id,
            )
            if bakery_id:
                queryset = queryset.filter(bakery_id=bakery_id)

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if needed_date:
            queryset = queryset.filter(needed_date=needed_date)
        return queryset.order_by("-needed_date", "-created_at")

    def _serialize(self, paper):
        paper = self.get_queryset().get(pk=paper.pk)
        return OrderPaperSerializer(paper).data

    def _ensure_can_create(self):
        if not user_can_create_order_papers(self.request.user):
            raise PermissionDenied(
                "Only branch or central stores staff can create order papers."
            )

    def _ensure_owns_requester(self, requesting_branch):
        user = self.request.user
        if user_has_global_branch_access(user):
            return
        staff_branch_id = get_staff_branch_id(user)
        if staff_branch_id is None or staff_branch_id != requesting_branch.id:
            raise PermissionDenied(
                "You can only create order papers for your assigned branch."
            )

    def create(self, request, *args, **kwargs):
        self._ensure_can_create()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._ensure_owns_requester(serializer.validated_data["requesting_branch"])
        paper = serializer.save()
        return Response(self._serialize(paper), status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        paper = self.get_object()
        self._ensure_can_create()
        self._ensure_owns_requester(paper.requesting_branch)
        serializer = self.get_serializer(paper, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        paper = serializer.save()
        return Response(self._serialize(paper))

    def _run_requester_transition(self, request, handler):
        paper = self.get_object()
        self._ensure_can_create()
        self._ensure_owns_requester(paper.requesting_branch)
        try:
            paper = handler(paper)
        except InvalidOrderPaperStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except EmptyOrderPaperError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._serialize(paper))

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._run_requester_transition(request, submit_order_paper)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        paper = self.get_object()
        user = request.user
        if user_can_manage_bakery_order_papers(user) and paper.status == (
            OrderPaperStatus.SUBMITTED
        ):
            # Bakery may cancel an unaccepted request.
            if not user_has_global_branch_access(user):
                if get_staff_branch_id(user) != paper.bakery_id:
                    raise PermissionDenied(
                        "You can only cancel order papers for your bakery."
                    )
            try:
                paper = cancel_order_paper(paper)
            except InvalidOrderPaperStateError as exc:
                return Response(
                    {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
                )
            return Response(self._serialize(paper))
        return self._run_requester_transition(request, cancel_order_paper)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        if not user_can_manage_bakery_order_papers(request.user):
            raise PermissionDenied(
                "Only bakery staff or HQ admins can accept order papers."
            )
        paper = self.get_object()
        if not user_has_global_branch_access(request.user):
            if get_staff_branch_id(request.user) != paper.bakery_id:
                raise PermissionDenied(
                    "You can only accept order papers for your bakery."
                )
        serializer = self.get_serializer(paper, data=request.data)
        serializer.is_valid(raise_exception=True)
        paper = serializer.save()
        return Response(self._serialize(paper))

    @action(detail=False, methods=["get"])
    def demand(self, request):
        """Totals by product and requesting branch for bakery planning."""
        if not user_can_manage_bakery_order_papers(request.user):
            raise PermissionDenied(
                "Only bakery staff or HQ admins can view order paper demand."
            )
        from collections import defaultdict
        from decimal import Decimal

        needed_date = request.query_params.get("needed_date")
        bakery_id = request.query_params.get("bakery")
        queryset = self.get_queryset().filter(
            status__in=(
                OrderPaperStatus.SUBMITTED,
                OrderPaperStatus.ACCEPTED,
            ),
            production_sheet__isnull=True,
        )
        if needed_date:
            queryset = queryset.filter(needed_date=needed_date)
        if bakery_id:
            queryset = queryset.filter(bakery_id=bakery_id)

        papers = list(queryset.prefetch_related("lines__product", "requesting_branch"))
        demand = order_paper_demand_totals(papers)
        product_names = {}
        branch_names = {}
        for paper in papers:
            branch_names[paper.requesting_branch_id] = paper.requesting_branch.name
            for line in paper.lines.all():
                product_names[line.product_id] = line.product.name

        items = [
            {
                "product_id": product_id,
                "product_name": product_names.get(product_id),
                "requesting_branch_id": branch_id,
                "requesting_branch_name": branch_names.get(branch_id),
                "quantity": quantity,
            }
            for (product_id, branch_id), quantity in sorted(
                demand.items(),
                key=lambda item: (
                    product_names.get(item[0][0], ""),
                    branch_names.get(item[0][1], ""),
                ),
            )
        ]
        by_product = defaultdict(lambda: Decimal("0"))
        for item in items:
            by_product[item["product_id"]] += item["quantity"]
        totals = [
            {
                "product_id": product_id,
                "product_name": product_names.get(product_id),
                "quantity": quantity,
            }
            for product_id, quantity in sorted(
                by_product.items(),
                key=lambda item: product_names.get(item[0], ""),
            )
        ]
        return Response(
            {
                "needed_date": needed_date,
                "paper_count": len(papers),
                "lines": items,
                "product_totals": totals,
            }
        )
