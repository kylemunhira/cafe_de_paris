from .branch_access import (
    user_can_access_bakery_transfers,
    user_can_access_cashier_invoices,
    user_can_access_central_invoices,
    user_can_access_dashboard,
    user_can_access_fiscal_receipts,
    user_can_access_grv,
    user_can_access_kitchen,
    user_can_access_management_console,
    user_can_access_pos,
    user_can_access_stores_transfers,
    user_can_approve_fiscal_receipt,
    user_can_collect_payment,
    user_can_create_purchase_orders,
    user_can_manage_branches,
    user_can_manage_suppliers,
    user_can_manage_users,
    user_has_global_branch_access,
    user_is_cashier,
    user_is_grv_staff,
    user_is_waiter,
)


def _show_customers_suppliers_nav(user):
    return user_can_access_pos(user) or user_can_manage_suppliers(user)


def nav_access(request):
    user = request.user
    management = user_can_access_management_console(user)
    return {
        "is_cashier_only": user_is_cashier(user),
        "is_waiter_only": user_is_waiter(user),
        "is_grv_staff_only": user_is_grv_staff(user),
        "show_management_nav": management,
        "show_dashboard_nav": user_can_access_dashboard(user),
        "show_pos_nav": user_can_access_pos(user),
        "show_kitchen_nav": management and user_can_access_kitchen(user),
        "show_bakery_transfers_nav": management and user_can_access_bakery_transfers(user),
        "show_stores_transfers_nav": management and user_can_access_stores_transfers(user),
        "show_central_invoices_nav": management and user_can_access_central_invoices(user),
        "show_grv_nav": user_can_access_grv(user)
        and (management or user_is_grv_staff(user)),
        "show_users_nav": management and user_can_manage_users(user),
        "can_manage_branches": management and user_can_manage_branches(user),
        "can_receive_on_transfers_page": user_has_global_branch_access(user),
        "can_mark_transfer_invoice_paid": user_can_access_stores_transfers(user),
        "can_mark_central_invoice_paid": user_can_access_central_invoices(user),
        "can_approve_fiscal_receipt": user_can_approve_fiscal_receipt(user),
        "show_fiscal_receipts_nav": user_can_access_fiscal_receipts(user),
        "show_invoices_nav": management or user_can_access_cashier_invoices(user),
        "show_customers_nav": management and user_can_access_pos(user),
        "show_customer_payment_nav": user_is_cashier(user) and user_can_collect_payment(user),
        "show_suppliers_nav": management and user_can_manage_suppliers(user),
        "show_customers_suppliers_nav": management and _show_customers_suppliers_nav(user),
        "show_purchase_orders_nav": management and user_can_create_purchase_orders(user),
        "show_supplier_statement_nav": management and user_can_create_purchase_orders(user),
        "show_stock_take_nav": management or user_is_cashier(user),
    }
