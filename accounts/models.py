from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from branches.models import Branch
from catalog.models import PosStation

access_code_validator = RegexValidator(
    regex=r"^\d{4}$",
    message="Access code must be exactly 4 digits.",
)


class StaffRole(models.TextChoices):
    HQ_ADMIN = "hq_admin", "HQ Admin"
    BRANCH_MANAGER = "branch_manager", "Branch Manager"
    CASHIER = "cashier", "Cashier"
    WAITER = "waiter", "Waiter"
    BAKER = "baker", "Baker"
    STAFF = "staff", "Staff"


DESKTOP_POS_ROLES = frozenset(
    {
        StaffRole.CASHIER,
        StaffRole.BRANCH_MANAGER,
        StaffRole.WAITER,
    }
)


class StaffProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="staff_members",
    )
    role = models.CharField(
        max_length=20,
        choices=StaffRole.choices,
        default=StaffRole.CASHIER,
    )
    pos_access = models.BooleanField(
        default=False,
        help_text="Allows web and desktop POS for this user.",
    )
    kitchen_station = models.CharField(
        max_length=20,
        choices=PosStation.choices,
        blank=True,
        default="",
        help_text="Kitchen display filter — only orders for this prep station (bar or kitchen).",
    )
    access_code = models.CharField(
        max_length=4,
        unique=True,
        null=True,
        blank=True,
        validators=[access_code_validator],
        help_text="4-digit code for login and manager POS overrides.",
    )

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        display = self.user.get_full_name() or self.user.username
        return f"{display} ({self.get_role_display()}) @ {self.branch}"
