package com.cafedeparis.kitchen.data

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
        val body = postJson("${config.serverUrl}/api/auth/kitchen-login/", payload, authToken = null)
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
