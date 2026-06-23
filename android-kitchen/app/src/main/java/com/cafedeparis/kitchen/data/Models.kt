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
)

data class OrderItem(
    val id: Int,
    val product_name: String,
    val quantity: String,
    val price: String,
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
)

data class LoginResponse(
    val token: String,
    val user: UserInfo,
    val branch: Branch,
)

data class PagedOrders(
    val results: List<KitchenOrder>,
)
