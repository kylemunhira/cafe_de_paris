package com.cafedeparis.kitchen.data

import android.content.Context

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

    var userRole: String?
        get() = prefs.getString(KEY_USER_ROLE, null)
        set(value) = prefs.edit().putString(KEY_USER_ROLE, value).apply()

    var canCollectPayment: Boolean
        get() = prefs.getBoolean(KEY_CAN_COLLECT_PAYMENT, true)
        set(value) = prefs.edit().putBoolean(KEY_CAN_COLLECT_PAYMENT, value).apply()

    var kitchenStation: String?
        get() = prefs.getString(KEY_KITCHEN_STATION, null)
        set(value) = prefs.edit().putString(KEY_KITCHEN_STATION, value?.trim()).apply()

    var kitchenStationDisplay: String?
        get() = prefs.getString(KEY_KITCHEN_STATION_DISPLAY, null)
        set(value) = prefs.edit().putString(KEY_KITCHEN_STATION_DISPLAY, value?.trim()).apply()

    var canAccessKitchen: Boolean
        get() = prefs.getBoolean(KEY_CAN_ACCESS_KITCHEN, false)
        set(value) = prefs.edit().putBoolean(KEY_CAN_ACCESS_KITCHEN, value).apply()

    var canAccessPos: Boolean
        get() = prefs.getBoolean(KEY_CAN_ACCESS_POS, false)
        set(value) = prefs.edit().putBoolean(KEY_CAN_ACCESS_POS, value).apply()

    var fiscalizationEnabled: Boolean
        get() = prefs.getBoolean(KEY_FISCALIZATION_ENABLED, false)
        set(value) = prefs.edit().putBoolean(KEY_FISCALIZATION_ENABLED, value).apply()

    var canManageDiningTables: Boolean
        get() = prefs.getBoolean(KEY_CAN_MANAGE_DINING_TABLES, false)
        set(value) = prefs.edit().putBoolean(KEY_CAN_MANAGE_DINING_TABLES, value).apply()

    var printerAddress: String?
        get() = prefs.getString(KEY_PRINTER_ADDRESS, null)
        set(value) = prefs.edit().putString(KEY_PRINTER_ADDRESS, value?.trim()).apply()

    val isLoggedIn: Boolean
        get() = !token.isNullOrBlank() && branchId > 0

    fun shouldOpenPos(): Boolean {
        if (!canAccessPos) return false
        return when (userRole) {
            "cashier", "branch_manager", "waiter" -> true
            else -> canAccessPos && !canAccessKitchen
        }
    }

    fun saveLogin(response: LoginResponse) {
        token = response.token
        branchId = response.branch.id
        branchName = response.branch.name
        displayName = response.user.display_name
        userRole = response.user.role
        canAccessKitchen = response.can_access_kitchen
        canAccessPos = response.can_access_pos
        canCollectPayment = response.user.can_collect_payment
        kitchenStation = response.user.kitchen_station
        kitchenStationDisplay = response.user.kitchen_station_display
        fiscalizationEnabled = response.branch.fiscalization_enabled
        canManageDiningTables = response.user.can_manage_dining_tables
    }

    fun clearLogin() {
        prefs.edit()
            .remove(KEY_TOKEN)
            .remove(KEY_BRANCH_ID)
            .remove(KEY_BRANCH_NAME)
            .remove(KEY_DISPLAY_NAME)
            .remove(KEY_USER_ROLE)
            .remove(KEY_CAN_ACCESS_KITCHEN)
            .remove(KEY_CAN_ACCESS_POS)
            .remove(KEY_CAN_COLLECT_PAYMENT)
            .remove(KEY_KITCHEN_STATION)
            .remove(KEY_KITCHEN_STATION_DISPLAY)
            .remove(KEY_FISCALIZATION_ENABLED)
            .remove(KEY_CAN_MANAGE_DINING_TABLES)
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
        private const val KEY_USER_ROLE = "user_role"
        private const val KEY_CAN_ACCESS_KITCHEN = "can_access_kitchen"
        private const val KEY_CAN_ACCESS_POS = "can_access_pos"
        private const val KEY_CAN_COLLECT_PAYMENT = "can_collect_payment"
        private const val KEY_KITCHEN_STATION = "kitchen_station"
        private const val KEY_KITCHEN_STATION_DISPLAY = "kitchen_station_display"
        private const val KEY_FISCALIZATION_ENABLED = "fiscalization_enabled"
        private const val KEY_CAN_MANAGE_DINING_TABLES = "can_manage_dining_tables"
        private const val KEY_PRINTER_ADDRESS = "printer_address"
        private const val KEY_PRINTED_IDS = "printed_order_ids"
    }
}

