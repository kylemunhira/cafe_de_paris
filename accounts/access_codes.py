import re

from django.contrib.auth import get_user_model

from accounts.branch_access import (
    user_can_access_pos,
    user_has_global_branch_access,
    user_is_hq_admin,
    user_is_branch_manager,
)
from accounts.models import StaffProfile

User = get_user_model()

ACCESS_CODE_PATTERN = re.compile(r"^\d{4}$")


def normalize_access_code(value):
    return (value or "").strip()


def is_valid_access_code_format(value):
    return bool(ACCESS_CODE_PATTERN.fullmatch(normalize_access_code(value)))


def get_user_by_access_code(code):
    code = normalize_access_code(code)
    if not is_valid_access_code_format(code):
        return None
    try:
        profile = StaffProfile.objects.select_related("user").get(access_code=code)
    except StaffProfile.DoesNotExist:
        return None
    user = profile.user
    if not user.is_active:
        return None
    return user


def user_can_authorize_pos_override(user):
    """Branch managers and HQ/global users can authorize POS overrides."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not user.is_active:
        return False
    if user_has_global_branch_access(user):
        return True
    return user_is_branch_manager(user)


def resolve_access_code_user(code):
    """Return the active user for a 4-digit access code, or None."""
    return get_user_by_access_code(code)


def resolve_pos_override_authorizer(code):
    """
    Return a manager/HQ user for a valid override access code.

    Raises ValueError with a user-facing message when the code is present but invalid.
    Returns None when no code was provided.
    """
    code = normalize_access_code(code)
    if not code:
        return None
    user = get_user_by_access_code(code)
    if user is None or not user_can_authorize_pos_override(user):
        raise ValueError("Invalid manager access code.")
    return user


def resolve_bill_reprint_authorizer(code):
    """Return an HQ admin or superuser who may authorize another bill print."""
    code = normalize_access_code(code)
    if not code:
        raise ValueError("Admin access code is required to reprint a bill.")
    if not is_valid_access_code_format(code):
        raise ValueError("Access code must be exactly 4 digits.")

    user = get_user_by_access_code(code)
    if user is None or not (user.is_superuser or user_is_hq_admin(user)):
        raise ValueError("An admin or superuser access code is required to reprint a bill.")
    return user


def resolve_order_taker(code):
    """
    Return a POS-capable staff user for order attribution.

    Raises ValueError when the code is missing/invalid.
    """
    code = normalize_access_code(code)
    if not code:
        raise ValueError("Access code is required.")
    if not is_valid_access_code_format(code):
        raise ValueError("Access code must be exactly 4 digits.")
    user = get_user_by_access_code(code)
    if user is None or not user_can_access_pos(user):
        raise ValueError("Invalid access code.")
    return user
