package com.cafedeparis.kitchen.data

import android.content.Context
import org.json.JSONObject
import java.io.File

class AppConfig(private val context: Context) {

    private var cachedServerUrl: String? = null

    val serverUrl: String
        get() = cachedServerUrl ?: loadServerUrl().also { cachedServerUrl = it }

    val configFile: File
        get() = File(context.getExternalFilesDir(null), CONFIG_FILE_NAME)

    fun reload() {
        cachedServerUrl = null
    }

    private fun loadServerUrl(): String {
        ensureExternalConfig()
        val external = configFile
        if (external.exists()) {
            return parseServerUrl(external.readText())
        }
        return readAssetConfig()?.let { parseServerUrl(it) } ?: DEFAULT_SERVER_URL
    }

    private fun ensureExternalConfig() {
        val external = configFile
        if (external.exists()) return
        val parent = external.parentFile ?: return
        if (!parent.exists()) parent.mkdirs()
        val assetText = readAssetConfig() ?: return
        external.writeText(assetText)
    }

    private fun readAssetConfig(): String? {
        return try {
            context.assets.open(CONFIG_FILE_NAME).bufferedReader().use { it.readText() }
        } catch (_: Exception) {
            null
        }
    }

    private fun parseServerUrl(raw: String): String {
        return try {
            val json = JSONObject(raw)
            json.optString("serverUrl", DEFAULT_SERVER_URL).trim().trimEnd('/')
        } catch (_: Exception) {
            DEFAULT_SERVER_URL
        }
    }

    companion object {
        private const val CONFIG_FILE_NAME = "config.json"
        const val DEFAULT_SERVER_URL = "http://192.168.100.69:8000"
    }
}
