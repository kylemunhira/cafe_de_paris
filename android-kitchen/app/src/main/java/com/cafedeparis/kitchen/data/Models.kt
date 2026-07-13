package com.cafedeparis.kitchen.data

data class Branch(
    val id: Int,
    val name: String,
    val location: String? = null,
    val fiscalization_enabled: Boolean = false,
)

data class UserInfo(
    val id: Int,
    val username: String,
    val display_name: String,
    val role: String,
    val can_manage_fiscal_day: Boolean = false,
    val can_manage_dining_tables: Boolean = false,
    val can_collect_payment: Boolean = true,
    val kitchen_station: String? = null,
    val kitchen_station_display: String? = null,
)

data class OrderItemAddon(
    val name: String,
    val price: String,
)

data class OrderItem(
    val id: Int,
    val product_name: String,
    val quantity: String,
    val price: String,
    val notes: String = "",
    val addons: List<OrderItemAddon> = emptyList(),
)

data class OrderPaymentLine(
    val method: String,
    val amount: String,
    val method_display: String? = null,
    val currency_name: String? = null,
    val currency_symbol: String? = null,
)

data class KitchenOrder(
    val id: Int,
    val branch: Int,
    val branch_name: String,
    val order_type: String,
    val table_number: String,
    val total_amount: String,
    val status: String,
    val kitchen_status: String,
    val created_by_name: String?,
    val customer_name: String?,
    val created_at: String,
    val items: List<OrderItem>,
    val branch_fiscalization_enabled: Boolean = false,
    val customer: Int? = null,
    val payment_currency_name: String? = null,
    val payment_currency_symbol: String? = null,
    val amount_paid: String? = null,
    val receipt_number: String? = null,
    val paid_by_name: String? = null,
    val fiscal_approval_status: String? = null,
    val payment_method: String? = null,
    val customer_account_balance: String? = null,
    val payments: List<OrderPaymentLine> = emptyList(),
)

data class Customer(
    val id: Int,
    val full_name: String,
    val account_balance: String,
)

data class Supplier(
    val id: Int,
    val name: String,
    val is_active: Boolean = true,
)

data class LoginResponse(
    val token: String,
    val user: UserInfo,
    val branch: Branch,
    val can_access_kitchen: Boolean = false,
    val can_access_pos: Boolean = false,
)

data class ProductCategory(
    val id: Int,
    val name: String,
)

data class MenuAddon(
    val id: Int,
    val name: String,
    val selling_price: String,
    val is_active: Boolean = true,
)

data class MenuAddonGroup(
    val id: Int,
    val name: String,
    val selection_type: String,
    val addons: List<MenuAddon> = emptyList(),
)

data class Product(
    val id: Int,
    val name: String,
    val category: Int?,
    val category_name: String?,
    val selling_price: String,
    val addon_groups: List<MenuAddonGroup> = emptyList(),
) {
    fun hasActiveAddons(): Boolean =
        addon_groups.any { group -> group.addons.any { addon -> addon.is_active } }
}

data class Currency(
    val id: Int,
    val code: String,
    val name: String,
    val symbol: String,
    val is_base: Boolean,
    val is_active: Boolean = true,
    val current_rate: String?,
)

data class DiningTable(
    val id: Int,
    val branch: Int,
    val name: String,
    val sort_order: Int,
    val is_active: Boolean,
)

data class CartAddon(
    val id: Int,
    val name: String,
    val price: Double,
)

data class CartLine(
    val lineKey: String,
    val productId: Int,
    val name: String,
    val price: Double,
    var quantity: Double,
    val addons: List<CartAddon> = emptyList(),
    val notes: String = "",
)

fun cartLineKey(productId: Int, addonIds: List<Int>, notes: String): String {
    val sorted = addonIds.sorted().joinToString(",")
    return "$productId|$sorted|${notes.trim()}"
}

data class DayEndStockTakeCheck(
    val completed: Boolean,
    val detail: String,
    val draftInProgress: Boolean = false,
)

data class OrderSlipPrintOptions(
    val taxRate: Double = 15.5,
    val baseCurrencyCode: String? = null,
    val paymentOptions: List<PaymentOptionLine> = emptyList(),
)

data class PaymentOptionLine(
    val name: String,
    val symbol: String = "",
    val amount: Double,
)

data class DayEndReportResponse(
    val branchName: String,
    val branchLocation: String?,
    val baseCurrencyCode: String?,
    val printedAt: String,
    val report: org.json.JSONObject,
)

data class PagedOrders(
    val results: List<KitchenOrder>,
)
