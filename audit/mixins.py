from .models import AuditAction
from .services import (
    action_for_update,
    diff_dicts,
    entity_label_for,
    record_audit,
    resolve_actor_branch,
    snapshot_fields,
)


class AuditedModelMixin:
    """
    Record update / delete / deactivate events for ModelViewSet mutations.

    Subclasses set:
      audit_entity_type: str
      audit_fields: iterable of field names
      audit_label_field: str | list | callable (default "name")
    """

    audit_entity_type = None
    audit_fields = ()
    audit_label_field = "name"

    def get_audit_snapshot(self, instance):
        return snapshot_fields(instance, self.audit_fields)

    def get_audit_label(self, instance):
        return entity_label_for(instance, self.audit_label_field)

    def get_audit_branch(self, instance):
        request = getattr(self, "request", None)
        actor = getattr(request, "user", None) if request else None
        return resolve_actor_branch(actor, entity=instance)

    def _audit_request_actor(self):
        request = getattr(self, "request", None)
        if request is None:
            return None, None
        return request, getattr(request, "user", None)

    def _record_update_audit(self, before, after, instance):
        changes = diff_dicts(before, after)
        if not changes:
            return
        request, actor = self._audit_request_actor()
        record_audit(
            action=action_for_update(before, after),
            entity_type=self.audit_entity_type,
            entity_id=instance.pk,
            entity_label=self.get_audit_label(instance),
            changes=changes,
            actor=actor,
            branch=self.get_audit_branch(instance),
            request=request,
        )

    def _record_delete_audit(self, instance, *, action=AuditAction.DELETE, changes=None):
        request, actor = self._audit_request_actor()
        snapshot = changes if changes is not None else self.get_audit_snapshot(instance)
        record_audit(
            action=action,
            entity_type=self.audit_entity_type,
            entity_id=instance.pk,
            entity_label=self.get_audit_label(instance),
            changes=snapshot,
            actor=actor,
            branch=self.get_audit_branch(instance),
            request=request,
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        before = self.get_audit_snapshot(instance)
        super().perform_update(serializer)
        after = self.get_audit_snapshot(serializer.instance)
        self._record_update_audit(before, after, serializer.instance)

    def perform_destroy(self, instance):
        self._record_delete_audit(instance)
        super().perform_destroy(instance)