object JsonParsers {
    fun parseLoginResponse(body: String): LoginResponse {
        val json = org.json.JSONObject(body)
        val user = json.getJSONObject("user")
        val branch = json.getJSONObject("branch")
        return LoginResponse(
            token = json.getString("token"),
            user = UserInfo(
                id = user.getInt("id"),
                username = user.getString("username"),
                display_name = user.getString("display_name"),
                role = user.getString("role"),
                can_manage_fiscal_day = user.optBoolean("can_manage_fiscal_day", false),
                can_manage_dining_tables = user.optBoolean("can_manage_dining_tables", false),
                can_collect_payment = user.optBoolean("can_collect_payment", true),
                kitchen_station = user.optString("kitchen_station", null)?.takeIf { it.isNotBlank() },
                kitchen_station_display = user.optString("kitchen_station_display", null)?.takeIf { it.isNotBlank() },
            ),
            branch = Branch(
                id = branch.getInt("id"),
                name = branch.getString("name"),
                location = branch.optString("location", null),
                fiscalization_enabled = branch.optBoolean("fiscalization_enabled", false),
            ),
            can_access_kitchen = json.optBoolean("can_access_kitchen", false),
            can_access_pos = json.optBoolean("can_access_pos", false),
        )
    }

    fun parseOrders(body: String): List<KitchenOrder> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            parseOrder(results.getJSONObject(index))
        }
    }

    fun parseOrder(body: String): KitchenOrder = parseOrder(org.json.JSONObject(body))

    fun parseProducts(body: String): List<Product> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            parseProduct(results.getJSONObject(index))
        }
    }

    private fun parseProduct(item: org.json.JSONObject): Product {
        val addonGroupsJson = item.optJSONArray("addon_groups") ?: org.json.JSONArray()
        val addonGroups = (0 until addonGroupsJson.length()).map { groupIndex ->
            val group = addonGroupsJson.getJSONObject(groupIndex)
            val addonsJson = group.optJSONArray("addons") ?: org.json.JSONArray()
            val addons = (0 until addonsJson.length()).map { addonIndex ->
                val addon = addonsJson.getJSONObject(addonIndex)
                MenuAddon(
                    id = addon.getInt("id"),
                    name = addon.getString("name"),
                    selling_price = addon.optString("selling_price", "0"),
                    is_active = addon.optBoolean("is_active", true),
                )
            }
            MenuAddonGroup(
                id = group.getInt("id"),
                name = group.getString("name"),
                selection_type = group.optString("selection_type", "multiple"),
                addons = addons,
            )
        }
        return Product(
            id = item.getInt("id"),
            name = item.getString("name"),
            category = item.optInt("category").takeIf { item.has("category") && !item.isNull("category") },
            category_name = item.optString("category_name", null),
            selling_price = item.optString("selling_price", "0"),
            addon_groups = addonGroups,
        )
    }

    fun parseCategories(body: String): List<ProductCategory> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            ProductCategory(
                id = item.getInt("id"),
                name = item.getString("name"),
            )
        }
    }

    fun parseCurrencies(body: String): List<Currency> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            Currency(
                id = item.getInt("id"),
                code = item.optString("code", ""),
                name = item.getString("name"),
                symbol = item.optString("symbol", ""),
                is_base = item.optBoolean("is_base", false),
                is_active = item.optBoolean("is_active", true),
                current_rate = item.optString("current_rate", null),
            )
        }
    }

    private fun parseOrder(json: org.json.JSONObject): KitchenOrder {
        val itemsJson = json.optJSONArray("items") ?: org.json.JSONArray()
        val items = (0 until itemsJson.length()).map { i ->
            val item = itemsJson.getJSONObject(i)
            val addonsJson = item.optJSONArray("addons") ?: org.json.JSONArray()
            val addons = (0 until addonsJson.length()).map { addonIndex ->
                val addon = addonsJson.getJSONObject(addonIndex)
                OrderItemAddon(
                    name = addon.getString("name"),
                    price = addon.optString("price", "0"),
                )
            }
            OrderItem(
                id = item.getInt("id"),
                product_name = item.getString("product_name"),
                quantity = item.optString("quantity", "0"),
                price = item.optString("price", "0"),
                notes = item.optString("notes", ""),
                addons = addons,
            )
        }
        val paymentsJson = json.optJSONArray("payments") ?: org.json.JSONArray()
        val payments = (0 until paymentsJson.length()).map { i ->
            val payment = paymentsJson.getJSONObject(i)
            OrderPaymentLine(
                method = payment.optString("method", "cash"),
                amount = payment.optString("amount", "0"),
                method_display = payment.optString("method_display", null),
                currency_name = payment.optString("currency_name", null),
                currency_symbol = payment.optString("currency_symbol", null),
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
            customer = json.optInt("customer").takeIf { json.has("customer") && !json.isNull("customer") },
            payment_currency_name = json.optString("payment_currency_name", null),
            payment_currency_symbol = json.optString("payment_currency_symbol", null),
            amount_paid = json.optString("amount_paid", null),
            receipt_number = json.optString("receipt_number", null),
            paid_by_name = json.optString("paid_by_name", null),
            fiscal_approval_status = json.optString("fiscal_approval_status", null),
            payment_method = json.optString("payment_method", null),
            customer_account_balance = json.optString("customer_account_balance", null),
            payments = payments,
        )
    }

    fun parseSuppliers(body: String): List<Supplier> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            Supplier(
                id = item.getInt("id"),
                name = item.getString("name"),
                is_active = item.optBoolean("is_active", true),
            )
        }
    }

    fun parseCustomers(body: String): List<Customer> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            parseCustomerObject(results.getJSONObject(index))
        }
    }

    fun parseCustomer(body: String): Customer {
        return parseCustomerObject(org.json.JSONObject(body))
    }

    private fun parseCustomerObject(item: org.json.JSONObject): Customer {
        return Customer(
            id = item.getInt("id"),
            full_name = item.optString("full_name", item.optString("first_name", "Customer")),
            account_balance = jsonNumberAsString(item, "account_balance", "0"),
            credit_limit = jsonNumberAsString(item, "credit_limit", "0"),
        )
    }

    private fun jsonNumberAsString(
        json: org.json.JSONObject,
        key: String,
        fallback: String,
    ): String {
        if (!json.has(key) || json.isNull(key)) return fallback
        return when (val raw = json.get(key)) {
            is Number -> raw.toString()
            else -> raw.toString().ifBlank { fallback }
        }
    }

    fun parseDiningTables(body: String): List<DiningTable> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            DiningTable(
                id = item.getInt("id"),
                branch = item.getInt("branch"),
                name = item.getString("name"),
                sort_order = item.optInt("sort_order", 0),
                is_active = item.optBoolean("is_active", true),
            )
        }
    }

    fun parseDayEndStockTakeCheck(body: String): DayEndStockTakeCheck {
        val json = org.json.JSONObject(body)
        return DayEndStockTakeCheck(
            completed = json.optBoolean("completed", false),
            detail = json.optString("detail", ""),
            draftInProgress = json.optBoolean("draft_in_progress", false),
        )
    }

    fun parseDayEndReport(body: String): DayEndReportResponse {
        val json = org.json.JSONObject(body)
        val branch = json.getJSONObject("branch")
        val base = json.optJSONObject("base_currency")
        return DayEndReportResponse(
            branchName = branch.getString("name"),
            branchLocation = branch.optString("location", null),
            baseCurrencyCode = base?.optString("code", null),
            printedAt = json.optString("printed_at", ""),
            report = json.getJSONObject("report"),
        )
    }

    fun parseStockTakes(body: String): List<StockTake> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            parseStockTakeObject(results.getJSONObject(index))
        }
    }

    fun parseStockTake(body: String): StockTake {
        return parseStockTakeObject(org.json.JSONObject(body))
    }

    private fun parseStockTakeObject(json: org.json.JSONObject): StockTake {
        val linesJson = json.optJSONArray("lines") ?: org.json.JSONArray()
        val lines = (0 until linesJson.length()).map { index ->
            val line = linesJson.getJSONObject(index)
            val counted = if (line.isNull("counted_quantity")) {
                null
            } else {
                line.optString("counted_quantity", null)
            }
            StockTakeLine(
                id = line.getInt("id"),
                productId = line.optInt("product", 0),
                productName = line.optString("product_name", "Product"),
                categoryName = line.optString("category_name", null),
                countedQuantity = counted,
            )
        }
        return StockTake(
            id = json.getInt("id"),
            stockTakeType = json.optString("stock_take_type", "daily"),
            stockTakeTypeDisplay = json.optString(
                "stock_take_type_display",
                json.optString("stock_take_type", "Daily"),
            ),
            status = json.optString("status", "draft"),
            countDate = json.optString("count_date", ""),
            lines = lines,
        )
    }

    fun parseCustomerDeposit(body: String): CustomerDepositResult {
        val json = org.json.JSONObject(body)
        val transaction = json.optJSONObject("transaction")
            ?: throw IllegalArgumentException(
                "Server did not confirm the deposit. Check the app server URL matches the portal.",
            )
        val transactionId = transaction.optInt("id", 0)
        if (transactionId <= 0) {
            throw IllegalArgumentException(
                "Server did not confirm the deposit. Check the app server URL matches the portal.",
            )
        }
        val balance = when {
            json.isNull("account_balance") -> transaction.optString("balance_after", "0")
            else -> {
                val raw = json.get("account_balance")
                when (raw) {
                    is Number -> raw.toString()
                    else -> raw.toString()
                }
            }
        }
        val amount = if (transaction.isNull("amount")) {
            null
        } else {
            when (val raw = transaction.get("amount")) {
                is Number -> raw.toString()
                else -> raw.toString()
            }
        }
        return CustomerDepositResult(
            accountBalance = balance,
            transactionId = transactionId,
            amount = amount,
        )
    }
}
