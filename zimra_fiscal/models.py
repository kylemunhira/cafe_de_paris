from django.db import models

from branches.models import Branch
from orders.models import Order


class BranchFiscalState(models.Model):
    branch = models.OneToOneField(
        Branch,
        on_delete=models.CASCADE,
        related_name="fiscal_state",
    )
    receipt_counter = models.PositiveIntegerField(default=0)
    receipt_global_no = models.PositiveIntegerField(default=0)
    invoice_sequence = models.PositiveIntegerField(default=0)
    invoice_sequence_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "branch fiscal state"
        verbose_name_plural = "branch fiscal states"

    def __str__(self):
        return f"Fiscal state for {self.branch}"


class FiscalReceiptStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUBMITTED = "submitted", "Submitted"
    ACCEPTED = "accepted", "Accepted"
    FAILED = "failed", "Failed"


class FiscalReceipt(models.Model):
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="fiscal_receipt",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="fiscal_receipts",
    )
    receipt_counter = models.PositiveIntegerField()
    receipt_global_no = models.PositiveIntegerField()
    invoice_no = models.CharField(max_length=32)
    payload = models.JSONField()
    device_branch_name = models.CharField(max_length=120, blank=True)
    device_serial_no = models.CharField(max_length=64, blank=True)
    fiscal_day_number = models.PositiveIntegerField(null=True, blank=True)
    fiscal_invoice_number = models.CharField(max_length=32, blank=True)
    qr_string = models.TextField(blank=True)
    qr_url = models.CharField(max_length=500, blank=True)
    verification_code = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20,
        choices=FiscalReceiptStatus.choices,
        default=FiscalReceiptStatus.PENDING,
    )
    zimra_response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Fiscal receipt {self.invoice_no} (order #{self.order_id})"
