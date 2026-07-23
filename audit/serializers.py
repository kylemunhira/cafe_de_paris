from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    changes_summary = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "created_at",
            "actor",
            "actor_name",
            "branch",
            "branch_name",
            "action",
            "action_display",
            "entity_type",
            "entity_id",
            "entity_label",
            "changes",
            "changes_summary",
            "request_path",
        ]

    def get_actor_name(self, obj):
        if not obj.actor_id:
            return ""
        user = obj.actor
        return user.get_full_name() or user.username

    def get_branch_name(self, obj):
        if not obj.branch_id:
            return ""
        return obj.branch.name

    def get_changes_summary(self, obj):
        changes = obj.changes or {}
        if not changes:
            return ""
        # Delete / deactivate often store a flat snapshot
        sample = next(iter(changes.values()), None)
        if isinstance(sample, dict) and ("from" in sample or "to" in sample):
            parts = []
            for field, delta in list(changes.items())[:8]:
                if isinstance(delta, dict):
                    parts.append(f"{field}: {delta.get('from')} → {delta.get('to')}")
                else:
                    parts.append(f"{field}")
            extra = len(changes) - len(parts)
            summary = "; ".join(parts)
            if extra > 0:
                summary = f"{summary}; +{extra} more"
            return summary[:300]
        keys = list(changes.keys())[:8]
        summary = ", ".join(keys)
        if len(changes) > len(keys):
            summary = f"{summary}; +{len(changes) - len(keys)} more"
        return summary[:300]
