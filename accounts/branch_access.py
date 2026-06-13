from django.db.models import Q

from branches.models import BranchType

from .models import StaffProfile, StaffRole

GLOBAL_ACCESS_USERNAMES = frozenset({"zimhope"})


def user_has_global_branch_access(user):
    """HQ Admins and designated global users can see all branches."""
    if not user or not user.is_authenticated:
        return False

    if user.username.casefold() in GLOBAL_ACCESS_USERNAMES:
        return True

    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False

    return profile.role == StaffRole.HQ_ADMIN


def get_staff_branch_id(user):
    if not user or not user.is_authenticated:
        return None
    try:
        return user.staff_profile.branch_id
    except StaffProfile.DoesNotExist:
        return None


NO_BRANCH_ACCESS = object()


def resolve_branch_filter(user, requested_branch_id=None):
    """
    Return the branch id queryset filters must use.
    None means no branch restriction (all branches).
    """
    if not user or not user.is_authenticated:
        return None

    if user_has_global_branch_access(user):
        if requested_branch_id in (None, ""):
            return None
        try:
            return int(requested_branch_id)
        except (TypeError, ValueError):
            return None

    branch_id = get_staff_branch_id(user)
    if branch_id is None:
        return NO_BRANCH_ACCESS
    return branch_id


def effective_branch_id(user, requested_branch_id=None):
    """Return None (all branches) or a branch id; raises ValueError if user has no branch."""
    branch_id = resolve_branch_filter(user, requested_branch_id)
    if branch_id is NO_BRANCH_ACCESS:
        raise ValueError("No branch assigned to this user.")
    return branch_id


def filter_by_branch_field(queryset, user, branch_field="branch", requested_branch_id=None):
    branch_id = resolve_branch_filter(user, requested_branch_id)
    if branch_id is NO_BRANCH_ACCESS:
        return queryset.none()
    if branch_id is None:
        return queryset
    return queryset.filter(**{f"{branch_field}_id": branch_id})


def filter_by_branch_participation(queryset, user, requested_branch_id=None):
    """For records tied to a branch as source and/or destination."""
    branch_id = resolve_branch_filter(user, requested_branch_id)
    if branch_id is NO_BRANCH_ACCESS:
        return queryset.none()
    if branch_id is None:
        return queryset
    return queryset.filter(
        Q(from_branch_id=branch_id) | Q(to_branch_id=branch_id)
    )


def get_staff_branch_type(user):
    if not user or not user.is_authenticated:
        return None
    try:
        return user.staff_profile.branch.branch_type
    except StaffProfile.DoesNotExist:
        return None


def user_can_manage_branches(user):
    """Only designated global users may create or edit branches."""
    if not user or not user.is_authenticated:
        return False
    return user.username.casefold() in GLOBAL_ACCESS_USERNAMES


def user_can_manage_users(user):
    """Only HQ admins and designated global users may manage staff accounts."""
    return user_has_global_branch_access(user)


def user_can_access_pos(user):
    """Retail branch staff use POS; central bakery and HQ locations do not."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return True
    return get_staff_branch_type(user) == BranchType.BRANCH


def user_can_access_bakery_transfers(user):
    """Central bakery staff, HQ admins, and designated global users."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return True
    return get_staff_branch_type(user) == BranchType.BAKERY


def user_can_access_grv(user):
    """Branch/HQ staff receive goods via GRV; global users use bakery transfers."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return False
    branch_type = get_staff_branch_type(user)
    return branch_type in (BranchType.BRANCH, BranchType.HQ)


def user_can_manage_outgoing_delivery(user, note):
    if not user_can_access_bakery_transfers(user):
        return False
    return note.from_branch.branch_type == BranchType.BAKERY


def user_can_receive_delivery(user, note):
    if user_has_global_branch_access(user):
        return True
    branch_id = get_staff_branch_id(user)
    return branch_id is not None and branch_id == note.to_branch_id


def user_can_approve_delivery(user, note):
    """Bakery staff approve outgoing notes; receiving branch approves on GRV."""
    return user_can_manage_outgoing_delivery(user, note) or user_can_receive_delivery(
        user, note
    )


def user_can_manage_suppliers(user):
    """HQ admins and designated global users manage supplier master data."""
    return user_has_global_branch_access(user)


def user_can_approve_purchase_orders(user):
    """HQ admins approve submitted purchase orders."""
    return user_has_global_branch_access(user)


def user_can_receive_purchase_order(user, purchase_order):
    """Receiving branch staff (or HQ admins) confirm goods receipt."""
    if user_has_global_branch_access(user):
        return True
    branch_id = get_staff_branch_id(user)
    return branch_id is not None and branch_id == purchase_order.branch_id
