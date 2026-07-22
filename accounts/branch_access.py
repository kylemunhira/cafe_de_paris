from django.db.models import Q

from branches.models import BranchType

from .models import DESKTOP_POS_ROLES, StaffProfile, StaffRole

GLOBAL_ACCESS_USERNAMES = frozenset({"zimhope"})


def user_has_global_branch_access(user):
    """HQ Admins and designated global users can see all branches."""
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

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


def user_is_hq_admin(user):
    """HQ admin — full management console with global branch visibility."""
    if not user or not user.is_authenticated:
        return False
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role == StaffRole.HQ_ADMIN


def user_is_branch_manager(user):
    """Branch manager — operational console without HQ dashboard or stores transfers."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return False
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role == StaffRole.BRANCH_MANAGER


def user_can_access_dashboard(user):
    """HQ and global users only — not cashiers, GRV staff, or branch managers."""
    if not user_can_access_management_console(user):
        return False
    return not user_is_branch_manager(user)


def user_can_manage_users(user):
    """Only HQ admins and designated global users may manage staff accounts."""
    if user_is_branch_manager(user):
        return False
    return user_has_global_branch_access(user)


def user_is_waiter(user):
    """Branch waiter — POS order entry without payment collection."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return False
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role == StaffRole.WAITER


def get_staff_kitchen_station(user):
    if not user or not user.is_authenticated:
        return ""
    try:
        return user.staff_profile.kitchen_station or ""
    except StaffProfile.DoesNotExist:
        return ""


def user_can_access_pos(user):
    """POS access: cashiers, waiters, HQ admins, global users, or explicit pos_access flag."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return True
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    if profile.role in (StaffRole.CASHIER, StaffRole.WAITER):
        return True
    return profile.pos_access


def user_can_collect_payment(user):
    """Collect payment / issue receipts — not available to waiters."""
    if not user or not user.is_authenticated:
        return False
    if user_is_waiter(user):
        return False
    return user_can_access_pos(user)


def user_can_use_desktop_pos(user):
    """Offline desktop POS — cashiers, waiters, and branch managers."""
    if not user_can_access_pos(user):
        return False
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role in DESKTOP_POS_ROLES


def user_can_access_kitchen(user):
    """Kitchen display for branch/HQ staff preparing POS orders."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return True
    branch_type = get_staff_branch_type(user)
    if branch_type is None:
        return user.is_staff or user.is_superuser
    return branch_type in (BranchType.BRANCH, BranchType.HQ)


def user_can_access_bakery_transfers(user):
    """Central bakery staff, HQ admins, and designated global users."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return True
    return get_staff_branch_type(user) == BranchType.BAKERY


def user_can_access_stores_transfers(user):
    """Central stores staff, HQ admins, and designated global users."""
    if not user or not user.is_authenticated:
        return False
    if user_is_branch_manager(user) or user_is_grv_staff(user):
        return False
    if user_has_global_branch_access(user):
        return True
    return get_staff_branch_type(user) == BranchType.STORES


def user_can_access_central_invoices(user):
    """Central stores staff selling bakery products to external customers."""
    return user_can_access_stores_transfers(user)


def user_is_cashier(user):
    """Branch cashier — limited web console (POS and fiscal documents only)."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return False
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role == StaffRole.CASHIER


def user_is_grv_staff(user):
    """Branch/HQ/stores staff role — limited web console (GRV only)."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return False
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role == StaffRole.STAFF


def user_is_baker(user):
    """Bakery staff — limited web console (stock take, production, transfers)."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return False
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role == StaffRole.BAKER


def user_can_access_management_console(user):
    """Full management console — not cashiers, waiters, bakers, or GRV-only staff."""
    if not user or not user.is_authenticated:
        return False
    return (
        not user_is_cashier(user)
        and not user_is_waiter(user)
        and not user_is_baker(user)
        and not user_is_grv_staff(user)
    )


def user_can_access_cashier_invoices(user):
    """Cashiers on fiscal branches may view proforma invoices."""
    return user_is_cashier(user) and user_can_access_fiscal_receipts(user)


def user_can_access_grv(user):
    """Branch/HQ/stores staff and HQ admins receive goods via GRV; other global users use transfer pages."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user_is_cashier(user):
        return False
    if user_is_hq_admin(user):
        return True
    if user_has_global_branch_access(user):
        return False
    branch_type = get_staff_branch_type(user)
    return branch_type in (BranchType.BRANCH, BranchType.HQ, BranchType.STORES)


def user_can_manage_outgoing_delivery(user, note):
    if note.from_branch.branch_type == BranchType.BAKERY:
        return user_can_access_bakery_transfers(user)
    if note.from_branch.branch_type == BranchType.STORES:
        return user_can_access_stores_transfers(user)
    return False


def user_can_receive_delivery(user, note):
    if user_has_global_branch_access(user):
        return True
    branch_id = get_staff_branch_id(user)
    return branch_id is not None and branch_id == note.to_branch_id


def user_can_approve_delivery(user, note):
    """Receiving branch approves bakery deliveries; stores staff approve-and-deliver."""
    from branches.models import BranchType

    if note.from_branch.branch_type == BranchType.BAKERY:
        return user_can_receive_delivery(user, note)
    return user_can_manage_outgoing_delivery(user, note) or user_can_receive_delivery(
        user, note
    )


def user_can_manage_suppliers(user):
    """HQ admins and designated global users manage supplier master data."""
    return user_has_global_branch_access(user)


def user_can_create_purchase_orders(user):
    """HQ admins and central stores staff record purchases (stock added immediately)."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return True
    if get_staff_branch_type(user) != BranchType.STORES:
        return False
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role in (StaffRole.BRANCH_MANAGER, StaffRole.STAFF)


def user_can_manage_dining_tables(user):
    """HQ admins and branch managers configure POS dining tables."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return True
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role == StaffRole.BRANCH_MANAGER


def user_can_approve_purchase_orders(user):
    """HQ admins approve submitted purchase orders."""
    return user_has_global_branch_access(user)


def user_can_approve_fiscal_receipt(user):
    """Branch managers and HQ admins approve proforma invoices for fiscalization."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return True
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.role == StaffRole.BRANCH_MANAGER


def user_can_manage_fiscal_day(user):
    """POS staff on a fiscal branch may check status and open/close the fiscal day."""
    if not user or not user.is_authenticated:
        return False
    if user_has_global_branch_access(user):
        return True
    if user_is_waiter(user) or not user_can_access_pos(user):
        return False
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.branch.fiscalization_enabled


def user_can_access_fiscal_receipts(user):
    """Receipts nav: fiscal branches, or HQ/global users when any branch is fiscal."""
    if not user or not user.is_authenticated:
        return False
    if user_is_waiter(user):
        return False
    if user_has_global_branch_access(user):
        from branches.models import Branch

        return Branch.objects.filter(
            is_active=True,
            fiscalization_enabled=True,
        ).exists()
    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return False
    return profile.branch.fiscalization_enabled


def user_can_receive_purchase_order(user, purchase_order):
    """Receiving branch staff (or HQ admins) confirm goods receipt."""
    if user_has_global_branch_access(user):
        return True
    branch_id = get_staff_branch_id(user)
    return branch_id is not None and branch_id == purchase_order.branch_id
