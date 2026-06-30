from accounts.branch_access import (
    NO_BRANCH_ACCESS,
    filter_by_branch_field,
    resolve_branch_filter,
    user_can_access_pos,
    user_can_manage_branches,
    user_can_manage_dining_tables,
    user_can_manage_fiscal_day,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from zimra_fiscal.exceptions import ZimraConfigurationError, ZimraSubmissionError
from zimra_fiscal.fiscal_day import (
    close_fiscal_day,
    get_fiscal_day_status,
    open_fiscal_day,
)

from .dining_tables import ensure_default_dining_tables
from .models import Branch, DiningTable
from .serializers import BranchSerializer, DiningTableSerializer


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = resolve_branch_filter(self.request.user)
        if allowed is NO_BRANCH_ACCESS:
            return qs.none()
        if allowed is not None:
            return qs.filter(pk=allowed)
        return qs

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.action in ("fiscal_day_open", "fiscal_day_close"):
            return
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not user_can_manage_branches(request.user):
                raise PermissionDenied("You do not have permission to manage branches.")

    def _assert_fiscal_day_access(self, request, branch):
        if not user_can_manage_fiscal_day(request.user):
            raise PermissionDenied(
                "POS access on a fiscal branch is required for fiscal day operations."
            )
        allowed = resolve_branch_filter(request.user, branch.id)
        if allowed is NO_BRANCH_ACCESS:
            raise PermissionDenied("No branch assigned to this user.")
        if allowed is not None and allowed != branch.id:
            raise PermissionDenied("You do not have access to this branch.")
        if not branch.fiscalization_enabled:
            raise PermissionDenied("This branch is not configured for fiscalization.")

    def _fiscal_day_error_response(self, exc):
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=True, methods=["get"], url_path="fiscal-day/status")
    def fiscal_day_status(self, request, pk=None):
        branch = self.get_object()
        self._assert_fiscal_day_access(request, branch)
        try:
            payload = get_fiscal_day_status(branch)
        except ZimraConfigurationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ZimraSubmissionError as exc:
            return self._fiscal_day_error_response(exc)
        return Response(payload)

    @action(detail=True, methods=["post"], url_path="fiscal-day/open")
    def fiscal_day_open(self, request, pk=None):
        branch = self.get_object()
        self._assert_fiscal_day_access(request, branch)
        try:
            payload = open_fiscal_day(branch)
        except ZimraConfigurationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ZimraSubmissionError as exc:
            return self._fiscal_day_error_response(exc)
        return Response(payload)

    @action(detail=True, methods=["post"], url_path="fiscal-day/close")
    def fiscal_day_close(self, request, pk=None):
        branch = self.get_object()
        self._assert_fiscal_day_access(request, branch)
        try:
            payload = close_fiscal_day(branch)
        except ZimraConfigurationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ZimraSubmissionError as exc:
            return self._fiscal_day_error_response(exc)
        return Response(payload)


class DiningTableViewSet(viewsets.ModelViewSet):
    queryset = DiningTable.objects.select_related("branch").all()
    serializer_class = DiningTableSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        branch = self.request.query_params.get("branch")
        qs = filter_by_branch_field(qs, self.request.user, requested_branch_id=branch)
        active_only = self.request.query_params.get("active_only")
        if active_only in ("1", "true", "yes"):
            qs = qs.filter(is_active=True)
        return qs

    def list(self, request, *args, **kwargs):
        branch_id = request.query_params.get("branch")
        if branch_id:
            try:
                branch_pk = int(branch_id)
            except (TypeError, ValueError):
                branch_pk = None
            if branch_pk is not None:
                allowed = resolve_branch_filter(request.user, branch_pk)
                if allowed is not NO_BRANCH_ACCESS and (allowed is None or allowed == branch_pk):
                    branch = Branch.objects.filter(pk=branch_pk).first()
                    if branch:
                        ensure_default_dining_tables(branch)
        return super().list(request, *args, **kwargs)

    def _require_manage_dining_tables(self):
        if not user_can_manage_dining_tables(self.request.user):
            raise PermissionDenied(
                "Only branch managers can add or edit dining tables."
            )

    def _assert_branch_write_access(self, branch_id):
        allowed = resolve_branch_filter(self.request.user, branch_id)
        if allowed is NO_BRANCH_ACCESS:
            raise PermissionDenied("No branch assigned to this user.")
        if allowed is not None and allowed != branch_id:
            raise PermissionDenied("You do not have access to this branch.")

    def create(self, request, *args, **kwargs):
        self._require_manage_dining_tables()
        branch_id = request.data.get("branch")
        if branch_id is not None:
            self._assert_branch_write_access(int(branch_id))
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._require_manage_dining_tables()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._require_manage_dining_tables()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._require_manage_dining_tables()
        return super().destroy(request, *args, **kwargs)
