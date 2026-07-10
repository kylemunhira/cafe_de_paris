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
    allow_negative_stock = models.BooleanField(
        default=False,
        help_text=(
            "When enabled, POS sales may deduct stock below zero. "
            "Transfers and production still require sufficient stock."
        ),
    )
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


class DiningTable(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="dining_tables",
    )
    name = models.CharField(max_length=20)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "name"],
                name="uniq_dining_table_per_branch",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.branch.name})"
