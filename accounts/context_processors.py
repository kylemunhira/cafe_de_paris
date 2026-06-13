from .branch_access import (
    user_can_access_bakery_transfers,
    user_can_access_grv,
    user_can_access_pos,
    user_can_manage_branches,
    user_can_manage_suppliers,
    user_can_manage_users,
    user_can_approve_purchase_orders,
    user_has_global_branch_access,
)


def nav_access(request):
    user = request.user
    return {
        "show_pos_nav": user_can_access_pos(user),
        "show_bakery_transfers_nav": user_can_access_bakery_transfers(user),
        "show_grv_nav": user_can_access_grv(user),
        "show_users_nav": user_can_manage_users(user),
        "can_manage_branches": user_can_manage_branches(user),
        "can_receive_on_transfers_page": user_has_global_branch_access(user),
        "show_suppliers_nav": user_can_manage_suppliers(user),
        "can_approve_purchase_orders": user_can_approve_purchase_orders(user),
    }
