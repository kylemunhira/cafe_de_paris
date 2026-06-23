package com.cafedeparis.kitchen.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

class SessionManager(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var token: String?
        get() = prefs.getString(KEY_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_TOKEN, value).apply()

    var branchId: Int
        get() = prefs.getInt(KEY_BRANCH_ID, -1)
        set(value) = prefs.edit().putInt(KEY_BRANCH_ID, value).apply()

    var branchName: String?
        get() = prefs.getString(KEY_BRANCH_NAME, null)
        set(value) = prefs.edit().putString(KEY_BRANCH_NAME, value).apply()

    var displayName: String?
        get() = prefs.getString(KEY_DISPLAY_NAME, null)
        set(value) = prefs.edit().putString(KEY_DISPLAY_NAME, value).apply()

    var printerAddress: String?
        get() = prefs.getString(KEY_PRINTER_ADDRESS, null)
        set(value) = prefs.edit().putString(KEY_PRINTER_ADDRESS, value?.trim()).apply()

    val isLoggedIn: Boolean
        get() = !token.isNullOrBlank() && branchId > 0

    fun saveLogin(response: LoginResponse) {
        token = response.token
        branchId = response.branch.id
        branchName = response.branch.name
        displayName = response.user.display_name
    }

    fun clearLogin() {
        prefs.edit()
            .remove(KEY_TOKEN)
            .remove(KEY_BRANCH_ID)
            .remove(KEY_BRANCH_NAME)
            .remove(KEY_DISPLAY_NAME)
            .apply()
    }

    fun markPrinted(orderId: Int) {
        val ids = getPrintedOrderIds().toMutableSet()
        ids.add(orderId)
        prefs.edit().putStringSet(KEY_PRINTED_IDS, ids.map { it.toString() }.toSet()).apply()
    }

    fun getPrintedOrderIds(): Set<Int> {
        return prefs.getStringSet(KEY_PRINTED_IDS, emptySet())
            ?.mapNotNull { it.toIntOrNull() }
            ?.toSet()
            ?: emptySet()
    }

    fun clearPrintedOrderIds() {
        prefs.edit().remove(KEY_PRINTED_IDS).apply()
    }

    companion object {
        private const val PREFS_NAME = "kitchen_session"
        private const val KEY_TOKEN = "token"
        private const val KEY_BRANCH_ID = "branch_id"
        private const val KEY_BRANCH_NAME = "branch_name"
        private const val KEY_DISPLAY_NAME = "display_name"
        private const val KEY_PRINTER_ADDRESS = "printer_address"
        private const val KEY_PRINTED_IDS = "printed_order_ids"
    }
}

object JsonParsers {
    fun parseLoginResponse(body: String): LoginResponse {
        val json = JSONObject(body)
        val user = json.getJSONObject("user")
        val branch = json.getJSONObject("branch")
        return LoginResponse(
            token = json.getString("token"),
            user = UserInfo(
                id = user.getInt("id"),
                username = user.getString("username"),
                display_name = user.getString("display_name"),
                role = user.getString("role"),
            ),
            branch = Branch(
                id = branch.getInt("id"),
                name = branch.getString("name"),
                location = branch.optString("location", null),
                fiscalization_enabled = branch.optBoolean("fiscalization_enabled", false),
            ),
        )
    }

    fun parseOrders(body: String): List<KitchenOrder> {
        val json = JSONObject(body)
        val results = json.optJSONArray("results") ?: JSONArray()
        return (0 until results.length()).map { index ->
            parseOrder(results.getJSONObject(index))
        }
    }

    private fun parseOrder(json: JSONObject): KitchenOrder {
        val itemsJson = json.optJSONArray("items") ?: JSONArray()
        val items = (0 until itemsJson.length()).map { i ->
            val item = itemsJson.getJSONObject(i)
            OrderItem(
                id = item.getInt("id"),
                product_name = item.getString("product_name"),
                quantity = item.optString("quantity", "0"),
                price = item.optString("price", "0"),
            )
        }
        return KitchenOrder(
            id = json.getInt("id"),
            branch = json.getInt("branch"),
            branch_name = json.optString("branch_name", ""),
            order_type = json.optString("order_type", "takeaway"),
            table_number = json.optString("table_number", ""),
            total_amount = json.optString("total_amount", "0"),
            status = json.optString("status", "open"),
            kitchen_status = json.optString("kitchen_status", "pending"),
            created_by_name = json.optString("created_by_name", null),
            customer_name = json.optString("customer_name", null),
            created_at = json.optString("created_at", ""),
            items = items,
            branch_fiscalization_enabled = json.optBoolean("branch_fiscalization_enabled", false),
        )
    }
}
