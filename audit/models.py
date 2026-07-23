from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    DEACTIVATE = "deactivate", "Deactivate"


class AuditEvent(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=20, choices=AuditAction.choices)
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.CharField(max_length=64)
    entity_label = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    request_path = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["branch", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} {self.entity_type}:{self.entity_id} by {self.actor_id}"
