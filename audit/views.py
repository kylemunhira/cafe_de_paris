from django.db.models import Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from accounts.branch_access import (
    filter_by_branch_field,
    user_can_access_management_console,
)

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated]
    queryset = AuditEvent.objects.select_related("actor", "branch").all()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not user_can_access_management_console(request.user):
            raise PermissionDenied("Only management staff can view the audit log.")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        branch = params.get("branch")
        qs = filter_by_branch_field(qs, self.request.user, requested_branch_id=branch)

        action = params.get("action")
        if action:
            qs = qs.filter(action=action)

        entity_type = params.get("entity_type")
        if entity_type:
            qs = qs.filter(entity_type=entity_type)

        actor = params.get("actor")
        if actor:
            qs = qs.filter(actor_id=actor)

        date_from = params.get("from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = params.get("to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        search = (params.get("search") or params.get("q") or "").strip()
        if search:
            qs = qs.filter(
                Q(entity_label__icontains=search)
                | Q(entity_type__icontains=search)
                | Q(entity_id__icontains=search)
                | Q(actor__username__icontains=search)
                | Q(actor__first_name__icontains=search)
                | Q(actor__last_name__icontains=search)
            )

        return qs
