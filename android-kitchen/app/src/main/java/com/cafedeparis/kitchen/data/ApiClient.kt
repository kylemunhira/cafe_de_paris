package com.cafedeparis.kitchen.data

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

class ApiException(val statusCode: Int, message: String) : Exception(message)

class ApiClient(
    private val session: SessionManager,
    private val config: AppConfig,
) {

    fun login(username: String, password: String): LoginResponse {
        val payload = JSONObject()
            .put("username", username)
            .put("password", password)
        val body = postJson("${config.serverUrl}/api/auth/mobile-login/", payload, authToken = null)
        return JsonParsers.parseLoginResponse(body)
    }

    fun fetchOpenOrders(): List<KitchenOrder> {
        val token = session.token ?: throw ApiException(401, "Not logged in")
        val branchId = session.branchId
        val url =
            "${config.serverUrl}/api/orders/?status=open&branch=$branchId&page_size=500"
        val body = getJson(url, token)
        return JsonParsers.parseOrders(body)
    }

    fun fetchProducts(): List<Product> {
        val token = requireToken()
        val url = "${config.serverUrl}/api/products/?pos_catalog=true&page_size=1000"
        val body = getJson(url, token)
        return JsonParsers.parseProducts(body)
    }

    fun fetchCategories(): List<ProductCategory> {
        val token = requireToken()
        val url = "${config.serverUrl}/api/categories/?page_size=200"
        val body = getJson(url, token)
        return JsonParsers.parseCategories(body)
    }

    fun fetchCurrencies(): List<Currency> {
        val token = requireToken()
        val url = "${config.serverUrl}/api/currencies/?page_size=50"
        val body = getJson(url, token)
        return JsonParsers.parseCurrencies(body)
    }

    fun fetchCustomers(): List<Customer> {
        val token = requireToken()
        val url = "${config.serverUrl}/api/customers/?page_size=500"
        val body = getJson(url, token)
        return JsonParsers.parseCustomers(body)
    }

    fun fetchSuppliers(): List<Supplier> {
        val token = requireToken()
        val url = "${config.serverUrl}/api/suppliers/?active_only=true&page_size=500"
        val body = getJson(url, token)
        return JsonParsers.parseSuppliers(body)
    }

    fun createExpense(
        expenseDate: String,
        description: String,
        amount: String,
        currencyId: Int,
        supplierId: Int? = null,
    ) {
        val token = requireToken()
        val payload = JSONObject()
            .put("branch", session.branchId)
            .put("expense_date", expenseDate)
            .put("description", description)
            .put("amount", amount)
            .put("currency", currencyId)
        if (supplierId != null) {
            payload.put("supplier", supplierId)
        }
        postJson("${config.serverUrl}/api/expenses/", payload, token)
    }

    fun fetchDiningTables(): List<DiningTable> {
        val token = requireToken()
        val branchId = session.branchId
        val url = "${config.serverUrl}/api/dining-tables/?branch=$branchId&active_only=true&page_size=500"
        val body = getJson(url, token)
        return JsonParsers.parseDiningTables(body)
    }

    fun checkDayEndStockTake(date: String): DayEndStockTakeCheck {
        val token = requireToken()
        val branchId = session.branchId
        val url = "${config.serverUrl}/api/stock-takes/day-end-check/?branch=$branchId&date=$date"
        val body = getJson(url, token)
        return JsonParsers.parseDayEndStockTakeCheck(body)
    }

    fun fetchStockTakes(type: String, status: String = "draft"): List<StockTake> {
        val token = requireToken()
        val branchId = session.branchId
        val url =
            "${config.serverUrl}/api/stock-takes/?branch=$branchId&stock_take_type=$type&status=$status&page_size=100"
        val body = getJson(url, token)
        return JsonParsers.parseStockTakes(body)
    }

    fun fetchStockTake(stockTakeId: Int): StockTake {
        val token = requireToken()
        val body = getJson("${config.serverUrl}/api/stock-takes/$stockTakeId/", token)
        return JsonParsers.parseStockTake(body)
    }

    fun createStockTake(type: String, countDate: String): StockTake {
        val token = requireToken()
        val payload = JSONObject()
            .put("branch", session.branchId)
            .put("stock_take_type", type)
            .put("count_date", countDate)
        val body = postJson("${config.serverUrl}/api/stock-takes/", payload, token)
        return JsonParsers.parseStockTake(body)
    }

    fun updateStockTakeLines(
        stockTakeId: Int,
        lines: List<Pair<Int, String?>>,
    ): StockTake {
        val token = requireToken()
        val linesJson = JSONArray()
        for ((lineId, counted) in lines) {
            val line = JSONObject().put("id", lineId)
            if (counted == null) {
                line.put("counted_quantity", JSONObject.NULL)
            } else {
                line.put("counted_quantity", counted)
            }
            linesJson.put(line)
        }
        val payload = JSONObject().put("lines", linesJson)
        val body = patchJson("${config.serverUrl}/api/stock-takes/$stockTakeId/lines/", payload, token)
        return JsonParsers.parseStockTake(body)
    }

    fun completeStockTake(stockTakeId: Int): StockTake {
        val token = requireToken()
        val body = postJson(
            "${config.serverUrl}/api/stock-takes/$stockTakeId/complete/",
            JSONObject(),
            token,
        )
        return JsonParsers.parseStockTake(body)
    }

    fun depositToCustomer(
        customerId: Int,
        currencyId: Int,
        amount: String,
        notes: String = "",
    ): CustomerDepositResult {
        val token = requireToken()
        val branchId = session.branchId
        if (branchId <= 0) {
            throw ApiException(400, "Branch is not configured for this session.")
        }
        if (customerId <= 0) {
            throw ApiException(400, "Select a customer.")
        }
        if (currencyId <= 0) {
            throw ApiException(400, "Select a currency.")
        }
        val payload = JSONObject()
            .put("branch", branchId)
            .put("currency_id", currencyId)
            .put("amount", amount)
            .put("notes", notes)
        val body = postJson(
            "${config.serverUrl}/api/customers/$customerId/deposit/",
            payload,
            token,
        )
        return try {
            JsonParsers.parseCustomerDeposit(body)
        } catch (err: IllegalArgumentException) {
            throw ApiException(502, err.message ?: "Deposit was not confirmed by the server.")
        }
    }

    fun fetchCustomer(customerId: Int): Customer {
        val token = requireToken()
        val body = getJson("${config.serverUrl}/api/customers/$customerId/", token)
        return JsonParsers.parseCustomer(body)
    }

    fun fetchDayEndReport(date: String, countedByCurrency: Map<Int, String>): DayEndReportResponse {
        val token = requireToken()
        val counted = JSONObject()
        for ((currencyId, amount) in countedByCurrency) {
            counted.put(currencyId.toString(), amount)
        }
        val payload = JSONObject()
            .put("branch", session.branchId)
            .put("date", date)
            .put("counted", counted)
        val body = postJson("${config.serverUrl}/api/reports/day-end/", payload, token)
        return JsonParsers.parseDayEndReport(body)
    }

    fun createOrder(
        orderType: String,
        tableNumber: String?,
        items: List<CartLine>,
    ): KitchenOrder {
        val token = requireToken()
        val itemsJson = JSONArray()
        for (line in items) {
            val item = JSONObject()
                .put("product_id", line.productId)
                .put("quantity", line.quantity)
            if (line.notes.isNotBlank()) {
                item.put("notes", line.notes)
            }
            if (line.addons.isNotEmpty()) {
                val addonIds = JSONArray()
                for (addon in line.addons) {
                    addonIds.put(addon.id)
                }
                item.put("addon_ids", addonIds)
            }
            itemsJson.put(item)
        }
        val payload = JSONObject()
            .put("branch", session.branchId)
            .put("order_type", orderType)
            .put("items", itemsJson)
        if (!tableNumber.isNullOrBlank()) {
            payload.put("table_number", tableNumber.trim())
        }
        val body = postJson("${config.serverUrl}/api/orders/", payload, token)
        return JsonParsers.parseOrder(body)
    }

    fun updateOrderCustomer(orderId: Int, customerId: Int?): KitchenOrder {
        val token = requireToken()
        val payload = JSONObject().put("customer", customerId ?: JSONObject.NULL)
        val body = patchJson("${config.serverUrl}/api/orders/$orderId/", payload, token)
        return JsonParsers.parseOrder(body)
    }

    fun cancelOrder(orderId: Int): KitchenOrder {
        val token = requireToken()
        val body = postJson("${config.serverUrl}/api/orders/$orderId/cancel/", JSONObject(), token)
        return JsonParsers.parseOrder(body)
    }

    fun payOrderCash(orderId: Int, currencyId: Int): KitchenOrder {
        val token = requireToken()
        val payload = JSONObject()
            .put("currency_id", currencyId)
            .put("payment_method", "cash")
        val body = postJson("${config.serverUrl}/api/orders/$orderId/pay/", payload, token)
        return JsonParsers.parseOrder(body)
    }

    fun payOrderWithTenders(
        orderId: Int,
        payments: List<Pair<Int, String>>,
    ): KitchenOrder {
        val token = requireToken()
        val lines = org.json.JSONArray()
        payments.forEach { (currencyId, amount) ->
            lines.put(
                JSONObject()
                    .put("currency_id", currencyId)
                    .put("amount", amount),
            )
        }
        val paymentMethod = if (payments.size > 1) "multi" else "cash"
        val payload = JSONObject()
            .put("payment_method", paymentMethod)
            .put("payments", lines)
        val body = postJson("${config.serverUrl}/api/orders/$orderId/pay/", payload, token)
        return JsonParsers.parseOrder(body)
    }

    fun payOrderFromAccount(orderId: Int): KitchenOrder {
        val token = requireToken()
        val payload = JSONObject().put("payment_method", "account")
        val body = postJson("${config.serverUrl}/api/orders/$orderId/pay/", payload, token)
        return JsonParsers.parseOrder(body)
    }

    private fun requireToken(): String {
        return session.token ?: throw ApiException(401, "Not logged in")
    }

    private fun postJson(urlString: String, payload: JSONObject, authToken: String?): String {
        return sendJsonWithBody(urlString, "POST", payload, authToken, redirectCount = 0)
    }

    private fun patchJson(urlString: String, payload: JSONObject, token: String): String {
        // Prefer real PATCH; fall back handled by sendJsonWithBody redirect logic.
        return sendJsonWithBody(urlString, "PATCH", payload, token, redirectCount = 0)
    }

    private fun sendJsonWithBody(
        urlString: String,
        method: String,
        payload: JSONObject,
        authToken: String?,
        redirectCount: Int,
    ): String {
        if (redirectCount > 3) {
            throw ApiException(502, "Too many redirects talking to the server.")
        }
        val connection = openConnection(urlString, method, authToken)
        connection.doOutput = true
        connection.instanceFollowRedirects = false
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        val bytes = payload.toString().toByteArray(Charsets.UTF_8)
        connection.setFixedLengthStreamingMode(bytes.size)
        connection.outputStream.use { stream ->
            stream.write(bytes)
            stream.flush()
        }
        return try {
            val code = connection.responseCode
            if (code in REDIRECT_CODES) {
                val location = connection.getHeaderField("Location")
                    ?: throw ApiException(code, "Redirect without Location header.")
                val nextUrl = resolveRedirectUrl(urlString, location)
                connection.disconnect()
                // Re-send the same method+body. Never convert POST into GET.
                return sendJsonWithBody(nextUrl, method, payload, authToken, redirectCount + 1)
            }
            readResponse(connection, code)
        } finally {
            connection.disconnect()
        }
    }

    private fun resolveRedirectUrl(currentUrl: String, location: String): String {
        return if (location.startsWith("http://") || location.startsWith("https://")) {
            location
        } else {
            URL(URL(currentUrl), location).toString()
        }
    }

    private fun getJson(urlString: String, token: String): String {
        val connection = openConnection(urlString, "GET", token)
        connection.instanceFollowRedirects = true
        return try {
            readResponse(connection)
        } finally {
            connection.disconnect()
        }
    }

    private fun openConnection(urlString: String, method: String, token: String?): HttpURLConnection {
        val connection = URL(urlString).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 10_000
        connection.readTimeout = 15_000
        connection.setRequestProperty("Accept", "application/json")
        if (!token.isNullOrBlank()) {
            connection.setRequestProperty("Authorization", "Token $token")
        }
        return connection
    }

    private fun readResponse(connection: HttpURLConnection, knownCode: Int? = null): String {
        val code = knownCode ?: connection.responseCode
        val stream = if (code in 200..299) {
            connection.inputStream
        } else {
            connection.errorStream ?: connection.inputStream
        }
        val body = BufferedReader(InputStreamReader(stream, Charsets.UTF_8))
            .use { it.readText() }
        if (code !in 200..299) {
            throw ApiException(code, extractErrorMessage(body, code))
        }
        return body
    }

    private fun extractErrorMessage(body: String, code: Int): String {
        if (body.isBlank()) return "Request failed ($code)"
        return try {
            val json = JSONObject(body)
            when {
                json.has("detail") -> {
                    when (val detail = json.get("detail")) {
                        is String -> detail
                        is JSONArray -> (0 until detail.length()).joinToString("\n") {
                            detail.optString(it)
                        }
                        else -> detail.toString()
                    }
                }
                else -> {
                    val parts = mutableListOf<String>()
                    val keys = json.keys()
                    while (keys.hasNext()) {
                        val key = keys.next()
                        val value = json.get(key)
                        val message = when (value) {
                            is JSONArray -> (0 until value.length()).joinToString(", ") {
                                value.optString(it)
                            }
                            else -> value.toString()
                        }
                        parts.add("$key: $message")
                    }
                    parts.joinToString("\n").ifBlank { "Request failed ($code)" }
                }
            }
        } catch (_: Exception) {
            body
        }
    }

    companion object {
        private val REDIRECT_CODES = setOf(301, 302, 303, 307, 308)
    }
}
