package com.cafedeparis.kitchen.data

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
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

    fun fetchDayEndReport(date: String, countedByCurrency: Map<Int, String>): DayEndReportResponse {
        val token = requireToken()
        val branchId = session.branchId
        val query = StringBuilder("branch=$branchId&date=$date")
        for ((currencyId, amount) in countedByCurrency) {
            query.append("&counted_$currencyId=${java.net.URLEncoder.encode(amount, Charsets.UTF_8.name())}")
        }
        val url = "${config.serverUrl}/api/reports/day-end/?$query"
        val body = getJson(url, token)
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

    fun payOrderCash(orderId: Int, currencyId: Int): KitchenOrder {
        val token = requireToken()
        val payload = JSONObject()
            .put("currency_id", currencyId)
            .put("payment_method", "cash")
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

    private fun getJson(urlString: String, token: String): String {
        val connection = openConnection(urlString, "GET", token)
        return readResponse(connection)
    }

    private fun postJson(urlString: String, payload: JSONObject, authToken: String?): String {
        val connection = openConnection(urlString, "POST", authToken)
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { writer ->
            writer.write(payload.toString())
        }
        return readResponse(connection)
    }

    private fun patchJson(urlString: String, payload: JSONObject, token: String): String {
        val connection = openConnection(urlString, "PATCH", token)
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { writer ->
            writer.write(payload.toString())
        }
        return readResponse(connection)
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

    private fun readResponse(connection: HttpURLConnection): String {
        val code = connection.responseCode
        val stream = if (code in 200..299) {
            connection.inputStream
        } else {
            connection.errorStream
        }
        val body = BufferedReader(InputStreamReader(stream ?: connection.inputStream, Charsets.UTF_8))
            .use { it.readText() }
        if (code !in 200..299) {
            val detail = runCatching { JSONObject(body).optString("detail", body) }.getOrDefault(body)
            throw ApiException(code, detail.ifBlank { "Request failed ($code)" })
        }
        return body
    }
}
