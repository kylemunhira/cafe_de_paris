import uuid

from django.db import models

from orders.models import Order


class SyncedClientOrder(models.Model):
    """Maps a desktop client UUID to a central order (idempotent sync)."""

    client_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="sync_record",
    )
    synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-synced_at"]

    def __str__(self):
        return f"Sync {self.client_id} → order #{self.order_id}"
