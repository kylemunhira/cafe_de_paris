from django.db import models


class BranchType(models.TextChoices):
    HQ = "hq", "Headquarters"
    BRANCH = "branch", "Branch"
    BAKERY = "bakery", "Bakery"
    STORES = "stores", "Central Stores"


class Branch(models.Model):
    name = models.CharField(max_length=120)
    code = models.CharField(
        max_length=3,
        blank=True,
        help_text="3-letter receipt prefix, e.g. HIG for Highland, CHU for Churchill.",
    )
    location = models.CharField(max_length=255, blank=True)
    branch_type = models.CharField(
        max_length=20,
        choices=BranchType.choices,
        default=BranchType.BRANCH,
    )
    is_active = models.BooleanField(default=True)
    fiscalization_enabled = models.BooleanField(
        default=False,
        help_text="When enabled, sales from this branch are sent to the fiscal device.",
    )
    zimra_device_id = models.CharField(
        max_length=32,
        blank=True,
        help_text="ZIMRA fiscal device ID used in submit_receipt API path.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_branch_type_display()})"
